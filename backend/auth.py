"""Account, verification, session, and Google OAuth endpoints."""

import base64
import hashlib
import html
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from database import get_db
from models.auth_token import AuthToken
from models.research_paper import ResearchPaper
from models.sms_verification import SmsVerification
from models.user import User

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)

SESSION_COOKIE = "researchmate_session"
OAUTH_STATE_COOKIE = "researchmate_oauth_state"
SESSION_DAYS = 14
SESSION_HOURS = 12
VERIFICATION_HOURS = 24
RESET_MINUTES = 30
PROFILE_IMAGE_MAX_BYTES = 2 * 1024 * 1024
SMS_CODE_MINUTES = 5
SMS_RESEND_SECONDS = 60
SMS_PHONE_HOURLY_LIMIT = 5
SMS_REQUEST_HOURLY_LIMIT = 20
SMS_CODE_ATTEMPT_LIMIT = 5
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

DEFAULT_NOTIFICATION_PREFERENCES = {
    "email_notifications": False,
    "research_recommendations": False,
    "collaboration_requests": False,
    "project_updates": False,
    "messages_replies": False,
    "platform_announcements": False,
    "weekly_digest": False,
}
DEFAULT_PRIVACY_SETTINGS = {
    "profile_visibility": "private",
    "show_email": False,
    "show_education": True,
    "show_research_interests": True,
    "show_publications": True,
    "allow_collaboration_requests": False,
    "search_engine_visibility": False,
}


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class LoginCredentials(Credentials):
    remember_me: bool = False


class EmailAddress(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class PhoneNumber(BaseModel):
    phone_number: str = Field(min_length=8, max_length=16)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized):
            raise ValueError("Enter a phone number in international format, such as +14155552671.")
        return normalized


class PhoneCode(BaseModel):
    challenge_id: str = Field(min_length=32, max_length=128)
    code: str = Field(min_length=4, max_length=10)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Enter the numeric code from your text message.")
        return value


class TokenPayload(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=10, max_length=256)


