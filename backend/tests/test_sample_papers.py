import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import auth
import database
import main
from database import Base
from models.research_paper import ResearchPaper
from models.user import User
from services.sample_papers import SAMPLE_PAPERS, seed_sample_papers


class SamplePaperOnboardingTests(unittest.TestCase):
    def _create_test_db(self, root: Path):
        engine = create_engine(
            f"sqlite:///{root / 'sample-papers-test.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        return engine, sessionmaker(bind=engine)

    def test_new_user_registration_seeds_sample_papers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, SessionLocal = self._create_test_db(Path(tmpdir))

            def override_get_db():
                db = SessionLocal()
                try:
                    yield db
                finally:
                    db.close()

            main.app.dependency_overrides[database.get_db] = override_get_db
            try:
                client = TestClient(main.app)
                with patch.object(auth, "_get_verification_email_enabled", return_value=False):
                    resp = client.post(
                        "/auth/register",
                        json={"email": "newuser@example.com", "password": "StrongPassword123!"},
                    )
                self.assertEqual(resp.status_code, 201, resp.text)

                with SessionLocal() as db:
                    user = db.query(User).filter(User.email == "newuser@example.com").one()
                    papers = (
                        db.query(ResearchPaper)
                        .filter(ResearchPaper.user_id == user.id)
                        .order_by(ResearchPaper.id.asc())
                        .all()
                    )
                    self.assertEqual(len(papers), len(SAMPLE_PAPERS))
                    titles = [p.title for p in papers]
                    self.assertIn("Attention Is All You Need", titles)
                    self.assertIn(
                        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                        titles,
                    )
                    for paper in papers:
                        self.assertTrue(paper.is_saved)
                        self.assertTrue(paper.summary)
                        self.assertIsInstance(paper.classification, dict)
                        self.assertIn("metrics", paper.classification)
            finally:
                main.app.dependency_overrides.clear()
                Base.metadata.drop_all(bind=engine)
                engine.dispose()

    def test_seed_sample_papers_is_idempotent_for_existing_users(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, SessionLocal = self._create_test_db(Path(tmpdir))
            try:
                with SessionLocal() as db:
                    user = User(email="existing@example.com", email_verified=True)
                    db.add(user)
                    db.flush()

                    first_seed = seed_sample_papers(db, user.id)
                    db.commit()
                    self.assertEqual(len(first_seed), len(SAMPLE_PAPERS))

                    # Calling again should not duplicate papers
                    second_seed = seed_sample_papers(db, user.id)
                    db.commit()
                    self.assertEqual(second_seed, [])

                    total = (
                        db.query(ResearchPaper)
                        .filter(ResearchPaper.user_id == user.id)
                        .count()
                    )
                    self.assertEqual(total, len(SAMPLE_PAPERS))
            finally:
                Base.metadata.drop_all(bind=engine)
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
