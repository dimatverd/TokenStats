"""Response schemas for API v1 endpoints."""

from datetime import datetime

from pydantic import BaseModel


class RateLimitResponse(BaseModel):
    model: str
    rpm_limit: int
    rpm_used: int
    rpm_pct: float
    tpm_limit: int
    tpm_used: int
    tpm_pct: float


class UsageResponse(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    period_start: datetime
    period_end: datetime


class CostResponse(BaseModel):
    total_usd: float
    period_start: datetime
    period_end: datetime
    breakdown: list[dict]


class ProviderSummary(BaseModel):
    id: str
    name: str
    status: str  # "ok", "stale", "error"
    rpm: dict | None = None  # {"used": int, "limit": int, "pct": float}
    tpm: dict | None = None
    cost_today: float | None = None
    cost_month: float | None = None
    budget_month: float | None = None
    budget_pct: float | None = None


class SummaryResponse(BaseModel):
    providers: list[ProviderSummary]
    updated_at: datetime | None = None


class CompactProvider(BaseModel):
    n: str  # short name
    s: int  # status: 1=ok, 0=error
    r: float  # rpm %
    t: float  # tpm %
    c: float  # cost today


class CompactSummaryResponse(BaseModel):
    p: list[CompactProvider]
