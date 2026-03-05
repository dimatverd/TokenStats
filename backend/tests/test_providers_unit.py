"""Unit tests for provider classes — UP-01 through UP-16.

Tests validate_key, get_rate_limits, get_usage, get_costs for each provider,
mocking all HTTP calls and external auth (Google SA).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers.anthropic import TIER_LIMITS, AnthropicProvider
from app.providers.base import CostData, RateLimitInfo, UsageData
from app.providers.google import GoogleVertexProvider, _parse_sa
from app.providers.openai import OpenAIProvider

# ── Helpers ──────────────────────────────────────────────────────────────────


def _resp(status_code: int = 200, json_data: dict | None = None, headers: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    r.headers = headers or {}
    return r


def _http_client(get_resp=None, post_resp=None) -> MagicMock:
    """Mock async context manager for httpx.AsyncClient."""
    m = AsyncMock()
    m.__aenter__ = AsyncMock(return_value=m)
    m.__aexit__ = AsyncMock(return_value=None)
    if get_resp is not None:
        m.get.return_value = get_resp
    if post_resp is not None:
        m.post.return_value = post_resp
    return m


_ANTHROPIC = AnthropicProvider()
_OPENAI = OpenAIProvider()
_GOOGLE = GoogleVertexProvider()

_VALID_SA = '{"type":"service_account","project_id":"my-proj","private_key":"-----BEGIN RSA PRIVATE KEY-----\\nfake\\n-----END RSA PRIVATE KEY-----\\n","client_email":"sa@my-proj.iam.gserviceaccount.com"}'


# ══════════════════════════════════════════════════════════════════════════════
# RateLimitInfo — base class property tests
# ══════════════════════════════════════════════════════════════════════════════


def test_rate_limit_info_rpm_pct():
    r = RateLimitInfo(model="m", rpm_limit=1000, rpm_used=250, tpm_limit=50000, tpm_used=0)
    assert r.rpm_pct == 25.0


def test_rate_limit_info_tpm_pct():
    r = RateLimitInfo(model="m", rpm_limit=1000, rpm_used=0, tpm_limit=80000, tpm_used=40000)
    assert r.tpm_pct == 50.0


def test_rate_limit_info_zero_rpm_limit():
    r = RateLimitInfo(model="m", rpm_limit=0, rpm_used=0, tpm_limit=0, tpm_used=0)
    assert r.rpm_pct == 0.0
    assert r.tpm_pct == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# AnthropicProvider — validate_key
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anthropic_validate_key_missing_tier():
    """UP-04 variant: no tier kwarg → invalid, no HTTP call."""
    result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx")
    assert result.is_valid is False
    assert "tier" in result.error.lower()


@pytest.mark.asyncio
async def test_anthropic_validate_key_wrong_format():
    """UP-04 variant: key doesn't start with sk-ant-admin → invalid."""
    result = await _ANTHROPIC.validate_key("sk-ant-regular-xxx", tier="tier2")
    assert result.is_valid is False
    assert "admin" in result.error.lower()


@pytest.mark.asyncio
async def test_anthropic_validate_key_401():
    """UP-04: 401 from org endpoint → invalid."""
    client = _http_client(get_resp=_resp(401), post_resp=_resp(403))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx", tier="tier2")
    assert result.is_valid is False
    assert "unauthorized" in result.error.lower()


@pytest.mark.asyncio
async def test_anthropic_validate_key_403():
    """UP-04: 403 from org endpoint → invalid."""
    client = _http_client(get_resp=_resp(403), post_resp=_resp(403))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx", tier="tier2")
    assert result.is_valid is False
    assert "forbidden" in result.error.lower()


@pytest.mark.asyncio
async def test_anthropic_validate_key_connection_error():
    """UP-06: network error on org request → invalid."""
    client = _http_client(post_resp=_resp(403))
    client.get.side_effect = httpx.RequestError("timeout")
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx", tier="tier2")
    assert result.is_valid is False
    assert "connection" in result.error.lower()


