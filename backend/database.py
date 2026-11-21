
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Determine database mode:
# Set DB_MODE=sqlite or USE_SQLITE=true to force local SQLite.
# Default (or DB_MODE=supabase/postgres) uses DATABASE_URL / SUPABASE_CONNECTION_STRING.
db_mode = os.getenv("DB_MODE", "").strip().lower()
use_sqlite = db_mode == "sqlite" or os.getenv("USE_SQLITE", "").strip().lower() in ("true", "1", "yes")

if use_sqlite:
    DATABASE_URL = f"sqlite:///{(BASE_DIR / 'researchmate.db').as_posix()}"
    connect_args = {"check_same_thread": False}
    print("[Database] Using local SQLite: researchmate.db", flush=True)
else:
    raw_url = os.getenv("DATABASE_URL", "").strip() or os.getenv("SUPABASE_CONNECTION_STRING", "").strip()
    if raw_url:
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql://", 1)
        DATABASE_URL = raw_url
        if DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            print("[Database] Using SQLite from DATABASE_URL", flush=True)
        else:
            connect_args = {"sslmode": "require"} if ("localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL and "sslmode=" not in DATABASE_URL) else {}
            host = DATABASE_URL.split("@")[-1].split("/")[0] if "@" in DATABASE_URL else "PostgreSQL"
            print(f"[Database] Using Supabase PostgreSQL: {host}", flush=True)
    else:
        DATABASE_URL = f"sqlite:///{(BASE_DIR / 'researchmate.db').as_posix()}"
        connect_args = {"check_same_thread": False}
        print("[Database] Using fallback local SQLite: researchmate.db", flush=True)

engine_kwargs = {"connect_args": connect_args}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 15,
        "pool_pre_ping": True,
    })

engine = create_engine(
    DATABASE_URL,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
