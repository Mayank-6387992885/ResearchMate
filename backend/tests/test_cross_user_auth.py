import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from auth import get_current_user  # noqa: E402
from database import Base, get_db  # noqa: E402
from models.research_paper import ResearchPaper  # noqa: E402
from models.user import User  # noqa: E402


def test_cross_user_cannot_access_or_modify_another_users_paper(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cross_user.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    owner = User(email="owner@example.com", password_hash="x")
    intruder = User(email="intruder@example.com", password_hash="x")
    db.add_all([owner, intruder])
    db.commit()
    db.refresh(owner)
    db.refresh(intruder)

    paper = ResearchPaper(
        user_id=owner.id,
        title="Owner Private Paper",
        filename="private.pdf",
        stored_filename="private.pdf",
        file_path=str(tmp_path / "private.pdf"),
        summary="Confidential summary",
        pages=5,
        is_saved=True,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    def override_db():
        try:
            yield db
        finally:
            pass

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[get_current_user] = lambda: intruder

    try:
        with TestClient(main.app) as client:
            assert client.get(f"/papers/{paper.id}").status_code == 404
            assert client.get(f"/papers/{paper.id}/citation").status_code == 404
            assert client.post(f"/papers/{paper.id}/chat", json={"question": "What is this?"}).status_code == 404
            assert client.delete(f"/papers/{paper.id}").status_code == 404
    finally:
        main.app.dependency_overrides.clear()