@pytest.mark.asyncio
async def test_anthropic_validate_key_success():
    """UP-02 variant: org 200, inference 403 (read-only) → valid."""
    client = _http_client(get_resp=_resp(200), post_resp=_resp(403))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx", tier="tier2")
    assert result.is_valid is True
    assert result.is_read_only is True


@pytest.mark.asyncio
async def test_anthropic_validate_key_not_readonly():
    """SEC-02: org 200, inference 200 (can run inference) → not read-only."""
    client = _http_client(get_resp=_resp(200), post_resp=_resp(200))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        result = await _ANTHROPIC.validate_key("sk-ant-admin-xxx", tier="tier2")
    assert result.is_valid is False
    assert "not read-only" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# AnthropicProvider — get_rate_limits
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anthropic_get_rate_limits_success():
    """UP-02: org 200 → returns tier-based RateLimitInfo for all models."""
    client = _http_client(get_resp=_resp(200))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        limits = await _ANTHROPIC.get_rate_limits("sk-ant-admin-xxx", tier="tier2")

    assert len(limits) == 3
    expected = TIER_LIMITS["tier2"]
    for rl in limits:
        assert isinstance(rl, RateLimitInfo)
        assert rl.rpm_limit == expected["rpm"]
        assert rl.tpm_limit == expected["tpm"]
        assert rl.rpm_used == 0
        assert rl.tpm_used == 0


@pytest.mark.asyncio
async def test_anthropic_get_rate_limits_api_error():
    """UP-04: org non-200 → empty list."""
    client = _http_client(get_resp=_resp(401))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        limits = await _ANTHROPIC.get_rate_limits("sk-ant-admin-xxx", tier="tier2")
    assert limits == []


@pytest.mark.asyncio
async def test_anthropic_get_rate_limits_connection_error():
    """UP-06: network error → empty list."""
    client = _http_client()
    client.get.side_effect = httpx.RequestError("timeout")
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        limits = await _ANTHROPIC.get_rate_limits("sk-ant-admin-xxx", tier="tier2")
    assert limits == []


@pytest.mark.asyncio
async def test_anthropic_get_rate_limits_default_tier():
    """No tier kwarg → falls back to tier1 limits."""
    client = _http_client(get_resp=_resp(200))
    with patch("app.providers.anthropic.httpx.AsyncClient", return_value=client):
        limits = await _ANTHROPIC.get_rate_limits("sk-ant-admin-xxx")

    expected = TIER_LIMITS["tier1"]
    assert limits[0].rpm_limit == expected["rpm"]


# ══════════════════════════════════════════════════════════════════════════════
# AnthropicProvider — get_usage / get_costs
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_anthropic_get_usage_empty():
    """UP-15: get_usage always returns [] (API not yet available)."""
    result = await _ANTHROPIC.get_usage("sk-ant-admin-xxx", tier="tier2")
    assert result == []


@pytest.mark.asyncio
async def test_anthropic_get_costs_none():
    """UP-03: get_costs always returns None (API not yet available)."""
    result = await _ANTHROPIC.get_costs("sk-ant-admin-xxx", tier="tier2")
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# OpenAIProvider — validate_key
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_openai_validate_key_wrong_format():
    """Key not starting with sk- → invalid, no HTTP call."""
    result = await _OPENAI.validate_key("bad-key-format")
    assert result.is_valid is False
    assert "sk-" in result.error


@pytest.mark.asyncio
async def test_openai_validate_key_401():
    """UP-10: 401 from /models → invalid."""
    client = _http_client(get_resp=_resp(401), post_resp=_resp(403))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.validate_key("sk-proj-testkey")
    assert result.is_valid is False
    assert "unauthorized" in result.error.lower()


@pytest.mark.asyncio
async def test_openai_validate_key_403():
    """403 from /models → invalid."""
    client = _http_client(get_resp=_resp(403), post_resp=_resp(403))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.validate_key("sk-proj-testkey")
    assert result.is_valid is False
    assert "forbidden" in result.error.lower()


