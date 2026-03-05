"""Tests for device registration endpoints."""

import pytest
from httpx import AsyncClient


async def _register_and_get_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/auth/register",
        json={"email": "device@example.com", "password": "securepass123"},
    )
    return resp.json()["access_token"]


async def _auth_headers(client: AsyncClient) -> dict:
    token = await _register_and_get_token(client)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_register_device(client: AsyncClient):
    headers = await _auth_headers(client)
    resp = await client.post(
        "/api/v1/devices/register",
        json={"device_token": "abc123token", "platform": "ios"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["device_token"] == "abc123token"
    assert data["platform"] == "ios"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_device_upsert(client: AsyncClient):
    headers = await _auth_headers(client)
    # Register with ios
    resp1 = await client.post(
        "/api/v1/devices/register",
        json={"device_token": "abc123token", "platform": "ios"},
        headers=headers,
    )
    assert resp1.status_code == 201

    # Re-register same token with android (upsert)
    resp2 = await client.post(
        "/api/v1/devices/register",
        json={"device_token": "abc123token", "platform": "android"},
        headers=headers,
    )
    assert resp2.status_code == 201
    data = resp2.json()
    assert data["platform"] == "android"
    assert data["id"] == resp1.json()["id"]


@pytest.mark.asyncio
async def test_unregister_device(client: AsyncClient):
    headers = await _auth_headers(client)
    # Register first
    await client.post(
        "/api/v1/devices/register",
        json={"device_token": "del-token", "platform": "watchos"},
        headers=headers,
    )
    # Delete
    resp = await client.delete("/api/v1/devices/del-token", headers=headers)
    assert resp.status_code == 204

    # Delete again should 404
    resp = await client.delete("/api/v1/devices/del-token", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_register_device_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/devices/register",
        json={"device_token": "abc123token", "platform": "ios"},
    )
    assert resp.status_code == 403
