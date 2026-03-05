"""TTL cache for provider data — swap for Redis in production."""

from cachetools import TTLCache

from app.config import settings
from app.providers.base import CostData, ProviderSnapshot, RateLimitInfo, UsageData

# Separate caches with different TTLs
_rate_limits_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.CACHE_TTL_RATE_LIMITS)
_usage_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.CACHE_TTL_USAGE)
_costs_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.CACHE_TTL_COSTS)
_snapshot_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.CACHE_TTL_RATE_LIMITS)


def _key(user_id: int, provider: str) -> str:
    return f"{user_id}:{provider}"


# ── Rate limits ─────────────────────────────────────────


def get_cached_rate_limits(user_id: int, provider: str) -> list[RateLimitInfo] | None:
    return _rate_limits_cache.get(_key(user_id, provider))


def set_cached_rate_limits(user_id: int, provider: str, data: list[RateLimitInfo]):
    _rate_limits_cache[_key(user_id, provider)] = data


# ── Usage ────────────────────────────────────────────────


def get_cached_usage(user_id: int, provider: str) -> list[UsageData] | None:
    return _usage_cache.get(_key(user_id, provider))


def set_cached_usage(user_id: int, provider: str, data: list[UsageData]):
    _usage_cache[_key(user_id, provider)] = data


# ── Costs ────────────────────────────────────────────────


def get_cached_costs(user_id: int, provider: str) -> CostData | None:
    return _costs_cache.get(_key(user_id, provider))


def set_cached_costs(user_id: int, provider: str, data: CostData | None):
    _costs_cache[_key(user_id, provider)] = data


# ── Full snapshot ────────────────────────────────────────


def get_cached_snapshot(user_id: int, provider: str) -> ProviderSnapshot | None:
    return _snapshot_cache.get(_key(user_id, provider))


def set_cached_snapshot(user_id: int, provider: str, snapshot: ProviderSnapshot):
    _snapshot_cache[_key(user_id, provider)] = snapshot


# ── Utilities ────────────────────────────────────────────


def invalidate_provider(user_id: int, provider: str):
    """Remove all cached data for a user+provider."""
    k = _key(user_id, provider)
    _rate_limits_cache.pop(k, None)
    _usage_cache.pop(k, None)
    _costs_cache.pop(k, None)
    _snapshot_cache.pop(k, None)


def clear_all():
    """Clear all caches (for testing)."""
    _rate_limits_cache.clear()
    _usage_cache.clear()
    _costs_cache.clear()
    _snapshot_cache.clear()
