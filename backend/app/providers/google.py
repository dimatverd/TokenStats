"""Google Vertex AI provider — Service Account JSON validation and data fetching."""

import json
from datetime import UTC, datetime

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from app.providers.base import (
    BaseProvider,
    CostData,
    KeyValidationResult,
    RateLimitInfo,
    UsageData,
)

_READONLY_SCOPES = [
    "https://www.googleapis.com/auth/monitoring.read",
    "https://www.googleapis.com/auth/cloud-platform.read-only",
]


def _parse_sa(api_key: str) -> tuple[dict | None, str | None]:
    """Parse and validate SA JSON structure. Returns (sa_dict, error)."""
    try:
        sa = json.loads(api_key)
    except (json.JSONDecodeError, TypeError):
        return None, "Key must be a valid Service Account JSON"

    required_fields = ["type", "project_id", "private_key", "client_email"]
    missing = [f for f in required_fields if f not in sa]
    if missing:
        return None, f"Service Account JSON missing fields: {', '.join(missing)}"

    if sa.get("type") != "service_account":
        return None, "JSON type must be 'service_account'"

    if not sa.get("project_id"):
        return None, "project_id is required in Service Account JSON"

    return sa, None


def _get_credentials(sa: dict) -> service_account.Credentials:
    """Create and refresh credentials from SA dict."""
    creds = service_account.Credentials.from_service_account_info(sa, scopes=_READONLY_SCOPES)
    creds.refresh(GoogleAuthRequest())
    return creds


class GoogleVertexProvider(BaseProvider):
    provider_type = "google"
    display_name = "Vertex AI"

    async def validate_key(self, api_key: str, **kwargs) -> KeyValidationResult:
        sa, error = _parse_sa(api_key)
        if error:
            return KeyValidationResult(False, False, error)

        try:
            creds = _get_credentials(sa)
        except Exception as e:
            return KeyValidationResult(False, False, f"Service Account authentication failed: {e}")

        token = creds.token
        project_id = sa["project_id"]

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"pageSize": 1},
                )
                if resp.status_code == 403:
                    return KeyValidationResult(False, False, "Insufficient permissions: requires monitoring.viewer role")
                if resp.status_code == 401:
                    return KeyValidationResult(False, False, "Service Account authentication failed")
            except httpx.RequestError as e:
                return KeyValidationResult(False, False, f"Connection error: {e}")

            try:
                resp = await client.post(
                    f"https://{project_id}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/us-central1/endpoints",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"displayName": "tokenstats-readonly-test"},
                )
                if resp.status_code in (200, 201):
                    return KeyValidationResult(False, False, "Key is not read-only: write request succeeded. SA must have only viewer roles.")
            except httpx.RequestError:
                pass

        return KeyValidationResult(True, True)

    async def get_rate_limits(self, api_key: str, **kwargs) -> list[RateLimitInfo]:
        """Fetch Vertex AI rate limits via monitoring API quotas."""
        sa, error = _parse_sa(api_key)
        if error:
            return []

        try:
            creds = _get_credentials(sa)
        except Exception:
            return []

        project_id = sa["project_id"]
        now = datetime.now(UTC)

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                # Query Vertex AI quota metrics
                end = now.isoformat() + "Z"
                start = (now.replace(minute=now.minute - 1 if now.minute > 0 else 59)).isoformat() + "Z"

                resp = await client.post(
                    f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries:query",
                    headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
                    json={
                        "query": (
                            'fetch consumer_quota::serviceruntime.googleapis.com/quota/rate/net_usage'
                            f' | filter resource.service == "aiplatform.googleapis.com"'
                            f' | within 1m'
                        ),
                    },
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                results = []
                for ts in data.get("timeSeriesData", []):
                    labels = {ld.get("key"): ld.get("value") for ld in ts.get("labelValues", [])}
                    model = labels.get("quota_metric", "vertex-ai")
                    points = ts.get("pointData", [])
                    used = int(points[0]["values"][0].get("int64Value", 0)) if points else 0
                    results.append(RateLimitInfo(
                        model=model,
                        rpm_limit=60,  # default quota
                        rpm_used=used,
                        tpm_limit=0,
                        tpm_used=0,
                    ))
                return results
            except (httpx.RequestError, KeyError, ValueError, IndexError):
                return []

    async def get_usage(self, api_key: str, **kwargs) -> list[UsageData]:
        """Fetch Vertex AI usage from BigQuery billing export or monitoring."""
        # Vertex AI doesn't have a direct usage API like OpenAI
        # Usage data comes from Cloud Monitoring or BigQuery billing export
        return []

    async def get_costs(self, api_key: str, **kwargs) -> CostData | None:
        """Fetch billing data from Cloud Billing API."""
        sa, error = _parse_sa(api_key)
        if error:
            return None

        try:
            creds = _get_credentials(sa)
        except Exception:
            return None

        # Cloud Billing API requires billing account access
        # For now return None — requires billing.viewer role setup
        return None
