"""Base provider interface for API key validation and data fetching."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KeyValidationResult:
    is_valid: bool
    is_read_only: bool
    error: str | None = None


@dataclass
class RateLimitInfo:
    """Rate limit data for a single model."""

    model: str
    rpm_limit: int  # requests per minute
    rpm_used: int
    tpm_limit: int  # tokens per minute
    tpm_used: int
    rpd_limit: int = 0  # requests per day
    rpd_used: int = 0

    @property
    def rpm_pct(self) -> float:
        return (self.rpm_used / self.rpm_limit * 100) if self.rpm_limit else 0

    @property
    def tpm_pct(self) -> float:
        return (self.tpm_used / self.tpm_limit * 100) if self.tpm_limit else 0


@dataclass
class UsageData:
    """Token usage for a time period."""

    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    period_start: datetime
    period_end: datetime


@dataclass
class CostData:
    """Cost data for a time period."""

    total_usd: float
    period_start: datetime
    period_end: datetime
    breakdown: list[dict] = field(default_factory=list)  # per-model breakdown


@dataclass
class ProviderSnapshot:
    """Complete snapshot of provider data from a single poll."""

    provider: str
    rate_limits: list[RateLimitInfo]
    usage: list[UsageData]
    costs: CostData | None
    is_stale: bool = False
    error: str | None = None
    fetched_at: datetime | None = None


class BaseProvider(ABC):
    @abstractmethod
    async def validate_key(self, api_key: str, **kwargs) -> KeyValidationResult:
        """Validate that the key is valid and read-only."""

    @abstractmethod
    async def get_rate_limits(self, api_key: str, **kwargs) -> list[RateLimitInfo]:
        """Fetch current rate limit usage for all models."""

    @abstractmethod
    async def get_usage(self, api_key: str, **kwargs) -> list[UsageData]:
        """Fetch token usage for current billing period."""

    @abstractmethod
    async def get_costs(self, api_key: str, **kwargs) -> CostData | None:
        """Fetch cost data for current billing period."""

    @property
    @abstractmethod
    def provider_type(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...
