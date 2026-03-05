"""Tests for API v1 endpoints — summary, limits, usage, costs."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.cache import (
    HistoryPoint,
    append_history_point,
    clear_all,
    set_cached_costs,
    set_cached_rate_limits,
    set_cached_snapshot,
    set_cached_usage,
)
from app.providers.base import CostData, ProviderSnapshot, RateLimitInfo, UsageData


async def _register_and_get_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/auth/register",
        json={"email": "api@example.com", "password": "securepass123"},
    )
    return resp.json()["access_token"]


async def _auth_headers(client: AsyncClient) -> dict:
    token = await _register_and_get_token(client)
    return {"Authorization": f"Bearer {token}"}


async def _add_provider(client: AsyncClient, headers: dict, provider: str = "anthropic", tier: str = "tier1"):
    """Add a provider key (mocked validation via direct DB insert)."""
    from app.auth.encryption import encrypt_key
    from app.auth.models import APIKeyStore, ProviderType
    from app.db import get_db
    from app.main import app

    db_override = app.dependency_overrides[get_db]
    async for session in db_override():
        # Get user id from token
        resp = await client.get("/auth/me", headers=headers)
        user_id = resp.json()["id"]

        record = APIKeyStore(
            user_id=user_id,
            provider=ProviderType(provider),
            encrypted_key=encrypt_key("sk-ant-admin-test-key"),
            key_hint="tkey",
            tier=tier,
            is_valid=True,
            validated_at=datetime.now(UTC),
        )
        session.add(record)
        await session.commit()
        return user_id


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_all()
    yield
    clear_all()


# ── Summary ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_no_providers(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["providers"] == []


@pytest.mark.asyncio
async def test_summary_with_provider_no_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    await _add_provider(client, headers)
    resp = await client.get("/api/v1/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["id"] == "anthropic"
    assert data["providers"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_summary_with_cached_data(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    now = datetime.now(UTC)
    set_cached_snapshot(
        user_id,
        "anthropic",
        ProviderSnapshot(
            provider="anthropic",
            rate_limits=[
                RateLimitInfo(model="claude-sonnet", rpm_limit=1000, rpm_used=50, tpm_limit=400000, tpm_used=100000)
            ],
            usage=[],
            costs=CostData(total_usd=12.50, period_start=now, period_end=now),
            fetched_at=now,
        ),
    )

    resp = await client.get("/api/v1/summary", headers=headers)
    assert resp.status_code == 200
    p = resp.json()["providers"][0]
    assert p["status"] == "ok"
    assert p["rpm"]["used"] == 50
    assert p["rpm"]["limit"] == 1000
    assert p["tpm"]["pct"] == 25.0
    assert p["cost_today"] == 12.50


@pytest.mark.asyncio
async def test_summary_compact_format(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    now = datetime.now(UTC)
    set_cached_snapshot(
        user_id,
        "anthropic",
        ProviderSnapshot(
            provider="anthropic",
            rate_limits=[
                RateLimitInfo(model="claude-sonnet", rpm_limit=1000, rpm_used=50, tpm_limit=400000, tpm_used=100000)
            ],
            usage=[],
            costs=CostData(total_usd=12.50, period_start=now, period_end=now),
            fetched_at=now,
        ),
    )

    resp = await client.get("/api/v1/summary?format=compact", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "p" in data
    assert data["p"][0]["n"] == "CL"
    assert data["p"][0]["s"] == 1
    assert data["p"][0]["c"] == 12.5


@pytest.mark.asyncio
async def test_summary_stale_provider(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    set_cached_snapshot(
        user_id,
        "anthropic",
        ProviderSnapshot(
            provider="anthropic",
            rate_limits=[],
            usage=[],
            costs=None,
            is_stale=True,
            error="Connection timeout",
            fetched_at=datetime.now(UTC),
        ),
    )

    resp = await client.get("/api/v1/summary", headers=headers)
    assert resp.json()["providers"][0]["status"] == "stale"


# ── Limits ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limits_no_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    await _add_provider(client, headers)
    resp = await client.get("/api/v1/limits/anthropic", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_limits_with_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    set_cached_rate_limits(
        user_id,
        "anthropic",
        [
            RateLimitInfo(model="claude-sonnet", rpm_limit=1000, rpm_used=50, tpm_limit=400000, tpm_used=100000),
        ],
    )

    resp = await client.get("/api/v1/limits/anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["model"] == "claude-sonnet"
    assert data[0]["rpm_pct"] == 5.0
    assert data[0]["tpm_pct"] == 25.0


@pytest.mark.asyncio
async def test_limits_unknown_provider(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/limits/invalid", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_limits_provider_not_configured(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/limits/anthropic", headers=headers)
    assert resp.status_code == 404
    assert "not configured" in resp.json()["detail"]


# ── Usage ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_usage_no_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    await _add_provider(client, headers)
    resp = await client.get("/api/v1/usage/anthropic", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_usage_with_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    now = datetime.now(UTC)
    set_cached_usage(
        user_id,
        "anthropic",
        [
            UsageData(
                model="claude-sonnet",
                input_tokens=5000,
                output_tokens=2000,
                total_tokens=7000,
                period_start=now,
                period_end=now,
            ),
        ],
    )

    resp = await client.get("/api/v1/usage/anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["total_tokens"] == 7000


# ── Costs ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_costs_no_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    await _add_provider(client, headers)
    resp = await client.get("/api/v1/costs/anthropic", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_costs_with_cache(client: AsyncClient):
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    now = datetime.now(UTC)
    set_cached_costs(
        user_id,
        "anthropic",
        CostData(
            total_usd=42.50,
            period_start=now,
            period_end=now,
            breakdown=[{"model": "claude-sonnet", "usd": 42.50}],
        ),
    )

    resp = await client.get("/api/v1/costs/anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_usd"] == 42.50
    assert len(data["breakdown"]) == 1


# ── Auth required ───────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/summary")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_limits_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/limits/anthropic")
    assert resp.status_code == 403


# ── History ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_history_empty(client: AsyncClient):
    """History endpoint returns empty list when no data points exist."""
    headers = await _auth_headers(client)
    await _add_provider(client, headers)
    resp = await client.get("/api/v1/history/anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["points"] == []


@pytest.mark.asyncio
async def test_history_with_points(client: AsyncClient):
    """History endpoint returns stored data points."""
    headers = await _auth_headers(client)
    user_id = await _add_provider(client, headers)

    now = datetime.now(UTC)
    for i in range(3):
        append_history_point(
            user_id,
            "anthropic",
            HistoryPoint(timestamp=now, rpm_pct=10.0 + i, tpm_pct=20.0 + i, cost_usd=1.5 + i),
        )

    resp = await client.get("/api/v1/history/anthropic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 3
    assert data["points"][0]["rpm_pct"] == 10.0
    assert data["points"][2]["cost_usd"] == 3.5


@pytest.mark.asyncio
async def test_history_unknown_provider(client: AsyncClient):
    """History endpoint returns 404 for unknown provider."""
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/history/invalid", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_history_requires_auth(client: AsyncClient):
    """History endpoint requires authentication."""
    resp = await client.get("/api/v1/history/anthropic")
    assert resp.status_code == 403