@pytest.mark.asyncio
async def test_openai_validate_key_connection_error():
    """UP-06: network error → invalid."""
    client = _http_client(post_resp=_resp(403))
    client.get.side_effect = httpx.RequestError("timeout")
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.validate_key("sk-proj-testkey")
    assert result.is_valid is False
    assert "connection" in result.error.lower()


@pytest.mark.asyncio
async def test_openai_validate_key_success():
    """UP-07: /models 200, completions 403 → valid read-only."""
    client = _http_client(get_resp=_resp(200), post_resp=_resp(403))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.validate_key("sk-proj-testkey")
    assert result.is_valid is True
    assert result.is_read_only is True


@pytest.mark.asyncio
async def test_openai_validate_key_not_readonly():
    """SEC-04: /models 200, completions 200 → not read-only."""
    client = _http_client(get_resp=_resp(200), post_resp=_resp(200))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.validate_key("sk-proj-testkey")
    assert result.is_valid is False
    assert "not read-only" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# OpenAIProvider — get_rate_limits
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_openai_get_rate_limits_success():
    """UP-08: parses x-ratelimit-* headers correctly."""
    headers = {
        "x-ratelimit-limit-requests": "500",
        "x-ratelimit-limit-tokens": "90000",
        "x-ratelimit-remaining-requests": "455",
        "x-ratelimit-remaining-tokens": "80000",
    }
    client = _http_client(get_resp=_resp(200, headers=headers))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        limits = await _OPENAI.get_rate_limits("sk-proj-testkey")

    assert len(limits) == 1
    rl = limits[0]
    assert rl.rpm_limit == 500
    assert rl.rpm_used == 45  # 500 - 455
    assert rl.tpm_limit == 90000
    assert rl.tpm_used == 10000  # 90000 - 80000


@pytest.mark.asyncio
async def test_openai_get_rate_limits_no_header():
    """UP-15: /models 200 but no rate-limit headers (rpm_limit=0) → empty list."""
    client = _http_client(get_resp=_resp(200))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        limits = await _OPENAI.get_rate_limits("sk-proj-testkey")
    assert limits == []


@pytest.mark.asyncio
async def test_openai_get_rate_limits_api_error():
    """UP-10: non-200 response → empty list."""
    client = _http_client(get_resp=_resp(401))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        limits = await _OPENAI.get_rate_limits("sk-proj-testkey")
    assert limits == []


# ══════════════════════════════════════════════════════════════════════════════
# OpenAIProvider — get_usage
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_openai_get_usage_success():
    """UP-07: parses usage buckets into UsageData list."""
    usage_json = {
        "data": [
            {
                "results": [
                    {
                        "object": "gpt-4o",
                        "input_tokens": 1000,
                        "output_tokens": 500,
                    }
                ]
            }
        ]
    }
    client = _http_client(get_resp=_resp(200, json_data=usage_json))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        results = await _OPENAI.get_usage("sk-proj-testkey")

    assert len(results) == 1
    ud = results[0]
    assert isinstance(ud, UsageData)
    assert ud.model == "gpt-4o"
    assert ud.input_tokens == 1000
    assert ud.output_tokens == 500
    assert ud.total_tokens == 1500


@pytest.mark.asyncio
async def test_openai_get_usage_empty_data():
    """UP-15: 200 with empty data list → empty list, no exception."""
    client = _http_client(get_resp=_resp(200, json_data={"data": []}))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        results = await _OPENAI.get_usage("sk-proj-testkey")
    assert results == []


@pytest.mark.asyncio
async def test_openai_get_usage_api_error():
    """UP-10: non-200 → empty list."""
    client = _http_client(get_resp=_resp(403))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        results = await _OPENAI.get_usage("sk-proj-testkey")
    assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# OpenAIProvider — get_costs
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_openai_get_costs_success():
    """UP-09: parses costs and converts cents → dollars."""
    costs_json = {
        "data": [
            {"results": [{"amount": {"value": 1250}}]},  # $12.50
            {"results": [{"amount": {"value": 750}}]},  # $7.50
        ]
    }
    client = _http_client(get_resp=_resp(200, json_data=costs_json))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.get_costs("sk-proj-testkey")

    assert isinstance(result, CostData)
    assert abs(result.total_usd - 20.0) < 0.001  # (1250+750)/100


