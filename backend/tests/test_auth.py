import base64
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import auth
import database
import main
from auth import Credentials, _hash_password, _token_digest, _verify_password
from database import Base
from models.research_paper import ResearchPaper
from models.user import User


class AuthHelperTests(unittest.TestCase):
    def test_password_hash_verifies_only_matching_password(self):
        stored_hash = _hash_password("a-long-example-password")

        self.assertTrue(_verify_password("a-long-example-password", stored_hash))
        self.assertFalse(_verify_password("a-different-password", stored_hash))

    def test_credentials_normalize_email_and_require_valid_address(self):
        credentials = Credentials(email=" Person@Example.com ", password="long-password-value")
        self.assertEqual(credentials.email, "person@example.com")

        with self.assertRaises(ValidationError):
            Credentials(email="not-an-email", password="long-password-value")

    def test_token_digest_is_stable_without_exposing_raw_token(self):
        digest = _token_digest("private-token")

        self.assertEqual(digest, _token_digest("private-token"))
        self.assertNotEqual(digest, "private-token")

    def test_auth_config_reports_whether_email_is_configured(self):
        with patch.dict("os.environ", {"SMTP_HOST": "smtp.test", "SMTP_FROM": "noreply@test"}):
            self.assertTrue(auth.auth_config()["email_configured"])

        with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_FROM": ""}):
            self.assertFalse(auth.auth_config()["email_configured"])

    def test_auth_config_reports_enabled_identity_providers(self):
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "google-id",
                "GOOGLE_CLIENT_SECRET": "google-secret",
                "GITHUB_CLIENT_ID": "github-id",
                "GITHUB_CLIENT_SECRET": "github-secret",
                "LINKEDIN_CLIENT_ID": "",
                "LINKEDIN_CLIENT_SECRET": "",
            },
        ):
            config = auth.auth_config()

        self.assertTrue(config["google_enabled"])
        self.assertTrue(config["github_enabled"])
        self.assertFalse(config["linkedin_enabled"])

    def test_auth_config_reports_twilio_verify_readiness(self):
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC-test",
                "TWILIO_AUTH_TOKEN": "test-auth-token",
                "TWILIO_VERIFY_SERVICE_SID": "VA-test",
            },
        ):
            self.assertTrue(auth.auth_config()["sms_enabled"])

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "",
                "TWILIO_AUTH_TOKEN": "",
                "TWILIO_VERIFY_SERVICE_SID": "",
            },
        ):
            self.assertFalse(auth.auth_config()["sms_enabled"])

    def test_phone_login_and_phone_link_use_twilio_verify(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_engine = create_engine(
                f"sqlite:///{Path(temporary_directory) / 'sms-test.db'}",
                connect_args={"check_same_thread": False},
            )
            test_session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=test_engine,
            )
            original_engine = main.engine
            original_main_session = main.SessionLocal
            original_db_session = database.SessionLocal

            try:
                main.engine = test_engine
                main.SessionLocal = test_session_local
                database.SessionLocal = test_session_local
                Base.metadata.create_all(bind=test_engine)
                with test_session_local() as db:
                    db.add_all([
                        User(
                            email="phone-login@example.com",
                            password_hash=_hash_password("phone-login-password"),
                            email_verified=True,
                            phone_number="+14155552671",
                            phone_verified=True,
                        ),
                        User(
                            email="phone-link@example.com",
                            password_hash=_hash_password("phone-link-password"),
                            email_verified=True,
                        ),
                    ])
                    db.commit()

                twilio_responses = []
                for status in ("pending", "approved", "pending", "approved"):
                    response = Mock()
                    response.raise_for_status.return_value = None
                    response.json.return_value = {"status": status}
                    twilio_responses.append(response)

                with (
                    patch.dict(
                        "os.environ",
                        {
                            "TWILIO_ACCOUNT_SID": "AC-test",
                            "TWILIO_AUTH_TOKEN": "test-auth-token",
                            "TWILIO_VERIFY_SERVICE_SID": "VA-test",
                        },
                    ),
                    patch.object(
                        auth.requests,
                        "post",
                        side_effect=twilio_responses,
                    ) as twilio_post,
                    TestClient(main.app) as client,
                ):
                    self.assertTrue(client.get("/auth/config").json()["sms_enabled"])
                    code_request = client.post(
                        "/auth/phone/login/code",
                        json={"phone_number": "+14155552671"},
                    )
                    self.assertEqual(code_request.status_code, 200)
                    verified_login = client.post(
                        "/auth/phone/login/verify?remember_me=true",
                        json={
                            "challenge_id": code_request.json()["challenge_id"],
                            "code": "123456",
                        },
                    )
                    self.assertEqual(verified_login.status_code, 200)
                    self.assertEqual(verified_login.json()["user"]["email"], "phone-login@example.com")
                    self.assertIn("Max-Age=1209600", verified_login.headers["set-cookie"])

                    self.assertEqual(client.post("/auth/logout").status_code, 200)
                    email_login = client.post(
                        "/auth/login",
                        json={
                            "email": "phone-link@example.com",
                            "password": "phone-link-password",
                        },
                    )
                    self.assertEqual(email_login.status_code, 200)
                    link_request = client.post(
                        "/auth/phone/link/code",
                        json={"phone_number": "+14155552672"},
                    )
                    self.assertEqual(link_request.status_code, 200)
                    linked_phone = client.post(
                        "/auth/phone/link/verify",
                        json={
                            "challenge_id": link_request.json()["challenge_id"],
                            "code": "123456",
                        },
                    )
                    self.assertEqual(linked_phone.status_code, 200)
                    self.assertEqual(linked_phone.json()["user"]["phone_number"], "+14155552672")
                    self.assertTrue(linked_phone.json()["user"]["phone_verified"])
                    unknown_number = client.post(
                        "/auth/phone/login/code",
                        json={"phone_number": "+14155552673"},
                    )
                    self.assertEqual(unknown_number.status_code, 200)
                    invalid_code = client.post(
                        "/auth/phone/login/verify",
                        json={
                            "challenge_id": unknown_number.json()["challenge_id"],
                            "code": "123456",
                        },
                    )
                    self.assertEqual(invalid_code.status_code, 401)
                    self.assertEqual(twilio_post.call_count, 4)
            finally:
                main.engine = original_engine
                main.SessionLocal = original_main_session
                database.SessionLocal = original_db_session
                Base.metadata.drop_all(bind=test_engine)
                test_engine.dispose()

    def test_profile_settings_are_private_and_persist_across_requests(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_engine = create_engine(
                f"sqlite:///{Path(temporary_directory) / 'profile-test.db'}",
                connect_args={"check_same_thread": False},
            )
            test_session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=test_engine,
            )
            original_engine = main.engine
            original_main_session = main.SessionLocal
            original_db_session = database.SessionLocal

            try:
                main.engine = test_engine
                main.SessionLocal = test_session_local
                database.SessionLocal = test_session_local
                Base.metadata.create_all(bind=test_engine)
                with test_session_local() as db:
                    db.add_all([
                        User(
                            email="profile@example.com",
                            password_hash=_hash_password("profile-secure-password"),
                            email_verified=True,
                        ),
                        User(
                            email="other@example.com",
                            password_hash=_hash_password("other-secure-password"),
                            email_verified=True,
                            username="taken_user",
                        ),
                    ])
                    db.commit()

                with TestClient(main.app) as client:
                    login_response = client.post(
                        "/auth/login",
                        json={
                            "email": "profile@example.com",
                            "password": "profile-secure-password",
                        },
                    )
                    self.assertEqual(login_response.status_code, 200)

                    initial_settings = client.get("/auth/profile")
                    self.assertEqual(initial_settings.status_code, 200)
                    self.assertEqual(
                        initial_settings.json()["privacy"]["profile_visibility"],
                        "private",
                    )

                    saved_settings = client.put(
                        "/auth/profile",
                        json={
                            "username": "Research_User",
                            "full_name": "Research User",
                            "education_level": "Graduate",
                            "institution": "Example University",
                        },
                    )
                    self.assertEqual(saved_settings.status_code, 200)
                    self.assertEqual(saved_settings.json()["profile"]["username"], "research_user")
                    self.assertEqual(
                        saved_settings.json()["profile"]["institution"],
                        "Example University",
                    )
                    self.assertEqual(saved_settings.json()["user"]["full_name"], "Research User")
                    self.assertEqual(
                        client.put(
                            "/auth/profile",
                            json={"phone_number": "123456789"},
                        ).status_code,
                        422,
                    )
                    self.assertEqual(
                        client.put(
                            "/auth/profile",
                            json={"phone_number": "1234567890"},
                        ).status_code,
                        200,
                    )

                    self.assertEqual(
                        client.put(
                            "/auth/profile",
                            json={"username": "taken_user"},
                        ).status_code,
                        409,
                    )
                    self.assertEqual(
                        client.put(
                            "/auth/profile",
                            json={"username": "bad username"},
                        ).status_code,
                        422,
                    )

                    notification_response = client.put(
                        "/auth/profile/notifications",
                        json={"weekly_digest": True, "email_notifications": True},
                    )
                    self.assertEqual(notification_response.status_code, 200)
                    self.assertTrue(client.get("/auth/profile").json()["notifications"]["weekly_digest"])

                    privacy_response = client.put(
                        "/auth/profile/privacy",
                        json={"profile_visibility": "public", "show_email": True},
                    )
                    self.assertEqual(privacy_response.status_code, 200)
                    self.assertEqual(
                        client.get("/auth/profile").json()["privacy"]["profile_visibility"],
                        "public",
                    )

                    image_bytes = base64.b64decode(
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l7sAAAAASUVORK5CYII="
                    )
                    image_response = client.post(
                        "/auth/profile/image",
                        files={"image": ("avatar.png", image_bytes, "image/png")},
                    )
                    self.assertEqual(image_response.status_code, 200)
                    self.assertIn("profile/image", client.get("/auth/profile").json()["user"]["profile_image_url"])
                    fetched_image = client.get("/auth/profile/image")
                    self.assertEqual(fetched_image.status_code, 200)
                    self.assertEqual(fetched_image.content, image_bytes)
                    self.assertEqual(client.delete("/auth/profile/image").status_code, 200)
                    self.assertIsNone(client.get("/auth/profile").json()["user"]["profile_image_url"])
            finally:
                main.engine = original_engine
                main.SessionLocal = original_main_session
                database.SessionLocal = original_db_session
                Base.metadata.drop_all(bind=test_engine)
                test_engine.dispose()

    def test_verification_email_has_styled_html_and_plain_text_fallback(self):
        verification_url = "https://researchmate.test/?verify_email=token&source=email"
        plain_text, html_body = auth._verification_email_content(verification_url)

        self.assertIn(verification_url, plain_text)
        self.assertIn("expires in 24 hours", plain_text)
        self.assertIn("Verify email address", html_body)
        self.assertIn(
            "href=\"https://researchmate.test/?verify_email=token&amp;source=email\"",
            html_body,
        )

    def test_github_and_linkedin_oauth_create_verified_sessions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_engine = create_engine(
                f"sqlite:///{Path(temporary_directory) / 'oauth-test.db'}",
                connect_args={"check_same_thread": False},
            )
            test_session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=test_engine,
            )
            original_engine = main.engine
            original_main_session = main.SessionLocal
            original_db_session = database.SessionLocal

            try:
                main.engine = test_engine
                main.SessionLocal = test_session_local
                database.SessionLocal = test_session_local
                Base.metadata.create_all(bind=test_engine)

                with (
                    patch.dict(
                        "os.environ",
                        {
                            "GITHUB_CLIENT_ID": "github-id",
                            "GITHUB_CLIENT_SECRET": "github-secret",
                            "LINKEDIN_CLIENT_ID": "linkedin-id",
                            "LINKEDIN_CLIENT_SECRET": "linkedin-secret",
                        },
                    ),
                    TestClient(main.app) as client,
                ):
                    providers = (
                        (
                            "github",
                            "github@example.com",
                            {"id": 12345},
                            [{"email": "github@example.com", "primary": True, "verified": True}],
                        ),
                        (
                            "linkedin",
                            "linkedin@example.com",
                            {
                                "sub": "linkedin-subject",
                                "email": "linkedin@example.com",
                                "email_verified": True,
                            },
                            None,
                        ),
                    )

                    for provider, email, profile, email_list in providers:
                        with self.subTest(provider=provider):
                            start_response = client.get(
                                f"/auth/{provider}/start",
                                follow_redirects=False,
                            )
                            self.assertEqual(start_response.status_code, 302)
                            state = parse_qs(urlparse(
                                start_response.headers["location"]
                            ).query)["state"][0]
                            token_response = Mock()
                            token_response.raise_for_status.return_value = None
                            token_response.json.return_value = {"access_token": "provider-access-token"}
                            profile_response = Mock()
                            profile_response.raise_for_status.return_value = None
                            profile_response.json.return_value = profile
                            get_responses = [profile_response]
                            if email_list is not None:
                                emails_response = Mock()
                                emails_response.raise_for_status.return_value = None
                                emails_response.json.return_value = email_list
                                get_responses.append(emails_response)

                            with (
                                patch.object(
                                    auth.requests,
                                    "post",
                                    return_value=token_response,
                                ),
                                patch.object(
                                    auth.requests,
                                    "get",
                                    side_effect=get_responses,
                                ),
                            ):
                                callback = client.get(
                                    f"/auth/{provider}/callback?code=provider-code&state={state}",
                                    follow_redirects=False,
                                )

                            self.assertEqual(callback.status_code, 303)
                            signed_in = client.get("/auth/me")
                            self.assertEqual(signed_in.status_code, 200)
                            user = signed_in.json()["user"]
                            self.assertEqual(user["email"], email)
                            self.assertTrue(user["email_verified"])
                            self.assertIn(provider, user["providers"])
            finally:
                main.engine = original_engine
                main.SessionLocal = original_main_session
                database.SessionLocal = original_db_session
                Base.metadata.drop_all(bind=test_engine)
                test_engine.dispose()

    def test_send_email_includes_html_alternative(self):
        with (
            patch.object(
                auth,
                "_email_configuration",
                return_value=("smtp.test", 587, "", "", "noreply@test", False),
            ),
            patch.object(auth.smtplib, "SMTP") as smtp_client,
        ):
            smtp_server = smtp_client.return_value.__enter__.return_value
            auth._send_email(
                "person@example.com",
                "Verify your ResearchMate account",
                "Verify your email: https://researchmate.test/verify",
                "<p>Verify your email</p>",
            )

        sent_message = smtp_server.send_message.call_args.args[0]
        self.assertEqual(sent_message.get_content_type(), "multipart/alternative")
        self.assertEqual(
            sent_message.get_body(("plain",)).get_content().strip(),
            "Verify your email: https://researchmate.test/verify",
        )
        self.assertIn("Verify your email", sent_message.get_body(("html",)).get_content())

    def test_registered_accounts_get_private_libraries_and_claim_legacy_papers(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_engine = create_engine(
                f"sqlite:///{Path(temporary_directory) / 'auth-test.db'}",
                connect_args={"check_same_thread": False},
            )
            test_session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=test_engine,
            )
            original_engine = main.engine
            original_main_session = main.SessionLocal
            original_db_session = database.SessionLocal

            try:
                main.engine = test_engine
                main.SessionLocal = test_session_local
                database.SessionLocal = test_session_local
                Base.metadata.create_all(bind=test_engine)
                with test_session_local() as db:
                    db.add(ResearchPaper(
                        title="Legacy paper",
                        filename="legacy.pdf",
                        stored_filename="legacy.pdf",
                        file_path=str(Path(temporary_directory) / "legacy.pdf"),
                        summary="Legacy summary",
                        pages=1,
                    ))
                    db.commit()

                with (
                    patch.dict("os.environ", {"SMTP_HOST": "smtp.test", "SMTP_FROM": "noreply@test"}),
                    patch.object(auth, "_send_email") as send_email,
                    TestClient(main.app) as client,
                ):
                    first_registration = client.post(
                        "/auth/register",
                        json={"email": "first@example.com", "password": "first-secure-password"},
                    )
                    self.assertEqual(first_registration.status_code, 201)
                    verification_body = send_email.call_args.args[2]
                    verification_html = send_email.call_args.args[3]
                    self.assertIn("Verify email address", verification_html)
                    verification_token = re.search(
                        r"verify_email=([^\s]+)", verification_body
                    ).group(1)
                    verified = client.post(
                        "/auth/verify-email",
                        json={"token": verification_token},
                    )
                    self.assertEqual(verified.status_code, 200)

                    first_login = client.post(
                        "/auth/login",
                        json={"email": "first@example.com", "password": "first-secure-password"},
                    )
                    self.assertEqual(first_login.status_code, 200)
                    self.assertNotIn("max-age=", first_login.headers["set-cookie"].lower())
                    current_user = client.get("/auth/me").json()["user"]
                    self.assertIn("email", current_user["providers"])
                    self.assertTrue(current_user["email_verified"])
                    self.assertEqual(
                        client.put(
                            "/auth/password",
                            json={
                                "current_password": "incorrect-password",
                                "new_password": "first-updated-password",
                            },
                        ).status_code,
                        400,
                    )
                    self.assertEqual(
                        client.put(
                            "/auth/password",
                            json={
                                "current_password": "first-secure-password",
                                "new_password": "first-updated-password",
                            },
                        ).status_code,
                        200,
                    )
                    remembered_login = client.post(
                        "/auth/login",
                        json={
                            "email": "first@example.com",
                            "password": "first-updated-password",
                            "remember_me": True,
                        },
                    )
                    self.assertEqual(remembered_login.status_code, 200)
                    self.assertIn("max-age=1209600", remembered_login.headers["set-cookie"].lower())
                    first_library = client.get("/papers").json()["papers"]
                    self.assertEqual([paper["title"] for paper in first_library], ["Legacy paper"])

                    second_registration = client.post(
                        "/auth/register",
                        json={"email": "second@example.com", "password": "second-secure-password"},
                    )
                    self.assertEqual(second_registration.status_code, 201)
                    second_verification_body = send_email.call_args.args[2]
                    second_token = re.search(
                        r"verify_email=([^\s]+)", second_verification_body
                    ).group(1)
                    self.assertEqual(
                        client.post("/auth/verify-email", json={"token": second_token}).status_code,
                        200,
                    )
                    second_login = client.post(
                        "/auth/login",
                        json={"email": "second@example.com", "password": "second-secure-password"},
                    )
                    self.assertEqual(second_login.status_code, 200)
                    self.assertEqual(client.get("/papers").json()["papers"], [])
            finally:
                main.engine = original_engine
                main.SessionLocal = original_main_session
                database.SessionLocal = original_db_session
                Base.metadata.drop_all(bind=test_engine)
                test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
