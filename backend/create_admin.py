#!/usr/bin/env python3
"""CLI utility to create or promote an administrator account in ResearchMate.

Usage:
    python create_admin.py
    python create_admin.py --email admin@researchmate.com --password "YourStrongPassword123"
"""

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal, Base, engine
from models.user import User


def hash_password(password: str) -> str:
    """Hash a password using the same scrypt configuration as auth.py."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def add_to_admin_emails(email: str) -> None:
    """Add email to ADMIN_EMAILS in backend/.env if not already present."""
    env_path = BACKEND_DIR / ".env"
    normalized = email.strip().lower()
    if not env_path.exists():
        env_path.write_text(f"ADMIN_EMAILS={normalized}\n", encoding="utf-8")
        os.environ["ADMIN_EMAILS"] = normalized
        return

    content = env_path.read_text(encoding="utf-8")
    match = re.search(r"^ADMIN_EMAILS\s*=\s*(.*)$", content, flags=re.MULTILINE)
    if match:
        existing = [e.strip().lower() for e in match.group(1).split(",") if e.strip()]
        if normalized not in existing:
            existing.append(normalized)
            new_val = ",".join(existing)
            new_content = re.sub(
                r"^ADMIN_EMAILS\s*=.*$",
                f"ADMIN_EMAILS={new_val}",
                content,
                flags=re.MULTILINE,
            )
            env_path.write_text(new_content, encoding="utf-8")
            os.environ["ADMIN_EMAILS"] = new_val
    else:
        new_content = content.rstrip() + f"\nADMIN_EMAILS={normalized}\n"
        env_path.write_text(new_content, encoding="utf-8")
        os.environ["ADMIN_EMAILS"] = normalized


def create_or_update_admin(email: str, password: str, full_name: str = "System Administrator") -> User:
    normalized_email = email.strip().lower()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == normalized_email).first()
        hashed = hash_password(password)

        if user is None:
            user = User(
                email=normalized_email,
                password_hash=hashed,
                email_verified=True,
                username=normalized_email.split("@")[0].replace(".", "_")[:30],
                profile_data=json.dumps({"full_name": full_name}),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            action = "created"
        else:
            user.password_hash = hashed
            user.email_verified = True
            db.commit()
            db.refresh(user)
            action = "updated"

        add_to_admin_emails(normalized_email)
        return user, action


def main():
    parser = argparse.ArgumentParser(description="Create or update an administrator account for ResearchMate.")
    parser.add_argument("--email", default=None, help="Admin email address")
    parser.add_argument("--password", default=None, help="Admin account password (min 10 characters)")
    parser.add_argument("--name", default="Administrator", help="Admin display name")

    args = parser.parse_args()

    email = args.email
    if not email:
        if sys.stdin.isatty():
            email = input("Enter admin email address: ").strip()
        else:
            email = "admin@researchmate.com"

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("[Error] Please enter a valid email address.", file=sys.stderr)
        sys.exit(1)

    password = args.password
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass("Enter admin password (min 10 characters): ").strip()
        else:
            password = "Admin@ResearchMate2026"

    if len(password) < 10:
        print("[Error] Password must be at least 10 characters.", file=sys.stderr)
        sys.exit(1)

    user, action = create_or_update_admin(email, password, args.name)

    print("\n" + "=" * 60)
    print(f" [SUCCESS] Administrator Account {action.upper()}!")
    print("=" * 60)
    print(f"  Email:        {user.email}")
    print(f"  Password:     {'*' * len(password)} (saved securely)")
    print(f"  Status:       Email Verified (Immediate Access)")
    print(f"  Role:         Administrator (Full Access)")
    print("=" * 60)
    print(" You can now sign in at http://localhost:5173 with these credentials.")
    print(" Admin settings are available in Settings -> Account & Security.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