class PasswordChange(BaseModel):
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class ProfileSettingsUpdate(BaseModel):
    username: str = Field(default="", max_length=30)
    full_name: str = Field(default="", max_length=120)
    date_of_birth: str = Field(default="", max_length=10)
    gender: str = Field(default="", max_length=40)
    phone_number: str = Field(default="", max_length=40)
    country: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    short_bio: str = Field(default="", max_length=500)
    education_level: str = Field(default="", max_length=100)
    institution: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=150)
    degree: str = Field(default="", max_length=150)
    specialization: str = Field(default="", max_length=200)
    graduation_year: str = Field(default="", max_length=4)
    academic_role: str = Field(default="", max_length=100)
    research_interests: str = Field(default="", max_length=2000)
    research_areas: str = Field(default="", max_length=2000)
    skills: str = Field(default="", max_length=2000)
    research_experience: str = Field(default="", max_length=3000)
    publications: str = Field(default="", max_length=3000)
    projects: str = Field(default="", max_length=3000)
    research_goals: str = Field(default="", max_length=2000)
    github_url: str = Field(default="", max_length=500)
    linkedin_url: str = Field(default="", max_length=500)
    google_scholar_url: str = Field(default="", max_length=500)
    orcid_id: str = Field(default="", max_length=100)
    personal_website: str = Field(default="", max_length=500)
    researchgate_url: str = Field(default="", max_length=500)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower().lstrip("@")
        if normalized and not re.fullmatch(r"[a-z0-9_]{3,30}", normalized):
            raise ValueError("Username must be 3–30 characters using letters, numbers, or underscores.")
        return normalized

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: str) -> str:
        value = value.strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Enter a valid date of birth.") from exc
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_profile_phone_number(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not re.fullmatch(r"\d{10}", normalized):
            raise ValueError("Enter a phone number containing exactly 10 digits.")
        return normalized

    @field_validator("graduation_year")
    @classmethod
    def validate_graduation_year(cls, value: str) -> str:
        value = value.strip()
        if value and (len(value) != 4 or not value.isdigit()):
            raise ValueError("Enter a four-digit graduation year.")
        return value


class NotificationPreferences(BaseModel):
    email_notifications: bool = False
    research_recommendations: bool = False
    collaboration_requests: bool = False
    project_updates: bool = False
    messages_replies: bool = False
    platform_announcements: bool = False
    weekly_digest: bool = False


class PrivacySettings(BaseModel):
    profile_visibility: str = "private"
    show_email: bool = False
    show_education: bool = True
    show_research_interests: bool = True
    show_publications: bool = True
    allow_collaboration_requests: bool = False
    search_engine_visibility: bool = False

    @field_validator("profile_visibility")
    @classmethod
    def validate_profile_visibility(cls, value: str) -> str:
        if value not in {"private", "public"}:
            raise ValueError("Profile visibility must be public or private.")
        return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _twilio_verify_config() -> tuple[str, str, str]:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    service_sid = os.getenv("TWILIO_VERIFY_SERVICE_SID", "").strip()
    if not account_sid or not auth_token or not service_sid:
        raise HTTPException(
            status_code=503,
            detail=(
                "SMS sign-in is not configured. Set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_VERIFY_SERVICE_SID in backend/.env, "
                "then restart the backend."
            ),
        )
    return account_sid, auth_token, service_sid


def _private_digest(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _twilio_verify_request(
    account_sid: str,
    auth_token: str,
    service_sid: str,
    endpoint: str,
    values: dict[str, str],
) -> dict[str, Any]:
    url = f"https://verify.twilio.com/v2/Services/{service_sid}/{endpoint}"
    try:
        response = requests.post(
            url,
            data=values,
            auth=(account_sid, auth_token),
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Twilio Verify response was not a JSON object.")
        return result
    except requests.RequestException as exc:
        logger.warning("Twilio Verify request failed with status %s.", getattr(
            getattr(exc, "response", None), "status_code", "unavailable"
        ))
        raise HTTPException(
            status_code=502,
            detail="The SMS verification service could not complete the request. Please try again.",
        ) from exc
    except ValueError as exc:
        logger.warning("Twilio Verify returned an invalid response.")
        raise HTTPException(
            status_code=502,
            detail="The SMS verification service returned an invalid response.",
        ) from exc


def _enforce_sms_rate_limits(
    db: Session,
    phone_hash: str,
    request_hash: str,
) -> None:
    now = _utcnow()
    db.query(SmsVerification).filter(
        SmsVerification.created_at <= now - timedelta(hours=1),
    ).delete(
        synchronize_session=False,
    )
    recent_phone = db.query(SmsVerification).filter(
        SmsVerification.phone_hash == phone_hash,
        SmsVerification.created_at >= now - timedelta(seconds=SMS_RESEND_SECONDS),
    ).count()
    hourly_phone = db.query(SmsVerification).filter(
        SmsVerification.phone_hash == phone_hash,
        SmsVerification.created_at >= now - timedelta(hours=1),
    ).count()
    hourly_request = db.query(SmsVerification).filter(
        SmsVerification.request_hash == request_hash,
        SmsVerification.created_at >= now - timedelta(hours=1),
    ).count()
    if recent_phone:
        raise HTTPException(
            status_code=429,
            detail="Please wait 60 seconds before requesting another verification code.",
        )
    if hourly_phone >= SMS_PHONE_HOURLY_LIMIT or hourly_request >= SMS_REQUEST_HOURLY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many SMS verification requests. Please try again later.",
        )


def _create_sms_challenge(
    db: Session,
    user_id: int | None,
    purpose: str,
    phone_number: str,
    phone_hash: str,
    request_hash: str,
) -> str:
    challenge_id = secrets.token_urlsafe(32)
    db.add(SmsVerification(
        user_id=user_id,
        challenge_hash=_token_digest(challenge_id),
        purpose=purpose,
        phone_number=phone_number,
        phone_hash=phone_hash,
        request_hash=request_hash,
        expires_at=_utcnow() + timedelta(minutes=SMS_CODE_MINUTES),
    ))
    db.commit()
    return challenge_id


def _active_sms_challenge(
    db: Session,
    challenge_id: str,
    purpose: str,
    user_id: int | None = None,
) -> SmsVerification:
    challenge = db.query(SmsVerification).filter(
        SmsVerification.challenge_hash == _token_digest(challenge_id),
        SmsVerification.purpose == purpose,
        SmsVerification.expires_at > _utcnow(),
        SmsVerification.used_at.is_(None),
    ).first()
    if challenge is None or (user_id is not None and challenge.user_id != user_id):
        raise HTTPException(status_code=400, detail="This verification request is invalid or expired.")
    if challenge.attempts >= SMS_CODE_ATTEMPT_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect codes. Request a new verification code.",
        )
    return challenge


def _check_sms_code(
    db: Session,
    challenge: SmsVerification,
    code: str,
) -> bool:
    challenge.attempts += 1
    db.commit()
    account_sid, auth_token, service_sid = _twilio_verify_config()
    result = _twilio_verify_request(
        account_sid,
        auth_token,
        service_sid,
        "VerificationCheck",
        {"To": challenge.phone_number, "Code": code},
    )
    return result.get("status") == "approved"


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def _verify_password(password: str | None, stored_hash: str | None) -> bool:
    if not password or not stored_hash:
        return False
    try:
        algorithm, salt_value, digest_value = stored_hash.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _create_token(db: Session, user_id: int, purpose: str, expires_at: datetime) -> str:
    raw_token = secrets.token_urlsafe(48)
    db.add(AuthToken(
        user_id=user_id,
        token_hash=_token_digest(raw_token),
        purpose=purpose,
        expires_at=expires_at,
    ))
    return raw_token


def _profile_image_url(user: User) -> str | None:
    if not user.profile_image:
        return None
    image_version = hashlib.sha256(user.profile_image).hexdigest()[:12]
    return f"/auth/profile/image?v={image_version}"


def _email_configuration() -> tuple[str, int, str, str, str, bool]:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        raise HTTPException(
            status_code=503,
            detail=(
                "Email is not configured in the running backend. Check SMTP_HOST and "
                "SMTP_FROM in backend/.env, then restart the backend."
            ),
        )
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="SMTP_PORT must be a valid port number.") from exc
    return (
        host,
        port,
        os.getenv("SMTP_USERNAME", ""),
        os.getenv("SMTP_PASSWORD", ""),
        sender,
        os.getenv("SMTP_USE_SSL", "").lower() == "true",
    )


