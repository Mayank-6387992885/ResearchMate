import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from auth import get_current_user
from database import get_db
from routers import papers_extras
from services.backup_service import create_database_backup


def test_create_database_backup_and_retention(tmp_path):
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO items (name) VALUES ('alpha')")
        conn.commit()

    backup_dir = tmp_path / "backups"
    backup_path = create_database_backup(db_path=db_file, backup_dir=backup_dir, keep_last=2)
    assert backup_path.exists()
    with sqlite3.connect(str(backup_path)) as bconn:
        rows = bconn.execute("SELECT name FROM items").fetchall()
        assert rows == [("alpha",)]


def test_pdf_export_endpoint(monkeypatch):
    fake_user = SimpleNamespace(id=1, email="prod_test@example.com")
    fake_paper = SimpleNamespace(
        id=42,
        title="Productivity Test Paper",
        category="AI",
        pages=3,
        summary="This is a test summary for PDF export.",
    )
    monkeypatch.setattr(papers_extras.paper_service, "get_paper_or_404", lambda db, pid, uid: fake_paper)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = lambda: None
    try:
        client = TestClient(app)
        pdf_res = client.get("/api/papers/42/export-pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()
