"""Google Vertex AI provider — Service Account JSON validation and data fetching."""

import json
from datetime import UTC, datetime, timedelta

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

# Published Vertex AI pricing per 1M tokens (USD) as of 2025-Q4.
# Source: https://cloud.google.com/vertex-ai/generative-ai/pricing
_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-002": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-pro-002": {"input": 1.25, "output": 5.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
}
_DEFAULT_PRICING = {"input": 1.25, "output": 5.00}  # conservative fallback

# Vertex AI GenAI metrics available in Cloud Monitoring.
_PREDICTION_INPUT_METRIC = "aiplatform.googleapis.com/prediction/online/input_token_count"
_PREDICTION_OUTPUT_METRIC = "aiplatform.googleapis.com/prediction/online/output_token_count"
_PREDICTION_COUNT_METRIC = "aiplatform.googleapis.com/prediction/online/prediction_count"

MONITORING_BASE = "https://monitoring.googleapis.com/v3"


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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _iso(dt: datetime) -> str:
    """Format datetime to ISO 8601 with Z suffix for the Monitoring API."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD from token counts and published pricing."""
    pricing = _PRICING_PER_1M.get(model, _DEFAULT_PRICING)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


async def _query_monitoring_metric(
    client: httpx.AsyncClient,
    project_id: str,
    token: str,
    metric_type: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Query Cloud Monitoring for a single metric across all Vertex models.

    Returns a list of dicts: [{"model": str, "value": int}, ...].
    """
    # Use the timeSeries.list endpoint with an aggregation to sum values
    # grouped by the model_id label.
    metric_filter = f'metric.type = "{metric_type}" AND resource.type = "aiplatform.googleapis.com/Endpoint"'
    params: dict[str, str] = {
        "filter": metric_filter,
        "interval.startTime": _iso(start),
        "interval.endTime": _iso(end),
        # Sum across all time-series points within the interval, grouped by model.
        "aggregation.alignmentPeriod": f"{int((end - start).total_seconds())}s",
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
        "aggregation.groupByFields": "metric.labels.model_id",
    }
    resp = await client.get(
        f"{MONITORING_BASE}/projects/{project_id}/timeSeries",
        headers=_auth_headers(token),
        params=params,
    )
    if resp.status_code != 200:
        return []

    data = resp.json()
    results: list[dict] = []
    for ts in data.get("timeSeries", []):
        model_id = ts.get("metric", {}).get("labels", {}).get("model_id", "unknown")
        points = ts.get("points", [])
        total = 0
        for pt in points:
            val = pt.get("value", {})
            total += int(val.get("int64Value", val.get("doubleValue", 0)))
        results.append({"model": model_id, "value": total})
    return results


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
                    f"{MONITORING_BASE}/projects/{project_id}/metricDescriptors",
                    headers=_auth_headers(token),
                    params={"pageSize": 1},
                )
                if resp.status_code == 403:
                    return KeyValidationResult(
                        False,
                        False,
                        "Insufficient permissions: requires monitoring.viewer role",
                    )
                if resp.status_code == 401:
                    return KeyValidationResult(False, False, "Service Account authentication failed")
            except httpx.RequestError as e:
                return KeyValidationResult(False, False, f"Connection error: {e}")

            try:
                resp = await client.post(
                    f"https://{project_id}-aiplatform.googleapis.com/v1/"
                    f"projects/{project_id}/locations/us-central1/endpoints",
                    headers={
                        **_auth_headers(token),
                        "Content-Type": "application/json",
                    },
                    json={"displayName": "tokenstats-readonly-test"},
                )
                if resp.status_code in (200, 201):
                    return KeyValidationResult(
                        False,
                        False,
                        "Key is not read-only: write request succeeded. SA must have only viewer roles.",
                    )
            except httpx.RequestError:
                pass

        return KeyValidationResult(True, True)

    async def get_rate_limits(self, api_key: str, **kwargs) -> list[RateLimitInfo]:
        """Fetch Vertex AI rate limits via quota metrics in Cloud Monitoring."""
        sa, error = _parse_sa(api_key)
        if error:
            return []

        try:
            creds = _get_credentials(sa)
        except Exception:
            return []

        project_id = sa["project_id"]

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                # Query Vertex AI quota metrics via MQL.
                resp = await client.post(
                    f"{MONITORING_BASE}/projects/{project_id}/timeSeries:query",
                    headers={
                        **_auth_headers(creds.token),
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": (
                            "fetch consumer_quota"
                            "::serviceruntime.googleapis.com"
                            "/quota/rate/net_usage"
                            " | filter resource.service "
                            '== "aiplatform.googleapis.com"'
                            " | within 1m"
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
                    results.append(
                        RateLimitInfo(
                            model=model,
                            rpm_limit=60,  # default quota
                            rpm_used=used,
                            tpm_limit=0,
                            tpm_used=0,
                        )
                    )
                return results
            except (httpx.RequestError, KeyError, ValueError, IndexError):
                return []

    async def get_usage(self, api_key: str, **kwargs) -> list[UsageData]:
        """Fetch Vertex AI GenAI token usage from Cloud Monitoring.

        Queries the ``prediction/online/input_token_count`` and
        ``prediction/online/output_token_count`` metrics for the current
        billing month, grouped by model_id.
        """
        sa, error = _parse_sa(api_key)
        if error:
            return []

        try:
            creds = _get_credentials(sa)
        except Exception:
            return []

        project_id = sa["project_id"]
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Cloud Monitoring requires at least 60s between start and end.
        if (now - start) < timedelta(seconds=60):
            start = now - timedelta(seconds=120)

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                input_data = await _query_monitoring_metric(
                    client,
                    project_id,
                    creds.token,
                    _PREDICTION_INPUT_METRIC,
                    start,
                    now,
                )
                output_data = await _query_monitoring_metric(
                    client,
                    project_id,
                    creds.token,
                    _PREDICTION_OUTPUT_METRIC,
                    start,
                    now,
                )
            except (httpx.RequestError, KeyError, ValueError):
                return []

        # Merge input and output by model.
        output_map: dict[str, int] = {d["model"]: d["value"] for d in output_data}
        all_models = {d["model"] for d in input_data} | set(output_map.keys())

        input_map: dict[str, int] = {d["model"]: d["value"] for d in input_data}

        results: list[UsageData] = []
        for model in sorted(all_models):
            inp = input_map.get(model, 0)
            out = output_map.get(model, 0)
            results.append(
                UsageData(
                    model=model,
                    input_tokens=inp,
                    output_tokens=out,
                    total_tokens=inp + out,
                    period_start=start,
                    period_end=now,
                )
            )
        return results

    async def get_costs(self, api_key: str, **kwargs) -> CostData | None:
        """Estimate Vertex AI costs from token usage and published pricing.

        Google Cloud does not expose a simple per-project cost API that
        works with a Service Account alone (the Cloud Billing API requires
        billing-account-level access).  Instead we query the same token
        usage metrics used by ``get_usage`` and multiply by published
        per-model pricing to produce an estimate.
        """
        sa, error = _parse_sa(api_key)
        if error:
            return None

        try:
            creds = _get_credentials(sa)
        except Exception:
            return None

        project_id = sa["project_id"]
        now = datetime.now(UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if (now - start) < timedelta(seconds=60):
            start = now - timedelta(seconds=120)

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                input_data = await _query_monitoring_metric(
                    client,
                    project_id,
                    creds.token,
                    _PREDICTION_INPUT_METRIC,
                    start,
                    now,
                )
                output_data = await _query_monitoring_metric(
                    client,
                    project_id,
                    creds.token,
                    _PREDICTION_OUTPUT_METRIC,
                    start,
                    now,
                )
            except (httpx.RequestError, KeyError, ValueError):
                return None

        output_map: dict[str, int] = {d["model"]: d["value"] for d in output_data}
        input_map: dict[str, int] = {d["model"]: d["value"] for d in input_data}
        all_models = set(input_map.keys()) | set(output_map.keys())

        if not all_models:
            return None

        breakdown: list[dict] = []
        total_usd = 0.0
        for model in sorted(all_models):
            inp = input_map.get(model, 0)
            out = output_map.get(model, 0)
            cost = _estimate_cost(model, inp, out)
            total_usd += cost
            breakdown.append(
                {
                    "model": model,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "estimated_cost_usd": round(cost, 6),
                }
            )

        return CostData(
            total_usd=round(total_usd, 6),
            period_start=start,
            period_end=now,
            breakdown=breakdown,
        )
