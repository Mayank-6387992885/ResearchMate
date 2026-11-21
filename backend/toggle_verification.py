#!/usr/bin/env python3
"""CLI command to inspect and toggle email verification requirement across ResearchMate.

Usage:
    python toggle_verification.py status
    python toggle_verification.py on       # Require email verification
    python toggle_verification.py off      # Disable email verification (bypass completely)
    python toggle_verification.py off --verify-all  # Disable and mark existing users as verified
    python toggle_verification.py toggle   # Flip current state
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Ensure backend directory is in Python path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal, Base, engine
from models.app_setting import AppSetting
from models.user import User


def sync_env_file(enabled: bool) -> None:
    """Keep backend/.env in sync with the email verification setting."""
    env_path = BACKEND_DIR / ".env"
    val_str = "true" if enabled else "false"
    if not env_path.exists():
        example_path = BACKEND_DIR / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text(f"SEND_VERIFICATION_EMAIL={val_str}\n", encoding="utf-8")
            return

    try:
        content = env_path.read_text(encoding="utf-8")
        if re.search(r"^SEND_VERIFICATION_EMAIL\s*=", content, flags=re.MULTILINE):
            new_content = re.sub(
                r"^SEND_VERIFICATION_EMAIL\s*=.*$",
                f"SEND_VERIFICATION_EMAIL={val_str}",
                content,
                flags=re.MULTILINE,
            )
        else:
            new_content = content.rstrip() + f"\nSEND_VERIFICATION_EMAIL={val_str}\n"
        env_path.write_text(new_content, encoding="utf-8")
        os.environ["SEND_VERIFICATION_EMAIL"] = val_str
    except Exception as exc:
        print(f"[Warning] Could not update backend/.env: {exc}", file=sys.stderr)


def get_verification_state(db) -> tuple[bool, str]:
    """Return (is_enabled, source_description)."""
    setting = db.get(AppSetting, "send_verification_email")
    if setting is not None:
        enabled = setting.value.strip().lower() == "true"
        return enabled, "database (application_settings)"
    
    env_val = os.getenv("SEND_VERIFICATION_EMAIL", "false").strip().lower()
    enabled = env_val not in {"false", "0", "no", "off"}
    return enabled, "environment (SEND_VERIFICATION_EMAIL)"


def set_verification_state(db, enabled: bool, verify_all: bool = False) -> tuple[int, int]:
    """Set verification state in database and update .env. Returns (verified_count, total_unverified)."""
    val_str = "true" if enabled else "false"
    setting = db.get(AppSetting, "send_verification_email")
    if setting is None:
        setting = AppSetting(key="send_verification_email", value=val_str)
        db.add(setting)
    else:
        setting.value = val_str

    verified_count = 0
    unverified_users = db.query(User).filter(User.email_verified.is_(False)).all()
    total_unverified = len(unverified_users)

    if verify_all:
        for user in unverified_users:
            user.email_verified = True
        verified_count = len(unverified_users)

    db.commit()
    sync_env_file(enabled)
    return verified_count, total_unverified


def print_status(db) -> None:
    enabled, source = get_verification_state(db)
    total_users = db.query(User).count()
    verified_users = db.query(User).filter(User.email_verified.is_(True)).count()
    unverified_users = db.query(User).filter(User.email_verified.is_(False)).count()
    env_val = os.getenv("SEND_VERIFICATION_EMAIL", "(not set)")

    status_badge = "[ENABLED]" if enabled else "[DISABLED]"
    print("=" * 60)
    print(f" ResearchMate - Email Verification Status: {status_badge}")
    print("=" * 60)
    print(f"  Current Setting:      {'REQUIRED (Enabled)' if enabled else 'NOT NEEDED (Disabled / Bypassed)'}")
    print(f"  Active Source:        {source}")
    print(f"  Env SEND_VERIFICATION: {env_val}")
    print("-" * 60)
    print(f"  Total User Accounts:  {total_users}")
    print(f"  Verified Accounts:    {verified_users}")
    print(f"  Unverified Accounts:  {unverified_users}")
    print("=" * 60)
    if not enabled:
        print("  * Email verification is disabled.")
        print("  * New registrations are verified immediately.")
        print("  * Existing users can log in without email confirmation.")
        print("  * SMTP is NOT required for signups.")
    else:
        print("  * Email verification is required.")
        print("  * New registrations receive a confirmation email link.")
        print("  * Working SMTP settings are required in backend/.env.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Command whether email verification is needed or not in ResearchMate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python toggle_verification.py status          # Check current verification status
  python toggle_verification.py off             # Disable verification project-wide
  python toggle_verification.py off --verify-all # Disable & verify existing accounts
  python toggle_verification.py on              # Require verification project-wide
  python toggle_verification.py toggle          # Flip current state
        """,
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "on", "enable", "true", "1", "off", "disable", "false", "0", "toggle"],
        help="Action to perform (default: status)",
    )
    parser.add_argument(
        "--verify-all",
        action="store_true",
        help="Also mark all currently unverified user accounts as verified in the database",
    )

    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        action = args.action.lower()

        if action == "status":
            print_status(db)
            return

        if action in {"on", "enable", "true", "1"}:
            set_verification_state(db, True, verify_all=args.verify_all)
            print("\n[SUCCESS] Email verification is now ENABLED project-wide.")
            print("New registrations will require email verification via SMTP.\n")
            print_status(db)

        elif action in {"off", "disable", "false", "0"}:
            verified_count, remaining_unverified = set_verification_state(
                db, False, verify_all=args.verify_all
            )
            print("\n[SUCCESS] Email verification is now DISABLED project-wide.")
            print("Users can sign up and sign in immediately without email confirmation.")
            if args.verify_all:
                print(f"Marked {verified_count} existing unverified account(s) as verified.")
            elif remaining_unverified > 0:
                print(f"Note: {remaining_unverified} existing unverified user(s) can now log in directly and will be auto-verified upon sign-in.")
            print()
            print_status(db)

        elif action == "toggle":
            current, _ = get_verification_state(db)
            new_state = not current
            verified_count, _ = set_verification_state(db, new_state, verify_all=args.verify_all)
            print(f"\n[SUCCESS] Email verification toggled to: {'ENABLED' if new_state else 'DISABLED'}.")
            if not new_state and args.verify_all:
                print(f"Marked {verified_count} existing unverified account(s) as verified.")
            print()
            print_status(db)


if __name__ == "__main__":
    main()
