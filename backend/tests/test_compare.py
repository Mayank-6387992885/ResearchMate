import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth import get_current_user
from database import Base, get_db
from main import app
from models.research_paper import ResearchPaper
from models.user import User


class ComparePapersEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "compare_test.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        with self.SessionLocal() as db:
            user = User(email="compare@example.com", email_verified=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            self.user_id = user.id

            p1 = ResearchPaper(
                title="Attention Is All You Need",
                filename="attention.pdf",
                stored_filename="attention.pdf",
                file_path="user-1/attention.pdf",
                summary="Introduces the Transformer architecture using self-attention.",
                pages=15,
                user_id=user.id,
                category="Technology",
                classification={"research_domains": ["NLP"], "methodologies": ["Transformer"]},
            )
            p2 = ResearchPaper(
                title="BERT Pre-training",
                filename="bert.pdf",
                stored_filename="bert.pdf",
                file_path="user-1/bert.pdf",
                summary="Bidirectional encoder representations from Transformers.",
                pages=16,
                user_id=user.id,
                category="Technology",
                classification={"research_domains": ["NLP"], "methodologies": ["Pre-training"]},
            )
            db.add_all([p1, p2])
            db.commit()
            db.refresh(p1)
            db.refresh(p2)
            self.paper_ids = [p1.id, p2.id]

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_get_current_user():
            with self.SessionLocal() as db:
                return db.query(User).filter(User.id == self.user_id).first()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_compare_papers_success(self):
        mock_response = json.dumps({
            "papers": [
                {
                    "id": self.paper_ids[0],
                    "title": "Attention Is All You Need",
                    "methodology": "Encoder-decoder with multi-head self-attention",
                    "datasets": "WMT 2014 EN-DE, EN-FR",
                    "key_metrics": "28.4 BLEU (EN-DE)",
                    "strengths": "Parallelizable training",
                    "limitations": "Quadratic attention complexity",
                },
                {
                    "id": self.paper_ids[1],
                    "title": "BERT Pre-training",
                    "methodology": "Masked language modeling on bidirectional Transformer",
                    "datasets": "GLUE, SQuAD v1.1",
                    "key_metrics": "93.2 F1 on SQuAD",
                    "strengths": "Strong transfer learning",
                    "limitations": "High pre-training compute",
                },
            ],
            "synthesis": "Both papers rely on Transformers, shifting from sequence-to-sequence translation to bidirectional pre-training.",
        })

        with patch("summarizer.stream_ollama", return_value=mock_response) as mock_llm:
            res = self.client.post("/api/papers/compare", json={"paper_ids": self.paper_ids})

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["papers"]), 2)
        self.assertEqual(data["papers"][0]["methodology"], "Encoder-decoder with multi-head self-attention")
        self.assertEqual(data["papers"][1]["key_metrics"], "93.2 F1 on SQuAD")
        self.assertIn("Transformers", data["synthesis"])
        mock_llm.assert_called_once()

    def test_compare_papers_rejects_fewer_than_two_ids(self):
        res = self.client.post("/api/papers/compare", json={"paper_ids": [self.paper_ids[0]]})
        self.assertEqual(res.status_code, 422)

    def test_compare_papers_rejects_duplicate_ids(self):
        res = self.client.post(
            "/api/papers/compare",
            json={"paper_ids": [self.paper_ids[0], self.paper_ids[0]]},
        )
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
