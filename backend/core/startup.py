import threading
import time

from sqlalchemy import inspect, text

from database import Base, SessionLocal, engine
from models.progress_task import ProgressTask
from services.progress_service import process_is_running


def init_database_and_tasks() -> None:
    """Create/migrate SQLite tables on startup and reconcile interrupted tasks."""
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
        try:
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names())

            if "research_papers" in existing_tables:
                paper_columns = {c["name"] for c in inspector.get_columns("research_papers")}
                with engine.begin() as connection:
                    if "category" not in paper_columns:
                        connection.execute(text("ALTER TABLE research_papers ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'Uncategorized'"))
                    if "classification" not in paper_columns:
                        connection.execute(text("ALTER TABLE research_papers ADD COLUMN classification JSON NOT NULL DEFAULT '{}'"))
                    if "updated_at" not in paper_columns:
                        connection.execute(text("ALTER TABLE research_papers ADD COLUMN updated_at TIMESTAMP"))
                    if "user_id" not in paper_columns:
                        connection.execute(text("ALTER TABLE research_papers ADD COLUMN user_id INTEGER REFERENCES users(id)"))

            if "users" in existing_tables:
                user_columns = {c["name"] for c in inspector.get_columns("users")}
                with engine.begin() as connection:
                    if "github_id" not in user_columns:
                        connection.execute(text("ALTER TABLE users ADD COLUMN github_id VARCHAR(255)"))
                    if "linkedin_sub" not in user_columns:
                        connection.execute(text("ALTER TABLE users ADD COLUMN linkedin_sub VARCHAR(255)"))
                    if "phone_number" not in user_columns:
                        connection.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(16)"))
                    if "phone_verified" not in user_columns:
                        connection.execute(text("ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT FALSE"))
                    for col, col_def in {
                        "username": "VARCHAR(30)",
                        "profile_data": "TEXT NOT NULL DEFAULT '{}'",
                        "profile_image": "BYTEA",
                        "profile_image_type": "VARCHAR(32)",
                        "notification_preferences": "TEXT NOT NULL DEFAULT '{}'",
                        "privacy_settings": "TEXT NOT NULL DEFAULT '{}'",
                    }.items():
                        if col not in user_columns:
                            connection.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_def}"))

            if "sms_verifications" in existing_tables:
                sms_cols = {c["name"] for c in inspector.get_columns("sms_verifications")}
                if "used_at" not in sms_cols:
                    with engine.begin() as connection:
                        connection.execute(text("ALTER TABLE sms_verifications ADD COLUMN used_at TIMESTAMP"))

            if "progress_tasks" in existing_tables:
                prog_cols = {c["name"] for c in inspector.get_columns("progress_tasks")}
                with engine.begin() as connection:
                    if "started_at" not in prog_cols:
                        connection.execute(text("ALTER TABLE progress_tasks ADD COLUMN started_at FLOAT"))
                    if "owner_user_id" not in prog_cols:
                        connection.execute(text("ALTER TABLE progress_tasks ADD COLUMN owner_user_id INTEGER"))
        except Exception as exc:
            print(f"[Database] SQLite migration notice: {exc}", flush=True)

    def _background_init():
        try:
            with SessionLocal() as db:
                interrupted = db.query(ProgressTask).filter(ProgressTask.status == "processing").all()
                for task in interrupted:
                    if not process_is_running(getattr(task, "owner_pid", None)):
                        setattr(task, "status", "error")
                        setattr(task, "message", "Backend stopped before this analysis completed.")
                        setattr(task, "updated_at", time.time())
                db.commit()
                print("[Startup] Database connection warmed and tasks reconciled.", flush=True)
        except Exception as exc:
            print(f"[Startup] Background init notice: {exc}", flush=True)

    threading.Thread(target=_background_init, daemon=True).start()
