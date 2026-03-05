"""Background polling tasks — fetch provider data periodically."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.auth.encryption import decrypt_key
from app.auth.models import APIKeyStore
from app.cache import (
    HistoryPoint,
    append_history_point,
    set_cached_costs,
    set_cached_rate_limits,
    set_cached_snapshot,
    set_cached_usage,
)
from app.config import settings
from app.db import async_session
from app.providers.base import ProviderSnapshot
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)


async def _poll_user_provider(record: APIKeyStore, fetch_rate_limits=True, fetch_usage_costs=True):
    """Poll a single user+provider and update cache."""
    provider = get_provider(record.provider.value)
    if not provider:
        return

    try:
        api_key = decrypt_key(record.encrypted_key)
    except Exception:
        logger.error("Failed to decrypt key for user=%s provider=%s", record.user_id, record.provider.value)
        return

    kwargs = {}
    if record.tier:
        kwargs["tier"] = record.tier

    now = datetime.now(UTC)
    error = None
    rate_limits = []
    usage = []
    costs = None

    if fetch_rate_limits:
        try:
            rate_limits = await provider.get_rate_limits(api_key, **kwargs)
            set_cached_rate_limits(record.user_id, record.provider.value, rate_limits)
        except Exception as e:
            logger.warning(
                "Rate limits fetch failed for user=%s provider=%s: %s", record.user_id, record.provider.value, e
            )
            error = str(e)

    if fetch_usage_costs:
        try:
            usage = await provider.get_usage(api_key, **kwargs)
            set_cached_usage(record.user_id, record.provider.value, usage)
        except Exception as e:
            logger.warning("Usage fetch failed for user=%s provider=%s: %s", record.user_id, record.provider.value, e)
            error = error or str(e)

        try:
            costs = await provider.get_costs(api_key, **kwargs)
            set_cached_costs(record.user_id, record.provider.value, costs)
        except Exception as e:
            logger.warning("Costs fetch failed for user=%s provider=%s: %s", record.user_id, record.provider.value, e)
            error = error or str(e)

    # Store full snapshot
    snapshot = ProviderSnapshot(
        provider=record.provider.value,
        rate_limits=rate_limits,
        usage=usage,
        costs=costs,
        is_stale=error is not None,
        error=error,
        fetched_at=now,
    )
    set_cached_snapshot(record.user_id, record.provider.value, snapshot)

    # Record history point for charts
    rpm_pct = max((rl.rpm_pct for rl in rate_limits), default=0.0)
    tpm_pct = max((rl.tpm_pct for rl in rate_limits), default=0.0)
    cost_usd = costs.total_usd if costs else 0.0
    append_history_point(
        record.user_id,
        record.provider.value,
        HistoryPoint(timestamp=now, rpm_pct=rpm_pct, tpm_pct=tpm_pct, cost_usd=cost_usd),
    )

    logger.info(
        "Polled user=%s provider=%s: %d rate_limits, %d usage, costs=%s, stale=%s",
        record.user_id,
        record.provider.value,
        len(rate_limits),
        len(usage),
        costs is not None,
        snapshot.is_stale,
    )


async def _poll_all(fetch_rate_limits=True, fetch_usage_costs=True):
    """Poll all active providers for all users."""
    async with async_session() as db:
        result = await db.execute(select(APIKeyStore).where(APIKeyStore.is_valid.is_(True)))
        records = result.scalars().all()

    for record in records:
        try:
            await _poll_user_provider(record, fetch_rate_limits=fetch_rate_limits, fetch_usage_costs=fetch_usage_costs)
        except Exception as e:
            logger.error("Polling error for user=%s provider=%s: %s", record.user_id, record.provider.value, e)


async def poll_rate_limits_loop():
    """Background loop: poll rate limits every POLLING_INTERVAL_RATE_LIMITS seconds."""
    logger.info("Starting rate limits polling loop (interval=%ds)", settings.POLLING_INTERVAL_RATE_LIMITS)
    while True:
        try:
            await _poll_all(fetch_rate_limits=True, fetch_usage_costs=False)
        except Exception as e:
            logger.error("Rate limits polling cycle failed: %s", e)
        await asyncio.sleep(settings.POLLING_INTERVAL_RATE_LIMITS)


async def poll_usage_costs_loop():
    """Background loop: poll usage+costs every POLLING_INTERVAL_USAGE_COSTS seconds."""
    logger.info("Starting usage/costs polling loop (interval=%ds)", settings.POLLING_INTERVAL_USAGE_COSTS)
    while True:
        try:
            await _poll_all(fetch_rate_limits=False, fetch_usage_costs=True)
        except Exception as e:
            logger.error("Usage/costs polling cycle failed: %s", e)
        await asyncio.sleep(settings.POLLING_INTERVAL_USAGE_COSTS)