@pytest.mark.asyncio
async def test_openai_get_costs_api_error():
    """Non-200 → None."""
    client = _http_client(get_resp=_resp(403))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.get_costs("sk-proj-testkey")
    assert result is None


@pytest.mark.asyncio
async def test_openai_get_costs_empty_data():
    """UP-15: 200 with no data → CostData with total_usd=0."""
    client = _http_client(get_resp=_resp(200, json_data={"data": []}))
    with patch("app.providers.openai.httpx.AsyncClient", return_value=client):
        result = await _OPENAI.get_costs("sk-proj-testkey")
    assert isinstance(result, CostData)
    assert result.total_usd == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Google — _parse_sa helper
# ══════════════════════════════════════════════════════════════════════════════


def test_parse_sa_invalid_json():
    """UP-14: non-JSON string → error."""
    sa, err = _parse_sa("not-json")
    assert sa is None
    assert "valid Service Account JSON" in err


def test_parse_sa_missing_fields():
    """UP-14: JSON missing required fields → error."""
    sa, err = _parse_sa('{"type":"service_account"}')
    assert sa is None
    assert "missing" in err.lower()


def test_parse_sa_wrong_type():
    """UP-14: type != service_account → error."""
    sa, err = _parse_sa('{"type":"authorized_user","project_id":"p","private_key":"k","client_email":"e"}')
    assert sa is None
    assert "service_account" in err


def test_parse_sa_empty_project_id():
    """UP-14: empty project_id → error."""
    sa, err = _parse_sa('{"type":"service_account","project_id":"","private_key":"k","client_email":"e"}')
    assert sa is None
    assert "project_id" in err


def test_parse_sa_valid():
    """Valid SA JSON → returns dict, no error."""
    sa, err = _parse_sa(_VALID_SA)
    assert err is None
    assert sa["project_id"] == "my-proj"
    assert sa["type"] == "service_account"


# ══════════════════════════════════════════════════════════════════════════════
# GoogleVertexProvider — validate_key
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_google_validate_key_invalid_json():
    """UP-14: invalid SA JSON → invalid result."""
    result = await _GOOGLE.validate_key("not-a-json")
    assert result.is_valid is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_google_validate_key_credentials_failure():
    """UP-14: SA JSON valid but credentials refresh fails → invalid."""
    with patch("app.providers.google._get_credentials", side_effect=Exception("auth failed")):
        result = await _GOOGLE.validate_key(_VALID_SA)
    assert result.is_valid is False
    assert "authentication failed" in result.error.lower()


@pytest.mark.asyncio
async def test_google_validate_key_403_monitoring():
    """UP-14: monitoring 403 → insufficient permissions."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(get_resp=_resp(403), post_resp=_resp(403))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        result = await _GOOGLE.validate_key(_VALID_SA)

    assert result.is_valid is False
    assert "permissions" in result.error.lower()


@pytest.mark.asyncio
async def test_google_validate_key_401_monitoring():
    """UP-14: monitoring 401 → auth failed."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(get_resp=_resp(401), post_resp=_resp(403))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        result = await _GOOGLE.validate_key(_VALID_SA)

    assert result.is_valid is False
    assert "authentication" in result.error.lower()


@pytest.mark.asyncio
async def test_google_validate_key_connection_error():
    """UP-06: network error → invalid."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(post_resp=_resp(403))
    client.get.side_effect = httpx.RequestError("timeout")
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        result = await _GOOGLE.validate_key(_VALID_SA)

    assert result.is_valid is False
    assert "connection" in result.error.lower()


@pytest.mark.asyncio
async def test_google_validate_key_success():
    """UP-11: monitoring 200, write endpoint fails (non-200/201) → valid."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(get_resp=_resp(200), post_resp=_resp(403))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        result = await _GOOGLE.validate_key(_VALID_SA)

    assert result.is_valid is True
    assert result.is_read_only is True


