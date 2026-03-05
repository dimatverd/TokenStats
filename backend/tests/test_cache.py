"""Tests for cache layer — US-10 acceptance criteria."""

from datetime import UTC, datetime

import pytest

from app.cache import (
    clear_all,
    get_cached_costs,
    get_cached_rate_limits,
    get_cached_snapshot,
    get_cached_usage,
    invalidate_provider,
    set_cached_costs,
    set_cached_rate_limits,
    set_cached_snapshot,
    set_cached_usage,
)
from app.providers.base import CostData, ProviderSnapshot, RateLimitInfo, UsageData


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_all()
    yield
    clear_all()


def test_rate_limits_cache_hit():
    """US-10: cached rate limits returned within TTL."""
    data = [RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=10, tpm_limit=50000, tpm_used=1000)]
    set_cached_rate_limits(1, "openai", data)
    result = get_cached_rate_limits(1, "openai")
    assert result is not None
    assert len(result) == 1
    assert result[0].model == "gpt-4"
    assert result[0].rpm_pct == 10.0


def test_rate_limits_cache_miss():
    """US-10: no cached data → None."""
    assert get_cached_rate_limits(1, "openai") is None


def test_usage_cache():
    """US-10: usage data cached and retrieved."""
    now = datetime.now(UTC)
    data = [
        UsageData(model="gpt-4", input_tokens=100, output_tokens=50, total_tokens=150, period_start=now, period_end=now)
    ]
    set_cached_usage(1, "openai", data)
    result = get_cached_usage(1, "openai")
    assert result is not None
    assert result[0].total_tokens == 150


def test_costs_cache():
    """US-10: costs data cached and retrieved."""
    now = datetime.now(UTC)
    cost = CostData(total_usd=42.50, period_start=now, period_end=now)
    set_cached_costs(1, "openai", cost)
    result = get_cached_costs(1, "openai")
    assert result is not None
    assert result.total_usd == 42.50


def test_snapshot_cache():
    """Full snapshot cached and retrieved."""
    now = datetime.now(UTC)
    snapshot = ProviderSnapshot(
        provider="openai",
        rate_limits=[RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=50, tpm_limit=10000, tpm_used=5000)],
        usage=[],
        costs=None,
        fetched_at=now,
    )
    set_cached_snapshot(1, "openai", snapshot)
    result = get_cached_snapshot(1, "openai")
    assert result is not None
    assert result.provider == "openai"
    assert result.rate_limits[0].rpm_pct == 50.0


def test_invalidate_provider():
    """Invalidating clears all caches for user+provider."""
    data = [RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=10, tpm_limit=50000, tpm_used=1000)]
    set_cached_rate_limits(1, "openai", data)
    set_cached_usage(1, "openai", [])
    invalidate_provider(1, "openai")
    assert get_cached_rate_limits(1, "openai") is None
    assert get_cached_usage(1, "openai") is None


def test_cache_isolation_between_users():
    """Different users have separate cache entries."""
    data1 = [RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=10, tpm_limit=50000, tpm_used=100)]
    data2 = [RateLimitInfo(model="gpt-4", rpm_limit=200, rpm_used=20, tpm_limit=100000, tpm_used=200)]
    set_cached_rate_limits(1, "openai", data1)
    set_cached_rate_limits(2, "openai", data2)
    assert get_cached_rate_limits(1, "openai")[0].rpm_limit == 100
    assert get_cached_rate_limits(2, "openai")[0].rpm_limit == 200


def test_cache_isolation_between_providers():
    """Different providers have separate cache entries."""
    set_cached_rate_limits(
        1, "openai", [RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=0, tpm_limit=50000, tpm_used=0)]
    )
    set_cached_rate_limits(
        1, "anthropic", [RateLimitInfo(model="claude", rpm_limit=50, rpm_used=0, tpm_limit=40000, tpm_used=0)]
    )
    assert get_cached_rate_limits(1, "openai")[0].rpm_limit == 100
    assert get_cached_rate_limits(1, "anthropic")[0].rpm_limit == 50
