"""Anthropic provider — Admin API key validation and data fetching."""

import httpx

from app.providers.base import (
    BaseProvider,
    CostData,
    KeyValidationResult,
    RateLimitInfo,
    UsageData,
)

# Anthropic tier rate limits (RPM/TPM per model class)
# https://docs.anthropic.com/en/docs/about-claude/models#rate-limits
TIER_LIMITS = {
    "tier1": {"rpm": 50, "tpm": 40_000},
    "tier2": {"rpm": 1_000, "tpm": 80_000},
    "tier3": {"rpm": 2_000, "tpm": 160_000},
    "tier4": {"rpm": 4_000, "tpm": 400_000},
    "build": {"rpm": 50, "tpm": 40_000},
    "scale": {"rpm": 4_000, "tpm": 400_000},
}


class AnthropicProvider(BaseProvider):
    provider_type = "anthropic"
    display_name = "Claude (Anthropic)"

    ADMIN_API_BASE = "https://api.anthropic.com/v1"

    def _headers(self, api_key: str) -> dict:
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}

    async def validate_key(self, api_key: str, **kwargs) -> KeyValidationResult:
        tier = kwargs.get("tier")
        if not tier:
            return KeyValidationResult(False, False, "Tier is required for Anthropic (tier1-tier4, build, scale)")

        if not api_key.startswith("sk-ant-admin"):
            return KeyValidationResult(False, False, "Key must be an Anthropic Admin API key (sk-ant-admin-...)")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/organizations",
                    headers=self._headers(api_key),
                )
                if resp.status_code == 401:
                    return KeyValidationResult(False, False, "Key validation failed: unauthorized")
                if resp.status_code == 403:
                    return KeyValidationResult(False, False, "Key validation failed: forbidden")
            except httpx.RequestError as e:
                return KeyValidationResult(False, False, f"Connection error: {e}")

            try:
                resp = await client.post(
                    f"{self.ADMIN_API_BASE}/messages",
                    headers={**self._headers(api_key), "content-type": "application/json"},
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "test"}],
                    },
                )
                if resp.status_code == 200:
                    return KeyValidationResult(False, False, "Key is not read-only: inference request succeeded")
            except httpx.RequestError:
                pass

        return KeyValidationResult(True, True)

    async def get_rate_limits(self, api_key: str, **kwargs) -> list[RateLimitInfo]:
        tier = kwargs.get("tier", "tier1")
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["tier1"])

        # Anthropic Admin API: GET /organizations/{org_id}/api_keys/{key_id}/usage
        # For now, return tier-based limits (actual usage requires org+key IDs)
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/organizations",
                    headers=self._headers(api_key),
                )
                if resp.status_code != 200:
                    return []
            except httpx.RequestError:
                return []

        models = ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-20250514"]
        return [
            RateLimitInfo(
                model=m,
                rpm_limit=limits["rpm"],
                rpm_used=0,  # Admin API doesn't expose per-model usage yet
                tpm_limit=limits["tpm"],
                tpm_used=0,
            )
            for m in models
        ]

    async def get_usage(self, api_key: str, **kwargs) -> list[UsageData]:
        # Anthropic Admin API doesn't have a direct usage endpoint yet
        # Return empty — will be populated when API supports it
        return []

    async def get_costs(self, api_key: str, **kwargs) -> CostData | None:
        # Anthropic Admin API doesn't have a direct billing endpoint yet
        return None
