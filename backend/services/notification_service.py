from __future__ import annotations

import logging
from typing import Any

import auth
from models.user import User

logger = logging.getLogger(__name__)


def should_notify_email(user: User, event_type: str = "summary_completed") -> bool:
    """Return True when the user has email notifications enabled for the given event."""
    prefs: dict[str, Any] = getattr(user, "notification_preferences", None) or {}
    if not isinstance(prefs, dict):
        return False
    if prefs.get("email_notifications") is False:
        return False
    if event_type in prefs:
        return bool(prefs.get(event_type))
    return bool(prefs.get("email_notifications", False))


def deliver_user_notification(
    user: User,
    subject: str,
    plain_text: str,
    html_body: str | None = None,
    *,
    event_type: str = "summary_completed",
) -> bool:
    """Deliver an email notification when the user's saved preferences allow it."""
    if not user or not getattr(user, "email", None):
        return False
    if not should_notify_email(user, event_type=event_type):
        return False
    if not getattr(auth, "_send_email", None):
        return False

    try:
        auth._send_email(user.email, subject, plain_text, html_body)
        return True
    except Exception as exc:
        logger.info("Skipping notification delivery for %s: %s", user.email, exc)
        return False