def _send_email(
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    host, port, username, password, sender, use_ssl = _email_configuration()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if username:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            if username:
                server.login(username, password)
            server.send_message(message)


def _verification_email_content(verification_url: str) -> tuple[str, str]:
    escaped_url = html.escape(verification_url, quote=True)
    plain_text = (
        "Welcome to ResearchMate!\n\n"
        "Confirm your email address to activate your account and keep your research "
        "workspace secure.\n\n"
        f"Verify your email: {verification_url}\n\n"
        "This link expires in 24 hours. If you did not create a ResearchMate account, "
        "you can ignore this email."
    )
    html_body = f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background-color:#f4f6fb;font-family:Arial,Helvetica,sans-serif;color:#20283a;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
      Confirm your email to activate your ResearchMate workspace.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#f4f6fb;">
      <tr>
        <td align="center" style="padding:40px 16px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background-color:#ffffff;border:1px solid #e6e9f2;border-radius:16px;">
            <tr>
              <td style="padding:32px 36px 12px;">
                <p style="margin:0;color:#6257d9;font-size:20px;font-weight:700;letter-spacing:-0.3px;">ResearchMate</p>
                <p style="margin:8px 0 0;color:#858da0;font-size:11px;font-weight:700;letter-spacing:1.4px;">YOUR RESEARCH WORKSPACE</p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 36px 36px;">
                <h1 style="margin:0 0 16px;color:#20283a;font-size:26px;line-height:1.3;">Confirm your email address</h1>
                <p style="margin:0 0 24px;color:#5f687b;font-size:15px;line-height:1.7;">
                  Welcome to ResearchMate. Confirm your email to activate your account and keep your research workspace secure.
                </p>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td align="center" bgcolor="#6257d9" style="border-radius:9px;">
                      <a href="{escaped_url}" style="display:inline-block;padding:14px 24px;border:1px solid #6257d9;border-radius:9px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;">Verify email address</a>
                    </td>
                  </tr>
                </table>
                <p style="margin:24px 0 8px;color:#737b8c;font-size:13px;line-height:1.6;">
                  This secure link expires in <strong style="color:#414a5d;">24 hours</strong>.
                </p>
                <p style="margin:0 0 8px;color:#737b8c;font-size:13px;line-height:1.6;">
                  If the button does not work, copy and paste this address into your browser:
                </p>
                <p style="margin:0;overflow-wrap:anywhere;word-break:break-word;color:#6257d9;font-size:12px;line-height:1.6;">
                  <a href="{escaped_url}" style="color:#6257d9;">{escaped_url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 36px;border-top:1px solid #edf0f5;">
                <p style="margin:0;color:#858da0;font-size:12px;line-height:1.6;">
                  If you did not create a ResearchMate account, you can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
          <p style="margin:18px 0 0;color:#a0a6b4;font-size:11px;line-height:1.5;">ResearchMate · Your research, organized.</p>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return plain_text, html_body


def _claim_legacy_papers(db: Session, user_id: int) -> None:
    db.query(ResearchPaper).filter(
        ResearchPaper.user_id.is_(None),
    ).update({"user_id": user_id}, synchronize_session=False)


def _set_session_cookie(response: Response, raw_token: str, max_age: int | None) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "").lower() == "true",
        samesite="lax",
        path="/",
    )


