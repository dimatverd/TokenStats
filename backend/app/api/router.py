"""API v1 router — summary, limits, usage, costs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CompactProvider,
    CompactSummaryResponse,
    CostResponse,
    ProviderSummary,
    RateLimitResponse,
    SummaryResponse,
    UsageResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.models import APIKeyStore, ProviderType, User
from app.cache import get_cached_costs, get_cached_rate_limits, get_cached_snapshot, get_cached_usage
from app.db import get_db

router = APIRouter(prefix="/api/v1", tags=["api"])

PROVIDER_SHORT_NAMES = {
    "anthropic": "CL",
    "openai": "OA",
    "google": "GV",
}

PROVIDER_DISPLAY_NAMES = {
    "anthropic": "Claude",
    "openai": "OpenAI",
    "google": "Vertex AI",
}


async def _get_user_providers(user: User, db: AsyncSession) -> list[APIKeyStore]:
    result = await db.execute(select(APIKeyStore).where(APIKeyStore.user_id == user.id))
    return list(result.scalars().all())


def _validate_provider(provider: str) -> str:
    try:
        return ProviderType(provider).value
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")


async def _ensure_user_has_provider(user: User, provider: str, db: AsyncSession) -> APIKeyStore:
    ptype = ProviderType(provider)
    result = await db.execute(select(APIKeyStore).where(APIKeyStore.user_id == user.id, APIKeyStore.provider == ptype))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not configured")
    return record


@router.get("/summary")
async def get_summary(
    format: str = Query(default="full", regex="^(full|compact)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    providers = await _get_user_providers(user, db)

    if format == "compact":
        items = []
        for p in providers:
            pv = p.provider.value
            snapshot = get_cached_snapshot(user.id, pv)
            rpm_pct = 0.0
            tpm_pct = 0.0
            cost = 0.0
            status = 0

            if snapshot and not snapshot.is_stale:
                status = 1
                if snapshot.rate_limits:
                    rpm_pct = max(rl.rpm_pct for rl in snapshot.rate_limits)
                    tpm_pct = max(rl.tpm_pct for rl in snapshot.rate_limits)
                if snapshot.costs:
                    cost = snapshot.costs.total_usd

            items.append(
                CompactProvider(
                    n=PROVIDER_SHORT_NAMES.get(pv, pv[:2].upper()),
                    s=status,
                    r=round(rpm_pct, 1),
                    t=round(tpm_pct, 1),
                    c=round(cost, 2),
                )
            )
        return CompactSummaryResponse(p=items)

    # Full format
    summaries = []
    latest_update = None

    for p in providers:
        pv = p.provider.value
        snapshot = get_cached_snapshot(user.id, pv)

        status = "ok"
        rpm = None
        tpm = None
        cost_today = None

        if snapshot is None:
            status = "pending"
        elif snapshot.is_stale:
            status = "stale"
        else:
            if snapshot.rate_limits:
                # Aggregate: take max usage across models
                max_rpm = max(snapshot.rate_limits, key=lambda r: r.rpm_pct)
                max_tpm = max(snapshot.rate_limits, key=lambda r: r.tpm_pct)
                rpm = {"used": max_rpm.rpm_used, "limit": max_rpm.rpm_limit, "pct": round(max_rpm.rpm_pct, 1)}
                tpm = {"used": max_tpm.tpm_used, "limit": max_tpm.tpm_limit, "pct": round(max_tpm.tpm_pct, 1)}
            if snapshot.costs:
                cost_today = snapshot.costs.total_usd

        if snapshot and snapshot.fetched_at:
            if latest_update is None or snapshot.fetched_at > latest_update:
                latest_update = snapshot.fetched_at

        summaries.append(
            ProviderSummary(
                id=pv,
                name=PROVIDER_DISPLAY_NAMES.get(pv, pv),
                status=status,
                rpm=rpm,
                tpm=tpm,
                cost_today=cost_today,
            )
        )

    return SummaryResponse(providers=summaries, updated_at=latest_update)


@router.get("/limits/{provider}", response_model=list[RateLimitResponse])
async def get_limits(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = _validate_provider(provider)
    await _ensure_user_has_provider(user, provider, db)

    cached = get_cached_rate_limits(user.id, provider)
    if cached is None:
        return []

    return [
        RateLimitResponse(
            model=rl.model,
            rpm_limit=rl.rpm_limit,
            rpm_used=rl.rpm_used,
            rpm_pct=round(rl.rpm_pct, 1),
            tpm_limit=rl.tpm_limit,
            tpm_used=rl.tpm_used,
            tpm_pct=round(rl.tpm_pct, 1),
        )
        for rl in cached
    ]


@router.get("/usage/{provider}", response_model=list[UsageResponse])
async def get_usage(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = _validate_provider(provider)
    await _ensure_user_has_provider(user, provider, db)

    cached = get_cached_usage(user.id, provider)
    if cached is None:
        return []

    return [
        UsageResponse(
            model=u.model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            total_tokens=u.total_tokens,
            period_start=u.period_start,
            period_end=u.period_end,
        )
        for u in cached
    ]


@router.get("/costs/{provider}", response_model=CostResponse | None)
async def get_costs(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = _validate_provider(provider)
    await _ensure_user_has_provider(user, provider, db)

    cached = get_cached_costs(user.id, provider)
    if cached is None:
        return None

    return CostResponse(
        total_usd=cached.total_usd,
        period_start=cached.period_start,
        period_end=cached.period_end,
        breakdown=cached.breakdown,
    )
