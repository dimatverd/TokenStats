"""OpenAI provider — Admin API key validation and data fetching."""

from datetime import UTC, datetime, timedelta

import httpx

from app.providers.base import (
    BaseProvider,
    CostData,
    KeyValidationResult,
    RateLimitInfo,
    UsageData,
)


class OpenAIProvider(BaseProvider):
    provider_type = "openai"
    display_name = "OpenAI"

    ADMIN_API_BASE = "https://api.openai.com/v1"

    def _headers(self, api_key: str) -> dict:
        return {"Authorization": f"Bearer {api_key}"}

    async def validate_key(self, api_key: str, **kwargs) -> KeyValidationResult:
        if not api_key.startswith("sk-"):
            return KeyValidationResult(False, False, "Key must be an OpenAI API key (sk-...)")

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/models",
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
                    f"{self.ADMIN_API_BASE}/chat/completions",
                    headers={**self._headers(api_key), "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}], "max_tokens": 1},
                )
                if resp.status_code == 200:
                    return KeyValidationResult(False, False, "Key is not read-only: inference request succeeded")
            except httpx.RequestError:
                pass

        return KeyValidationResult(True, True)

    async def get_rate_limits(self, api_key: str, **kwargs) -> list[RateLimitInfo]:
        """Fetch rate limits from OpenAI organization/limits endpoint."""
        results = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                # OpenAI returns rate limits in response headers of any API call
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/models",
                    headers=self._headers(api_key),
                )
                if resp.status_code != 200:
                    return []

                # Parse rate limit headers (present on all API responses)
                rpm_limit = int(resp.headers.get("x-ratelimit-limit-requests", "0"))
                tpm_limit = int(resp.headers.get("x-ratelimit-limit-tokens", "0"))
                rpm_remaining = int(resp.headers.get("x-ratelimit-remaining-requests", "0"))
                tpm_remaining = int(resp.headers.get("x-ratelimit-remaining-tokens", "0"))

                if rpm_limit > 0:
                    results.append(RateLimitInfo(
                        model="organization",
                        rpm_limit=rpm_limit,
                        rpm_used=rpm_limit - rpm_remaining,
                        tpm_limit=tpm_limit,
                        tpm_used=tpm_limit - tpm_remaining,
                    ))
            except httpx.RequestError:
                pass

        return results

    async def get_usage(self, api_key: str, **kwargs) -> list[UsageData]:
        """Fetch usage from OpenAI usage endpoint."""
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/organization/usage",
                    headers=self._headers(api_key),
                    params={
                        "start_time": int(start.timestamp()),
                        "end_time": int(now.timestamp()),
                    },
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                results = []
                for bucket in data.get("data", []):
                    for result in bucket.get("results", []):
                        results.append(UsageData(
                            model=result.get("object", "unknown"),
                            input_tokens=result.get("input_tokens", 0),
                            output_tokens=result.get("output_tokens", 0),
                            total_tokens=result.get("input_tokens", 0) + result.get("output_tokens", 0),
                            period_start=start,
                            period_end=now,
                        ))
                return results
            except (httpx.RequestError, KeyError, ValueError):
                return []

    async def get_costs(self, api_key: str, **kwargs) -> CostData | None:
        """Fetch costs from OpenAI billing endpoint."""
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.ADMIN_API_BASE}/organization/costs",
                    headers=self._headers(api_key),
                    params={
                        "start_time": int(start.timestamp()),
                        "end_time": int(now.timestamp()),
                    },
                )
                if resp.status_code != 200:
                    return None

                data = resp.json()
                total = sum(
                    r.get("amount", {}).get("value", 0)
                    for bucket in data.get("data", [])
                    for r in bucket.get("results", [])
                )
                return CostData(
                    total_usd=total / 100,  # cents to dollars
                    period_start=start,
                    period_end=now,
                )
            except (httpx.RequestError, KeyError, ValueError):
                return None
