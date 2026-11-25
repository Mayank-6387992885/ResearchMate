import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def create_database_backup(
    db_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
    keep_last: int = 10,
) -> Path:
    """Create a consistent online backup of the SQLite database and prune old backups."""
    if db_path is None:
        env_url = os.getenv("DATABASE_URL", "sqlite:///./researchmate.db")
        if not env_url.startswith("sqlite:///"):
            raise ValueError("Automated local backup only supports SQLite databases.")
        db_path = Path(env_url.replace("sqlite:///", "", 1))
    else:
        db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    target_dir = Path(backup_dir) if backup_dir else db_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = target_dir / f"{db_path.stem}_{timestamp}.db"

    with sqlite3.connect(str(db_path)) as src_conn:
        with sqlite3.connect(str(backup_path)) as dst_conn:
            src_conn.backup(dst_conn)

    if keep_last > 0:
        backups = sorted(
            target_dir.glob(f"{db_path.stem}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep_last:]:
            old_backup.unlink(missing_ok=True)

    return backup_path
