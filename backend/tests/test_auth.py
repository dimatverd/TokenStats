"""Tests for auth endpoints — US-01 & US-02 acceptance criteria."""

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """US-01: valid email + password >= 8 chars → 201 with JWT tokens."""
    resp = await client.post("/auth/register", json={
        "email": "dev@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "dev@example.com"
    assert "id" in data
    assert "created_at" in data
    # AC: registration must return JWT tokens
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """US-01: duplicate email → 409 Conflict."""
    payload = {"email": "dev@example.com", "password": "securepass123"}
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_email_case_insensitive(client: AsyncClient):
    """US-01: duplicate email with different casing → 409."""
    await client.post("/auth/register", json={
        "email": "Dev@Example.com",
        "password": "securepass123",
    })
    resp = await client.post("/auth/register", json={
        "email": "dev@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """US-01: invalid email → 422."""
    resp = await client.post("/auth/register", json={
        "email": "not-an-email",
        "password": "securepass123",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """US-01: password < 8 chars → 422."""
    resp = await client.post("/auth/register", json={
        "email": "dev@example.com",
        "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_empty_body(client: AsyncClient):
    """US-01: empty body → 422."""
    resp = await client.post("/auth/register", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """US-02: correct credentials → 200 with tokens."""
    await client.post("/auth/register", json={
        "email": "dev@example.com",
        "password": "securepass123",
    })
    resp = await client.post("/auth/login", json={
        "email": "dev@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """US-02: wrong password → 401."""
    await client.post("/auth/register", json={
        "email": "dev@example.com",
        "password": "securepass123",
    })
    resp = await client.post("/auth/login", json={
        "email": "dev@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """US-02: non-existent user → 401."""
    resp = await client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """Smoke test: health endpoint works."""
    resp = await client.get("/health")
    assert resp.status_code == 200


# ── US-02: Login and JWT ──────────────────────────────────


async def _register_and_login(client: AsyncClient) -> dict:
    """Helper: register + login, return token response."""
    await client.post("/auth/register", json={
        "email": "dev@example.com", "password": "securepass123",
    })
    resp = await client.post("/auth/login", json={
        "email": "dev@example.com", "password": "securepass123",
    })
    return resp.json()


@pytest.mark.asyncio
async def test_access_token_on_protected_endpoint(client: AsyncClient):
    """US-02: valid access token → can access protected endpoint."""
    tokens = await _register_and_login(client)
    resp = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}"
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == "dev@example.com"


@pytest.mark.asyncio
async def test_no_token_on_protected_endpoint(client: AsyncClient):
    """US-02: no token on protected endpoint → 401."""
    resp = await client.get("/auth/me")
    assert resp.status_code == 403  # HTTPBearer returns 403 when no credentials


@pytest.mark.asyncio
async def test_invalid_token_on_protected_endpoint(client: AsyncClient):
    """US-02: garbage token → 401."""
    resp = await client.get("/auth/me", headers={
        "Authorization": "Bearer garbage.token.here"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient):
    """US-02: expired access token → 401."""
    import time
    from datetime import datetime, timedelta, timezone
    # Create a token that expired 1 hour ago
    payload = {
        "sub": "1",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    resp = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {expired_token}"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rejected_as_access(client: AsyncClient):
    """US-02: refresh token used as access → 401."""
    tokens = await _register_and_login(client)
    resp = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {tokens['refresh_token']}"
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient):
    """US-02: refresh token → new access + refresh tokens."""
    tokens = await _register_and_login(client)
    resp = await client.post("/auth/token", json={
        "refresh_token": tokens["refresh_token"],
    })
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    # New access token should work
    resp2 = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {new_tokens['access_token']}"
    })
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client: AsyncClient):
    """US-02: access token used for refresh → 401."""
    tokens = await _register_and_login(client)
    resp = await client.post("/auth/token", json={
        "refresh_token": tokens["access_token"],
    })
    assert resp.status_code == 401
