"""Push notification service — sends APNs alerts when usage approaches limits."""

import logging
import time

import httpx
from jose import jwt as jose_jwt
from sqlalchemy import select

from app.auth.models import DeviceRegistration
from app.config import settings
from app.db import async_session
from app.providers.base import ProviderSnapshot

logger = logging.getLogger(__name__)

# Thresholds (percentage of limit used)
WARNING_THRESHOLD = 80.0
CRITICAL_THRESHOLD = 95.0

# Deduplication: don't resend the same alert within this many seconds
DEDUP_WINDOW_SECONDS = 3600  # 1 hour

# In-memory dedup store: key -> timestamp of last notification
# Key format: "{user_id}:{provider}:{model}:{level}"
_sent_alerts: dict[str, float] = {}


def _apns_configured() -> bool:
    """Return True if all required APNs settings are present."""
    return bool(settings.APNS_TEAM_ID and settings.APNS_KEY_ID and settings.APNS_PRIVATE_KEY)


def _make_apns_jwt() -> str:
    """Create a short-lived JWT for APNs authentication."""
    now = int(time.time())
    payload = {"iss": settings.APNS_TEAM_ID, "iat": now}
    headers = {"alg": "ES256", "kid": settings.APNS_KEY_ID}
    return jose_jwt.encode(payload, settings.APNS_PRIVATE_KEY, algorithm="ES256", headers=headers)


def _apns_base_url() -> str:
    if settings.APNS_USE_SANDBOX:
        return "https://api.sandbox.push.apple.com"
    return "https://api.push.apple.com"


def _should_send(dedup_key: str, now: float | None = None) -> bool:
    """Check deduplication: return True if we haven't sent this alert recently."""
    now = now if now is not None else time.time()
    last_sent = _sent_alerts.get(dedup_key)
    if last_sent is not None and (now - last_sent) < DEDUP_WINDOW_SECONDS:
        return False
    return True


def _record_sent(dedup_key: str, now: float | None = None) -> None:
    """Record that we sent an alert for deduplication."""
    _sent_alerts[dedup_key] = now if now is not None else time.time()


def evaluate_thresholds(
    snapshot: ProviderSnapshot,
) -> list[dict]:
    """Evaluate rate limits in a snapshot and return alerts that should fire.

    Returns a list of dicts with keys: model, metric, pct, level.
    """
    alerts: list[dict] = []
    for rl in snapshot.rate_limits:
        for metric, pct in [("rpm", rl.rpm_pct), ("tpm", rl.tpm_pct)]:
            if pct >= CRITICAL_THRESHOLD:
                alerts.append({"model": rl.model, "metric": metric, "pct": pct, "level": "critical"})
            elif pct >= WARNING_THRESHOLD:
                alerts.append({"model": rl.model, "metric": metric, "pct": pct, "level": "warning"})
    return alerts


async def _send_apns(device_token: str, title: str, body: str) -> bool:
    """Send a single push notification via APNs HTTP/2."""
    token = _make_apns_jwt()
    url = f"{_apns_base_url()}/3/device/{device_token}"
    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": f"{settings.APNS_TEAM_ID}.com.tokenstats",
        "apns-push-type": "alert",
    }
    try:
        async with httpx.AsyncClient(http2=True) as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                return True
            logger.warning(
                "APNs returned %s for device %s: %s",
                resp.status_code,
                device_token[:12],
                resp.text,
            )
            return False
    except Exception:
        logger.exception("Failed to send APNs notification to device %s", device_token[:12])
        return False


async def _get_device_tokens(user_id: int) -> list[str]:
    """Fetch all registered device tokens for a user."""
    async with async_session() as db:
        result = await db.execute(select(DeviceRegistration.device_token).where(DeviceRegistration.user_id == user_id))
        return [row[0] for row in result.all()]


async def check_and_notify(
    user_id: int,
    provider: str,
    snapshot: ProviderSnapshot,
    now: float | None = None,
) -> int:
    """Check if any rate limit exceeds thresholds and send push notifications.

    Returns the number of notifications sent.
    """
    if not _apns_configured():
        return 0

    alerts = evaluate_thresholds(snapshot)
    if not alerts:
        return 0

    # Filter out deduplicated alerts
    ts = now if now is not None else time.time()
    new_alerts = []
    for alert in alerts:
        dedup_key = f"{user_id}:{provider}:{alert['model']}:{alert['metric']}:{alert['level']}"
        if _should_send(dedup_key, ts):
            new_alerts.append((alert, dedup_key))

    if not new_alerts:
        return 0

    device_tokens = await _get_device_tokens(user_id)
    if not device_tokens:
        return 0

    sent_count = 0
    for alert, dedup_key in new_alerts:
        level_label = "Warning" if alert["level"] == "warning" else "Critical"
        title = f"{level_label}: {provider} rate limit"
        body = f"{alert['model']} {alert['metric'].upper()} at {alert['pct']:.0f}% of limit"
        for token in device_tokens:
            success = await _send_apns(token, title, body)
            if success:
                sent_count += 1
        _record_sent(dedup_key, ts)

    return sent_count


def clear_sent_alerts() -> None:
    """Clear the deduplication store (for testing)."""
    _sent_alerts.clear()
