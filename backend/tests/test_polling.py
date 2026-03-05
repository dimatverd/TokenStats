"""Tests for polling tasks — US-09 acceptance criteria."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache import clear_all, get_cached_rate_limits, get_cached_snapshot
from app.providers.base import RateLimitInfo


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_all()
    yield
    clear_all()


def _make_api_key_record(user_id=1, provider="openai", tier=None):
    """Create a mock APIKeyStore record."""
    record = MagicMock()
    record.user_id = user_id
    record.provider = MagicMock()
    record.provider.value = provider
    record.encrypted_key = "encrypted-key-data"
    record.is_valid = True
    record.tier = tier
    return record


@pytest.mark.asyncio
@patch("app.tasks.polling.async_session")
@patch("app.tasks.polling.decrypt_key", return_value="sk-test-key")
@patch("app.tasks.polling.get_provider")
async def test_poll_all_updates_cache(mock_get_provider, mock_decrypt, mock_session):
    """US-09: polling fetches data and updates cache."""
    from app.tasks.polling import _poll_all

    # Mock provider
    provider = AsyncMock()
    provider.get_rate_limits.return_value = [
        RateLimitInfo(model="gpt-4", rpm_limit=100, rpm_used=42, tpm_limit=50000, tpm_used=10000)
    ]
    provider.get_usage.return_value = []
    provider.get_costs.return_value = None
    mock_get_provider.return_value = provider

    # Mock DB session returning one record
    record = _make_api_key_record()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record]
    mock_db.execute.return_value = mock_result
    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

    await _poll_all()

    # Check cache was updated
    cached = get_cached_rate_limits(1, "openai")
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].rpm_used == 42

    snapshot = get_cached_snapshot(1, "openai")
    assert snapshot is not None
    assert snapshot.is_stale is False


@pytest.mark.asyncio
@patch("app.tasks.polling.async_session")
@patch("app.tasks.polling.decrypt_key", return_value="sk-test-key")
@patch("app.tasks.polling.get_provider")
async def test_poll_marks_stale_on_error(mock_get_provider, mock_decrypt, mock_session):
    """US-09: provider error → data marked as stale, polling continues."""
    from app.tasks.polling import _poll_all

    provider = AsyncMock()
    provider.get_rate_limits.side_effect = Exception("API timeout")
    provider.get_usage.return_value = []
    provider.get_costs.return_value = None
    mock_get_provider.return_value = provider

    record = _make_api_key_record()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record]
    mock_db.execute.return_value = mock_result
    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

    await _poll_all()  # Should not raise

    snapshot = get_cached_snapshot(1, "openai")
    assert snapshot is not None
    assert snapshot.is_stale is True
    assert "API timeout" in snapshot.error


@pytest.mark.asyncio
@patch("app.tasks.polling.async_session")
@patch("app.tasks.polling.decrypt_key", return_value="sk-test-key")
@patch("app.tasks.polling.get_provider")
async def test_poll_multiple_providers(mock_get_provider, mock_decrypt, mock_session):
    """US-09: polls multiple user+provider combinations."""
    from app.tasks.polling import _poll_all

    provider = AsyncMock()
    provider.get_rate_limits.return_value = [
        RateLimitInfo(model="test", rpm_limit=100, rpm_used=0, tpm_limit=50000, tpm_used=0)
    ]
    provider.get_usage.return_value = []
    provider.get_costs.return_value = None
    mock_get_provider.return_value = provider

    records = [
        _make_api_key_record(user_id=1, provider="openai"),
        _make_api_key_record(user_id=1, provider="anthropic", tier="tier2"),
        _make_api_key_record(user_id=2, provider="openai"),
    ]
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_db.execute.return_value = mock_result
    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

    await _poll_all()

    assert get_cached_snapshot(1, "openai") is not None
    assert get_cached_snapshot(1, "anthropic") is not None
    assert get_cached_snapshot(2, "openai") is not None


@pytest.mark.asyncio
@patch("app.tasks.polling.async_session")
@patch("app.tasks.polling.decrypt_key", side_effect=Exception("Decrypt failed"))
@patch("app.tasks.polling.get_provider")
async def test_poll_decrypt_failure_continues(mock_get_provider, mock_decrypt, mock_session):
    """US-09: decryption failure doesn't crash polling loop."""
    from app.tasks.polling import _poll_all

    record = _make_api_key_record()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record]
    mock_db.execute.return_value = mock_result
    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

    await _poll_all()  # Should not raise

    # No snapshot because decrypt failed before any fetching
    assert get_cached_snapshot(1, "openai") is None


@pytest.mark.asyncio
@patch("app.tasks.polling.async_session")
async def test_poll_empty_db(mock_session):
    """US-09: no providers in DB → polling completes without error."""
    from app.tasks.polling import _poll_all

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

    await _poll_all()  # Should not raise
