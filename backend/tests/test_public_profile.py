import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from database import Base, get_db  # noqa: E402
from models.research_paper import ResearchPaper  # noqa: E402
from models.user import User  # noqa: E402


def test_public_profile_returns_display_name_and_saved_papers(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pub_profile.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    user = User(
        email="alice@research.org",
        password_hash="x",
        privacy_settings={"public_profile": True},
    )
    private_user = User(
        email="bob@research.org",
        password_hash="x",
        privacy_settings={"public_profile": False},
    )
    db.add_all([user, private_user])
    db.commit()
    db.refresh(user)
    db.refresh(private_user)

    db.add(
        ResearchPaper(
            user_id=user.id,
            title="Public Paper",
            filename="pub.pdf",
            stored_filename="pub.pdf",
            file_path=str(tmp_path / "pub.pdf"),
            summary="Summary",
            pages=10,
            category="Technology",
            is_saved=True,
        )
    )
    db.commit()

    def override_db():
        try:
            yield db
        finally:
            pass

    main.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(main.app) as client:
            res = client.get(f"/api/users/{user.id}/public-profile")
            assert res.status_code == 200
            data = res.json()
            assert data["display_name"] == "alice"
            assert data["saved_papers_count"] == 1
            assert data["saved_papers"][0]["title"] == "Public Paper"
            assert "email" not in data

            private_res = client.get(f"/api/users/{private_user.id}/public-profile")
            assert private_res.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
