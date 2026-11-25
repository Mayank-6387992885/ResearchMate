"""Unit tests for semantic search service and /papers/search endpoints."""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("USE_SQLITE", "true")

from auth import get_current_user  # noqa: E402
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from models.paper_embedding import PaperEmbedding  # noqa: E402
from models.research_paper import ResearchPaper  # noqa: E402
from models.user import User  # noqa: E402
import services.semantic_search as semantic_search  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        user = User(email="researcher@example.com", username="researcher")
        db.add(user)
        db.commit()
        db.refresh(user)

        papers = [
            ResearchPaper(
                title="Attention Is All You Need",
                filename="attention.pdf",
                stored_filename="attention.pdf",
                file_path="user-1/attention.pdf",
                summary="We propose the Transformer, a neural network architecture based solely on self-attention mechanisms for sequence transduction.",
                pages=15,
                user_id=user.id,
                category="Technology",
                classification={"research_domains": ["Natural Language Processing"]},
            ),
            ResearchPaper(
                title="CRISPR-Cas9 Gene Editing",
                filename="crispr.pdf",
                stored_filename="crispr.pdf",
                file_path="user-1/crispr.pdf",
                summary="A programmable RNA-guided endonuclease system for targeted genome engineering in eukaryotic cells.",
                pages=12,
                user_id=user.id,
                category="Importance",
                classification={"research_domains": ["Genomics"]},
            ),
            ResearchPaper(
                title="Quantum Error Correction",
                filename="quantum.pdf",
                stored_filename="quantum.pdf",
                file_path="user-1/quantum.pdf",
                summary="Surface codes and stabilizer measurements protect logical qubits from decoherence in fault-tolerant quantum computing.",
                pages=20,
                user_id=user.id,
                category="Technology",
                classification={"research_domains": ["Quantum Computing"]},
            ),
        ]
        db.add_all(papers)
        db.commit()
        yield db, user
    finally:
        db.close()


def test_tfidf_fallback_when_ollama_unavailable(db_session, monkeypatch):
    db, user = db_session
    monkeypatch.setattr(semantic_search, "fetch_ollama_embedding", lambda *args, **kwargs: None)

    papers = db.query(ResearchPaper).filter(ResearchPaper.user_id == user.id).all()
    ranked, backend = semantic_search.semantic_search_papers(
        db, papers, query="transformer self-attention neural architecture", mode="semantic"
    )

    assert backend == "tfidf"
    assert len(ranked) == 3
    assert ranked[0]["paper"].title == "Attention Is All You Need"
    assert ranked[0]["score"] > ranked[1]["score"]
    assert "self-attention" in ranked[0]["snippet"].lower()


def test_ollama_embeddings_and_caching(db_session, monkeypatch):
    db, user = db_session
    calls = []

    def fake_ollama(text: str, model: str = "nomic-embed-text"):
        calls.append(text)
        lower = text.lower()
        if "genome" in lower or "crispr" in lower or "gene" in lower:
            return [1.0, 0.0, 0.0]
        if "quantum" in lower or "qubit" in lower:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    monkeypatch.setattr(semantic_search, "fetch_ollama_embedding", fake_ollama)

    papers = db.query(ResearchPaper).filter(ResearchPaper.user_id == user.id).all()
    ranked, backend = semantic_search.semantic_search_papers(
        db, papers, query="CRISPR genome editing", mode="semantic"
    )

    assert backend == "ollama"
    assert ranked[0]["paper"].title == "CRISPR-Cas9 Gene Editing"
    assert ranked[0]["score"] == 1.0
    assert db.query(PaperEmbedding).count() == 3

    # Second search should reuse cached paper embeddings (only 1 call for the query)
    calls.clear()
    ranked2, backend2 = semantic_search.semantic_search_papers(
        db, papers, query="quantum qubits", mode="semantic"
    )
    assert backend2 == "ollama"
    assert ranked2[0]["paper"].title == "Quantum Error Correction"
    assert len(calls) == 1


def test_search_endpoints_return_ranked_papers(db_session, monkeypatch):
    db, user = db_session
    monkeypatch.setattr(semantic_search, "fetch_ollama_embedding", lambda *args, **kwargs: None)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        client = TestClient(app)
        for path in ("/papers/search", "/api/papers/search"):
            resp = client.get(path, params={"q": "fault-tolerant qubits", "mode": "semantic"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["mode"] == "semantic"
            assert data["backend"] == "tfidf"
            assert data["total"] == 3
            assert data["papers"][0]["title"] == "Quantum Error Correction"
            assert "relevance_score" in data["papers"][0]
            assert "snippet" in data["papers"][0]
    finally:
        app.dependency_overrides.clear()