@pytest.mark.asyncio
async def test_google_validate_key_not_readonly():
    """SEC-06: monitoring 200, write endpoint 200 → not read-only."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(get_resp=_resp(200), post_resp=_resp(200))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        result = await _GOOGLE.validate_key(_VALID_SA)

    assert result.is_valid is False
    assert "not read-only" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# GoogleVertexProvider — get_rate_limits
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_google_get_rate_limits_invalid_sa():
    """UP-14: invalid SA → empty list."""
    limits = await _GOOGLE.get_rate_limits("not-json")
    assert limits == []


@pytest.mark.asyncio
async def test_google_get_rate_limits_creds_failure():
    """UP-14: creds refresh fails → empty list."""
    with patch("app.providers.google._get_credentials", side_effect=Exception("auth failed")):
        limits = await _GOOGLE.get_rate_limits(_VALID_SA)
    assert limits == []


@pytest.mark.asyncio
async def test_google_get_rate_limits_api_error():
    """UP-12: monitoring non-200 → empty list."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(post_resp=_resp(403))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        limits = await _GOOGLE.get_rate_limits(_VALID_SA)
    assert limits == []


@pytest.mark.asyncio
async def test_google_get_rate_limits_success():
    """UP-12: parses monitoring timeSeries response into RateLimitInfo."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    monitoring_json = {
        "timeSeriesData": [
            {
                "labelValues": [
                    {"key": "quota_metric", "value": "aiplatform.googleapis.com/online_prediction_requests"}
                ],
                "pointData": [{"values": [{"int64Value": "42"}]}],
            }
        ]
    }
    client = _http_client(post_resp=_resp(200, json_data=monitoring_json))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        limits = await _GOOGLE.get_rate_limits(_VALID_SA)

    assert len(limits) == 1
    rl = limits[0]
    assert isinstance(rl, RateLimitInfo)
    assert rl.rpm_used == 42
    assert "aiplatform" in rl.model


@pytest.mark.asyncio
async def test_google_get_rate_limits_empty_timeseries():
    """UP-15: 200 with no timeSeriesData → empty list."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    client = _http_client(post_resp=_resp(200, json_data={"timeSeriesData": []}))
    with (
        patch("app.providers.google._get_credentials", return_value=mock_creds),
        patch("app.providers.google.httpx.AsyncClient", return_value=client),
    ):
        limits = await _GOOGLE.get_rate_limits(_VALID_SA)
    assert limits == []


# ══════════════════════════════════════════════════════════════════════════════
# GoogleVertexProvider — get_usage / get_costs
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_google_get_usage_empty():
    """UP-15: get_usage always returns [] (no native token metrics)."""
    result = await _GOOGLE.get_usage(_VALID_SA)
    assert result == []


@pytest.mark.asyncio
async def test_google_get_costs_invalid_sa():
    """UP-13: invalid SA → None."""
    result = await _GOOGLE.get_costs("not-json")
    assert result is None


@pytest.mark.asyncio
async def test_google_get_costs_creds_failure():
    """UP-13: creds failure → None."""
    with patch("app.providers.google._get_credentials", side_effect=Exception("auth failed")):
        result = await _GOOGLE.get_costs(_VALID_SA)
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Provider metadata
# ══════════════════════════════════════════════════════════════════════════════


def test_provider_type_values():
    assert _ANTHROPIC.provider_type == "anthropic"
    assert _OPENAI.provider_type == "openai"
    assert _GOOGLE.provider_type == "google"


def test_provider_display_names():
    assert "Claude" in _ANTHROPIC.display_name or "Anthropic" in _ANTHROPIC.display_name
    assert "OpenAI" in _OPENAI.display_name
    assert "Vertex" in _GOOGLE.display_name or "AI" in _GOOGLE.display_name