def _issue_session(
    db: Session,
    user: User,
    response: Response,
    remember_me: bool = False,
) -> None:
    session_lifetime = (
        timedelta(days=SESSION_DAYS)
        if remember_me
        else timedelta(hours=SESSION_HOURS)
    )
    raw_token = _create_token(
        db,
        user.id,
        "session",
        _utcnow() + session_lifetime,
    )
    db.commit()
    max_age = int(session_lifetime.total_seconds()) if remember_me else None
    _set_session_cookie(response, raw_token, max_age)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    token = db.query(AuthToken).filter(
        AuthToken.token_hash == _token_digest(raw_token),
        AuthToken.purpose == "session",
        AuthToken.expires_at > _utcnow(),
    ).first()
    if token is None:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")

    user = db.get(User, token.user_id)
    if user is None or not user.email_verified:
        raise HTTPException(status_code=401, detail="This account is unavailable. Please sign in again.")
    return user


def user_to_dict(user: User) -> dict[str, Any]:
    providers = []
    if user.password_hash:
        providers.append("email")
    if user.google_sub:
        providers.append("google")
    if user.github_id:
        providers.append("github")
    if user.linkedin_sub:
        providers.append("linkedin")
    if user.phone_verified:
        providers.append("sms")
    try:
        profile_data = json.loads(user.profile_data or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Saved profile settings could not be read.") from exc
    return {
        "id": user.id,
        "email": user.email,
        "email_verified": user.email_verified,
        "phone_number": user.phone_number or "",
        "phone_verified": user.phone_verified,
        "providers": providers,
        "username": user.username or "",
        "full_name": profile_data.get("full_name", ""),
        "profile_image_url": _profile_image_url(user),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/config")
def auth_config():
    return {
        "email_configured": bool(
            os.getenv("SMTP_HOST", "").strip()
            and os.getenv("SMTP_FROM", "").strip()
        ),
        "google_enabled": bool(
            os.getenv("GOOGLE_CLIENT_ID")
            and os.getenv("GOOGLE_CLIENT_SECRET")
        ),
        "github_enabled": bool(
            os.getenv("GITHUB_CLIENT_ID")
            and os.getenv("GITHUB_CLIENT_SECRET")
        ),
        "linkedin_enabled": bool(
            os.getenv("LINKEDIN_CLIENT_ID")
            and os.getenv("LINKEDIN_CLIENT_SECRET")
        ),
        "sms_enabled": bool(
            os.getenv("TWILIO_ACCOUNT_SID", "").strip()
            and os.getenv("TWILIO_AUTH_TOKEN", "").strip()
            and os.getenv("TWILIO_VERIFY_SERVICE_SID", "").strip()
        ),
    }


@router.post("/register", status_code=201)
def register(payload: Credentials, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    _email_configuration()

    verification_token = secrets.token_urlsafe(48)
    try:
        user = User(email=email, password_hash=_hash_password(payload.password))
        db.add(user)
        db.flush()
        db.add(AuthToken(
            user_id=user.id,
            token_hash=_token_digest(verification_token),
            purpose="email_verification",
            expires_at=_utcnow() + timedelta(hours=VERIFICATION_HOURS),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise

    verification_url = f"{FRONTEND_URL}/?verify_email={verification_token}"
    plain_text, html_body = _verification_email_content(verification_url)
    try:
        _send_email(
            email,
            "Verify your ResearchMate account",
            plain_text,
            html_body,
        )
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(
            status_code=503,
            detail="Your account was created but the verification email could not be sent. Try resending it.",
        ) from exc
    return {"message": "Check your email for an account verification link."}


@router.post("/login")
def login(
    payload: LoginCredentials,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before signing in.")
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
    ).delete(synchronize_session=False)
    _issue_session(db, user, response, payload.remember_me)
    return {"user": user_to_dict(user)}


@router.post("/phone/login/code")
def send_phone_login_code(
    payload: PhoneNumber,
    request: Request,
    db: Session = Depends(get_db),
):
    account_sid, auth_token, service_sid = _twilio_verify_config()
    phone_number = payload.phone_number
    phone_hash = _private_digest(phone_number, auth_token)
    request_hash = _private_digest(
        request.client.host if request.client else "unknown",
        auth_token,
    )
    _enforce_sms_rate_limits(db, phone_hash, request_hash)

    user = db.query(User).filter(
        User.phone_number == phone_number,
        User.phone_verified.is_(True),
    ).first()
    if user is not None:
        _twilio_verify_request(
            account_sid,
            auth_token,
            service_sid,
            "Verifications",
            {"To": phone_number, "Channel": "sms"},
        )
    challenge_id = _create_sms_challenge(
        db,
        user.id if user else None,
        "login",
        phone_number,
        phone_hash,
        request_hash,
    )
    return {
        "challenge_id": challenge_id,
        "message": "If this number is linked to an account, a verification code has been sent.",
    }


@router.post("/phone/login/verify")
def verify_phone_login_code(
    payload: PhoneCode,
    response: Response,
    remember_me: bool = False,
    db: Session = Depends(get_db),
):
    challenge = _active_sms_challenge(db, payload.challenge_id, "login")
    if challenge.user_id is None:
        challenge.attempts += 1
        if challenge.attempts >= SMS_CODE_ATTEMPT_LIMIT:
            challenge.used_at = _utcnow()
        db.commit()
        raise HTTPException(status_code=401, detail="The verification code is invalid or expired.")
    if not _check_sms_code(db, challenge, payload.code):
        raise HTTPException(status_code=401, detail="The verification code is invalid or expired.")

    user = db.get(User, challenge.user_id)
    if user is None or not user.email_verified or not user.phone_verified:
        raise HTTPException(status_code=401, detail="The verification code is invalid or expired.")
    challenge.used_at = _utcnow()
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
    ).delete(synchronize_session=False)
    _issue_session(db, user, response, remember_me)
    return {"user": user_to_dict(user)}


@router.post("/phone/link/code")
def send_phone_link_code(
    payload: PhoneNumber,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account_sid, auth_token, service_sid = _twilio_verify_config()
    phone_number = payload.phone_number
    if user.phone_verified and user.phone_number == phone_number:
        return {"verified": True, "phone_number": phone_number}
    existing = db.query(User.id).filter(
        User.phone_number == phone_number,
        User.id != user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This phone number is linked to another account.")

    phone_hash = _private_digest(phone_number, auth_token)
    request_hash = _private_digest(
        request.client.host if request.client else "unknown",
        auth_token,
    )
    _enforce_sms_rate_limits(db, phone_hash, request_hash)
    _twilio_verify_request(
        account_sid,
        auth_token,
        service_sid,
        "Verifications",
        {"To": phone_number, "Channel": "sms"},
    )
    challenge_id = _create_sms_challenge(
        db,
        user.id,
        "link",
        phone_number,
        phone_hash,
        request_hash,
    )
    return {"challenge_id": challenge_id, "message": "A verification code has been sent."}


@router.post("/phone/link/verify")
def verify_phone_link_code(
    payload: PhoneCode,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    challenge = _active_sms_challenge(db, payload.challenge_id, "link", user.id)
    if not _check_sms_code(db, challenge, payload.code):
        raise HTTPException(status_code=401, detail="The verification code is invalid or expired.")

    existing = db.query(User.id).filter(
        User.phone_number == challenge.phone_number,
        User.id != user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This phone number is linked to another account.")

    user.phone_number = challenge.phone_number
    user.phone_verified = True
    challenge.used_at = _utcnow()
    db.commit()
    return {
        "user": user_to_dict(user),
        "phone_number": user.phone_number,
        "verified": user.phone_verified,
        "message": "Your phone number is verified for SMS sign-in.",
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        db.query(AuthToken).filter(
            AuthToken.token_hash == _token_digest(raw_token),
            AuthToken.purpose == "session",
        ).delete(synchronize_session=False)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return {"message": "Signed out."}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user_to_dict(user)}


def _read_settings(stored_value: str | None, defaults: dict[str, Any]) -> dict[str, Any]:
    try:
        stored = json.loads(stored_value or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Saved profile settings could not be read.") from exc
    return {**defaults, **stored}


def _profile_settings_response(user: User) -> dict[str, Any]:
    profile = _read_settings(user.profile_data, {})
    profile.update({
        "username": user.username or "",
        "email_address": user.email,
        "email_verified": user.email_verified,
        "profile_image_url": _profile_image_url(user),
    })
    return {
        "profile": profile,
        "notifications": _read_settings(
            user.notification_preferences,
            DEFAULT_NOTIFICATION_PREFERENCES,
        ),
        "privacy": _read_settings(user.privacy_settings, DEFAULT_PRIVACY_SETTINGS),
        "user": user_to_dict(user),
    }


@router.get("/profile")
def get_profile_settings(user: User = Depends(get_current_user)):
    return _profile_settings_response(user)


@router.put("/profile")
def update_profile_settings(
    payload: ProfileSettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    username = payload.username or None
    if username and db.query(User.id).filter(
        User.username == username,
        User.id != user.id,
    ).first():
        raise HTTPException(status_code=409, detail="That username is already in use.")

    user.username = username
    user.profile_data = json.dumps(
        payload.model_dump(exclude={"username"}),
        ensure_ascii=True,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is already in use.") from exc
    return _profile_settings_response(user)


@router.post("/profile/image")
async def upload_profile_image(
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await image.read(PROFILE_IMAGE_MAX_BYTES + 1)
    if len(content) > PROFILE_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Profile images must be 2 MB or smaller.")

    image_type = None
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        image_type = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        image_type = "image/jpeg"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        image_type = "image/webp"
    if image_type is None:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, or WebP image.")

    user.profile_image = content
    user.profile_image_type = image_type
    db.commit()
    return {"profile_image_url": "/auth/profile/image"}


@router.get("/profile/image")
def get_profile_image(user: User = Depends(get_current_user)):
    if not user.profile_image or not user.profile_image_type:
        raise HTTPException(status_code=404, detail="No profile image has been uploaded.")
    return Response(
        content=user.profile_image,
        media_type=user.profile_image_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/profile/image")
def delete_profile_image(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.profile_image = None
    user.profile_image_type = None
    db.commit()
    return {"profile_image_url": None}


@router.put("/profile/notifications")
def update_notification_preferences(
    payload: NotificationPreferences,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.notification_preferences = payload.model_dump_json()
    db.commit()
    return _profile_settings_response(user)


@router.put("/profile/privacy")
def update_privacy_settings(
    payload: PrivacySettings,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.privacy_settings = payload.model_dump_json()
    db.commit()
    return _profile_settings_response(user)


@router.put("/password")
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.password_hash and not _verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if not user.password_hash and payload.current_password:
        raise HTTPException(
            status_code=400,
            detail="This account does not have a password. Leave the current password blank.",
        )

    user.password_hash = _hash_password(payload.new_password)
    current_token = request.cookies.get(SESSION_COOKIE, "")
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
        AuthToken.token_hash != _token_digest(current_token),
    ).delete(synchronize_session=False)
    db.commit()
    return {
        "message": "Your password has been updated.",
        "user": user_to_dict(user),
    }


def _consume_token(db: Session, raw_token: str, purpose: str) -> AuthToken:
    token = db.query(AuthToken).filter(
        AuthToken.token_hash == _token_digest(raw_token),
        AuthToken.purpose == purpose,
        AuthToken.expires_at > _utcnow(),
    ).first()
    if token is None:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    db.delete(token)
    return token


@router.post("/verify-email")
def verify_email(payload: TokenPayload, db: Session = Depends(get_db)):
    token = _consume_token(db, payload.token, "email_verification")
    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="This account no longer exists.")
    is_first_verified_user = (
        db.query(User.id).filter(User.email_verified.is_(True)).count() == 0
    )
    user.email_verified = True
    if is_first_verified_user:
        _claim_legacy_papers(db, user.id)
    db.commit()
    return {"message": "Email verified. You can now sign in."}


@router.post("/resend-verification")
def resend_verification(payload: EmailAddress, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.email_verified:
        return {"message": "If the account needs verification, an email will be sent."}
    token = _create_token(
        db,
        user.id,
        "email_verification",
        _utcnow() + timedelta(hours=VERIFICATION_HOURS),
    )
    db.commit()
    verification_url = f"{FRONTEND_URL}/?verify_email={token}"
    plain_text, html_body = _verification_email_content(verification_url)
    _send_email(
        email,
        "Verify your ResearchMate account",
        plain_text,
        html_body,
    )
    return {"message": "If the account needs verification, an email will be sent."}


@router.post("/forgot-password")
def forgot_password(payload: EmailAddress, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or user.password_hash is None or not user.email_verified:
        return {"message": "If the account can be recovered, a reset email will be sent."}
    token = _create_token(
        db,
        user.id,
        "password_reset",
        _utcnow() + timedelta(minutes=RESET_MINUTES),
    )
    db.commit()
    _send_email(
        email,
        "Reset your ResearchMate password",
        f"Reset your ResearchMate password:\n\n{FRONTEND_URL}/?reset_password={token}\n\n"
        "This link expires in 30 minutes.",
    )
    return {"message": "If the account can be recovered, a reset email will be sent."}


@router.post("/reset-password")
def reset_password(payload: PasswordReset, db: Session = Depends(get_db)):
    token = _consume_token(db, payload.token, "password_reset")
    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="This account no longer exists.")
    user.password_hash = _hash_password(payload.password)
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password reset. You can now sign in."}


@router.get("/google/start")
def google_start(response: Response):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    state = secrets.token_urlsafe(32)
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    redirect = RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        status_code=302,
    )
    redirect.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "").lower() == "true",
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if not state_cookie or not hmac.compare_digest(state, state_cookie):
        raise HTTPException(status_code=400, detail="Google sign-in state is invalid. Try again.")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token.")
        profile_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Google sign-in could not be completed.") from exc

    email = str(profile.get("email", "")).strip().lower()
    google_sub = profile.get("sub")
    if not email or not google_sub or profile.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Google did not provide a verified email address.")

    was_first_verified_account = (
        db.query(User.id).filter(User.email_verified.is_(True)).count() == 0
    )
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None and user.google_sub not in (None, google_sub):
            raise HTTPException(status_code=409, detail="This email is linked to another Google account.")
        if user is None:
            user = User(email=email, google_sub=google_sub, email_verified=True)
            db.add(user)
            db.flush()
        else:
            user.google_sub = google_sub
            user.email_verified = True

    if was_first_verified_account:
        _claim_legacy_papers(db, user.id)

    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
    ).delete(synchronize_session=False)
    session_token = _create_token(
        db,
        user.id,
        "session",
        _utcnow() + timedelta(days=SESSION_DAYS),
    )
    db.commit()

    redirect = RedirectResponse(FRONTEND_URL, status_code=303)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/", samesite="lax")
    _set_session_cookie(redirect, session_token, SESSION_DAYS * 24 * 60 * 60)
    return redirect


def _provider_redirect_uri(provider: str) -> str:
    default_uri = f"http://localhost:8000/auth/{provider}/callback"
    return os.getenv(f"{provider.upper()}_REDIRECT_URI", default_uri)


def _provider_state_cookie(provider: str) -> str:
    return f"{OAUTH_STATE_COOKIE}_{provider}"


def _start_provider_login(
    provider: str,
    authorization_url: str,
    scope: str,
    extra_params: dict[str, str] | None = None,
) -> RedirectResponse:
    client_id = os.getenv(f"{provider.upper()}_CLIENT_ID")
    client_secret = os.getenv(f"{provider.upper()}_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=f"{provider.title()} sign-in is not configured.",
        )

    state = secrets.token_urlsafe(32)
    query = {
        "client_id": client_id,
        "redirect_uri": _provider_redirect_uri(provider),
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    if extra_params:
        query.update(extra_params)
    redirect = RedirectResponse(
        f"{authorization_url}?{urlencode(query)}",
        status_code=302,
    )
    redirect.set_cookie(
        _provider_state_cookie(provider),
        state,
        max_age=600,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "").lower() == "true",
        samesite="lax",
        path="/",
    )
    return redirect


def _complete_provider_login(
    provider: str,
    subject: str,
    email: str,
    state: str,
    state_cookie_name: str,
    request: Request,
    db: Session,
) -> RedirectResponse:
    email = email.strip().lower()
    if not email or not subject:
        raise HTTPException(status_code=403, detail=f"{provider.title()} did not provide a verified email.")

    subject_field = {"github": "github_id", "linkedin": "linkedin_sub"}[provider]
    cookie_state = request.cookies.get(state_cookie_name, "")
    if not cookie_state or not hmac.compare_digest(state, cookie_state):
        raise HTTPException(
            status_code=400,
            detail=f"{provider.title()} sign-in state is invalid. Try again.",
        )

    was_first_verified_account = (
        db.query(User.id).filter(User.email_verified.is_(True)).count() == 0
    )
    user = db.query(User).filter(getattr(User, subject_field) == subject).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        linked_subject = getattr(user, subject_field, None) if user is not None else None
        if linked_subject not in (None, subject):
            raise HTTPException(
                status_code=409,
                detail=f"This email is linked to another {provider.title()} account.",
            )
        if user is None:
            user = User(email=email, email_verified=True)
            db.add(user)
            db.flush()
        else:
            user.email_verified = True
        setattr(user, subject_field, subject)

    if was_first_verified_account:
        _claim_legacy_papers(db, user.id)

    db.query(AuthToken).filter(
        AuthToken.user_id == user.id,
        AuthToken.purpose == "session",
    ).delete(synchronize_session=False)
    session_token = _create_token(
        db,
        user.id,
        "session",
        _utcnow() + timedelta(days=SESSION_DAYS),
    )
    db.commit()

    redirect = RedirectResponse(FRONTEND_URL, status_code=303)
    redirect.delete_cookie(state_cookie_name, path="/", samesite="lax")
    _set_session_cookie(redirect, session_token, SESSION_DAYS * 24 * 60 * 60)
    return redirect


@router.get("/github/start")
def github_start():
    return _start_provider_login(
        "github",
        "https://github.com/login/oauth/authorize",
        "read:user user:email",
    )


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="GitHub sign-in is not configured.")
    try:
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _provider_redirect_uri("github"),
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("GitHub did not return an access token.")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        profile_response = requests.get(
            "https://api.github.com/user",
            headers=headers,
            timeout=15,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        emails_response = requests.get(
            "https://api.github.com/user/emails",
            headers=headers,
            timeout=15,
        )
        emails_response.raise_for_status()
        verified_email = next(
            (
                item.get("email")
                for item in emails_response.json()
                if item.get("verified") is True and item.get("primary") is True
            ),
            None,
        )
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="GitHub sign-in could not be completed.") from exc

    if not verified_email:
        raise HTTPException(status_code=403, detail="GitHub did not provide a verified primary email.")
    return _complete_provider_login(
        "github",
        str(profile.get("id", "")),
        str(verified_email),
        state,
        _provider_state_cookie("github"),
        request,
        db,
    )


@router.get("/linkedin/start")
def linkedin_start():
    return _start_provider_login(
        "linkedin",
        "https://www.linkedin.com/oauth/v2/authorization",
        "openid profile email",
    )


@router.get("/linkedin/callback")
def linkedin_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="LinkedIn sign-in is not configured.")
    try:
        token_response = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _provider_redirect_uri("linkedin"),
            },
            timeout=15,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("LinkedIn did not return an access token.")
        profile_response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="LinkedIn sign-in could not be completed.") from exc

    if profile.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="LinkedIn did not provide a verified email address.")
    return _complete_provider_login(
        "linkedin",
        str(profile.get("sub", "")),
        str(profile.get("email", "")),
        state,
        _provider_state_cookie("linkedin"),
        request,
        db,
    )
