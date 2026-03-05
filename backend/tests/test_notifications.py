"""Tests for the push notification service."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.notifications.service import (
    DEDUP_WINDOW_SECONDS,
    WARNING_THRESHOLD,
    check_and_notify,
    clear_sent_alerts,
    evaluate_thresholds,
)
from app.providers.base import ProviderSnapshot, RateLimitInfo


def _make_snapshot(rpm_pct: float = 0.0, tpm_pct: float = 0.0) -> ProviderSnapshot:
    """Helper: build a snapshot with one model at the given usage percentages."""
    rpm_limit = 1000
    tpm_limit = 100000
    rl = RateLimitInfo(
        model="gpt-4",
        rpm_limit=rpm_limit,
        rpm_used=int(rpm_limit * rpm_pct / 100),
        tpm_limit=tpm_limit,
        tpm_used=int(tpm_limit * tpm_pct / 100),
    )
    return ProviderSnapshot(
        provider="openai",
        rate_limits=[rl],
        usage=[],
        costs=None,
        fetched_at=datetime.now(UTC),
    )


class TestEvaluateThresholds:
    def test_warning_threshold_triggered(self):
        snapshot = _make_snapshot(rpm_pct=85.0, tpm_pct=50.0)
        alerts = evaluate_thresholds(snapshot)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "warning"
        assert alerts[0]["metric"] == "rpm"
        assert alerts[0]["pct"] >= WARNING_THRESHOLD

    def test_critical_threshold_triggered(self):
        snapshot = _make_snapshot(rpm_pct=97.0, tpm_pct=96.0)
        alerts = evaluate_thresholds(snapshot)
        assert len(alerts) == 2
        assert all(a["level"] == "critical" for a in alerts)

    def test_no_alert_below_threshold(self):
        snapshot = _make_snapshot(rpm_pct=50.0, tpm_pct=30.0)
        alerts = evaluate_thresholds(snapshot)
        assert len(alerts) == 0

    def test_both_warning_and_critical(self):
        snapshot = _make_snapshot(rpm_pct=82.0, tpm_pct=96.0)
        alerts = evaluate_thresholds(snapshot)
        levels = {a["metric"]: a["level"] for a in alerts}
        assert levels["rpm"] == "warning"
        assert levels["tpm"] == "critical"


class TestDeduplication:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_sent_alerts()
        yield
        clear_sent_alerts()

    @pytest.mark.asyncio
    async def test_same_alert_not_sent_twice_within_window(self):
        snapshot = _make_snapshot(rpm_pct=90.0)
        now = time.time()

        with (
            patch("app.notifications.service._apns_configured", return_value=True),
            patch("app.notifications.service._get_device_tokens", new_callable=AsyncMock, return_value=["token123"]),
            patch("app.notifications.service._send_apns", new_callable=AsyncMock, return_value=True),
        ):
            sent1 = await check_and_notify(1, "openai", snapshot, now=now)
            assert sent1 == 1

            sent2 = await check_and_notify(1, "openai", snapshot, now=now + 10)
            assert sent2 == 0  # deduplicated

    @pytest.mark.asyncio
    async def test_alert_sent_again_after_window_expires(self):
        snapshot = _make_snapshot(rpm_pct=90.0)
        now = time.time()

        with (
            patch("app.notifications.service._apns_configured", return_value=True),
            patch("app.notifications.service._get_device_tokens", new_callable=AsyncMock, return_value=["token123"]),
            patch("app.notifications.service._send_apns", new_callable=AsyncMock, return_value=True),
        ):
            sent1 = await check_and_notify(1, "openai", snapshot, now=now)
            assert sent1 == 1

            sent2 = await check_and_notify(1, "openai", snapshot, now=now + DEDUP_WINDOW_SECONDS + 1)
            assert sent2 == 1  # window expired, send again


class TestNoNotificationBelowThreshold:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_sent_alerts()
        yield
        clear_sent_alerts()

    @pytest.mark.asyncio
    async def test_no_notification_when_below_threshold(self):
        snapshot = _make_snapshot(rpm_pct=50.0, tpm_pct=30.0)

        with (
            patch("app.notifications.service._apns_configured", return_value=True),
            patch("app.notifications.service._get_device_tokens", new_callable=AsyncMock, return_value=["token123"]),
            patch("app.notifications.service._send_apns", new_callable=AsyncMock, return_value=True) as mock_send,
        ):
            sent = await check_and_notify(1, "openai", snapshot)
            assert sent == 0
            mock_send.assert_not_called()
