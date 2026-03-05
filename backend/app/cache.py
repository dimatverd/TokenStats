"""TTL cache for provider data — swap for Redis in production."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from cachetools import TTLCache

from app.config import settings
from app.providers.base import CostData, ProviderSnapshot, RateLimitInfo, UsageData

# ── History ring buffer (last 24h) ──────────────────────

MAX_HISTORY_POINTS = 1440  # 24h at one point per minute


@dataclass
class HistoryPoint:
    """A single historical data point for charts."""

    timestamp: datetime
    rpm_pct: float
    tpm_pct: float
    cost_usd: float


# keyed by "user_id:provider" -> deque of HistoryPoint
_history_store: dict[str, deque[HistoryPoint]] = {}


def append_history_point(user_id: int, provider: str, point: HistoryPoint) -> None:
    """Append a history point to the ring buffer for a user+provider."""
    k = _key(user_id, provider)
    if k not in _history_store:
        _history_store[k] = deque(maxlen=MAX_HISTORY_POINTS)
    _history_store[k].append(point)


def get_history(user_id: int, provider: str) -> list[HistoryPoint]:
    """Return all history points for a user+provider."""
    k = _key(user_id, provider)
    buf = _history_store.get(k)
    if buf is None:
        return []
    return list(buf)


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
    _history_store.clear()
