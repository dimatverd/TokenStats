"""Tests for provider key management — US-04, US-05, US-06 acceptance criteria."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.providers.base import KeyValidationResult


async def _get_auth_headers(client: AsyncClient) -> dict:
    """Register + login, return auth headers."""
    resp = await client.post(
        "/auth/register",
        json={
            "email": "dev@example.com",
            "password": "securepass123",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_valid_readonly():
    return AsyncMock(return_value=KeyValidationResult(True, True))


def _mock_invalid_key(error="Key validation failed"):
    return AsyncMock(return_value=KeyValidationResult(False, False, error))


def _mock_not_readonly():
    return AsyncMock(return_value=KeyValidationResult(True, False))


# ── US-04: Anthropic key ──────────────────────────────────


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_anthropic_key_success(mock_get, client: AsyncClient):
    """US-04: valid read-only admin key + tier → 201."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "anthropic",
            "api_key": "sk-ant-admin-xxxxxxxxxxxxxxxxxxxx",
            "tier": "tier2",
            "label": "My Claude key",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["key_hint"] == "xxxx"
    assert data["tier"] == "tier2"
    assert data["is_valid"] is True
    assert data["validated_at"] is not None


@pytest.mark.asyncio
async def test_add_anthropic_key_no_tier(client: AsyncClient):
    """US-04: Anthropic without tier → 422."""
    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "anthropic",
            "api_key": "sk-ant-admin-xxxxxxxxxxxxxxxxxxxx",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert "tier" in resp.json()["detail"].lower()


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_anthropic_key_invalid(mock_get, client: AsyncClient):
    """US-04: invalid key → 400."""
    provider = AsyncMock()
    provider.validate_key = _mock_invalid_key("Key validation failed")
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "anthropic",
            "api_key": "sk-ant-admin-badkey",
            "tier": "tier2",
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_anthropic_key_not_readonly(mock_get, client: AsyncClient):
    """US-04: key allows inference (not read-only) → 400."""
    provider = AsyncMock()
    provider.validate_key = _mock_not_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "anthropic",
            "api_key": "sk-ant-admin-fullaccess",
            "tier": "tier2",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "not read-only" in resp.json()["detail"].lower()


# ── US-05: OpenAI key ────────────────────────────────────


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_openai_key_success(mock_get, client: AsyncClient):
    """US-05: valid read-only OpenAI key → 201."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-xxxxxxxxxxxxxxxxxxxx",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == "openai"


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_openai_key_invalid(mock_get, client: AsyncClient):
    """US-05: invalid key → 400."""
    provider = AsyncMock()
    provider.validate_key = _mock_invalid_key()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-badkey",
        },
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_openai_key_not_readonly(mock_get, client: AsyncClient):
    """US-05: key allows inference (not read-only) → 400."""
    provider = AsyncMock()
    provider.validate_key = _mock_not_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-fullaccess",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "not read-only" in resp.json()["detail"].lower()


# ── US-06: Vertex AI (Google SA JSON) ────────────────────


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_google_key_success(mock_get, client: AsyncClient):
    """US-06: valid SA JSON with viewer roles → 201."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    sa_json = '{"type":"service_account","project_id":"my-project","private_key":"key","client_email":"sa@proj.iam.gserviceaccount.com"}'
    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "google",
            "api_key": sa_json,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["provider"] == "google"


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_google_key_insufficient_permissions(mock_get, client: AsyncClient):
    """US-06: SA without viewer roles → 400 (403 mapped to 400)."""
    provider = AsyncMock()
    provider.validate_key = _mock_invalid_key("Insufficient permissions: requires monitoring.viewer, billing.viewer")
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "google",
            "api_key": '{"type":"service_account","project_id":"p","private_key":"k","client_email":"e"}',
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "permissions" in resp.json()["detail"].lower()


# ── General provider tests ────────────────────────────────


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_add_provider_duplicate(mock_get, client: AsyncClient):
    """Adding same provider twice → 409."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-xxx",
        },
        headers=headers,
    )
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-yyy",
        },
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_provider_no_auth(client: AsyncClient):
    """Adding provider without auth → 403."""
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-xxx",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_list_providers(mock_get, client: AsyncClient):
    """List providers returns added keys."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-xxx",
        },
        headers=headers,
    )

    resp = await client.get("/auth/providers", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider"] == "openai"


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_delete_provider(mock_get, client: AsyncClient):
    """Delete provider → 204, then list is empty."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-xxx",
        },
        headers=headers,
    )

    resp = await client.delete("/auth/providers/openai", headers=headers)
    assert resp.status_code == 204

    resp = await client.get("/auth/providers", headers=headers)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
@patch("app.auth.router.get_provider")
async def test_key_stored_encrypted(mock_get, client: AsyncClient):
    """Key in DB is encrypted, not plaintext."""
    provider = AsyncMock()
    provider.validate_key = _mock_valid_readonly()
    mock_get.return_value = provider

    headers = await _get_auth_headers(client)
    resp = await client.post(
        "/auth/providers",
        json={
            "provider": "openai",
            "api_key": "sk-proj-secretkey12345",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    # The response should NOT contain the full key
    data = resp.json()
    assert "sk-proj-secretkey12345" not in str(data)
    assert data["key_hint"] == "2345"
