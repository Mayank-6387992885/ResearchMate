import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.user import User  # noqa: E402
from services.notification_service import deliver_user_notification, should_notify_email  # noqa: E402


def test_notification_respects_saved_preferences():
    user_disabled = User(id=1, email="a@example.com", password_hash="x", notification_preferences={"email_notifications": False})
    user_enabled = User(id=2, email="b@example.com", password_hash="x", notification_preferences={"email_notifications": True, "summary_completed": True})

    assert should_notify_email(user_disabled, "summary_completed") is False
    assert should_notify_email(user_enabled, "summary_completed") is True


def test_deliver_user_notification_sends_email_when_enabled():
    user = User(
        id=2,
        email="researcher@example.com",
        password_hash="x",
        notification_preferences={"email_notifications": True, "summary_completed": True},
    )
    with (
        patch("auth._is_email_configured", return_value=True),
        patch("auth._send_email") as mock_send,
    ):
        sent = deliver_user_notification(
            user,
            "Summary Ready",
            "Your paper summary is ready.",
            "<p>Your paper summary is ready.</p>",
            event_type="summary_completed",
        )
        assert sent is True
        mock_send.assert_called_once()
