from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from auth import get_current_user
from models.research_paper import ResearchPaper
from models.user import User
from services.citation_service import format_citation


def test_format_bibtex_with_full_metadata():
    paper = SimpleNamespace(
        id=42,
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017,
        doi="10.48550/arXiv.1706.03762",
        arxiv_id="1706.03762",
        pages=15,
        journal="NeurIPS",
    )
    content, media_type, ext = format_citation(paper, "bibtex")
    assert ext == "bib"
    assert "bibtex" in media_type
    assert "@article{vaswani2017_42," in content
    assert "author = {Ashish Vaswani and Noam Shazeer}" in content
    assert "title = {Attention Is All You Need}" in content
    assert "year = {2017}" in content
    assert "doi = {10.48550/arXiv.1706.03762}" in content
    assert "eprint = {1706.03762}" in content
    assert "pages = {1--15}" in content
    assert "journal = {NeurIPS}" in content


def test_format_ris_with_fallbacks():
    paper = SimpleNamespace(
        id=7,
        title="Minimal Paper",
        pages=0,
        uploaded_at=datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    content, media_type, ext = format_citation(paper, "ris")
    assert ext == "ris"
    assert "research-info-systems" in media_type
    assert "TY  - JOUR" in content
    assert "AU  - Unknown Author" in content
    assert "TI  - Minimal Paper" in content
    assert "PY  - 2025" in content
    assert "ER  - " in content


def test_format_apa_multiple_authors_and_doi():
    paper = SimpleNamespace(
        id=3,
        title="Deep Residual Learning",
        authors=["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren"],
        year=2016,
        doi="10.1109/CVPR.2016.90",
    )
    content, media_type, ext = format_citation(paper, "apa")
    assert ext == "txt"
    assert "text/plain" in media_type
    assert "Kaiming He, Xiangyu Zhang, & Shaoqing Ren (2016). Deep Residual Learning. https://doi.org/10.1109/CVPR.2016.90" in content


def test_format_invalid_raises_422():
    paper = SimpleNamespace(id=1, title="Test")
    with pytest.raises(HTTPException) as exc_info:
        format_citation(paper, "mla")
    assert exc_info.value.status_code == 422


def test_citation_endpoint_returns_bibtex_ris_apa(tmp_path):
    db_path = tmp_path / "test_citation.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    user = User(email="cite@example.com", password_hash="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)

    paper = ResearchPaper(
        title="Graph Neural Networks",
        filename="gnn.pdf",
        stored_filename="gnn_stored.pdf",
        file_path=str(tmp_path / "gnn_stored.pdf"),
        summary="A summary.",
        pages=10,
        user_id=user.id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        client = TestClient(app)

        res_bib = client.get(f"/papers/{paper.id}/citation?format=bibtex")
        assert res_bib.status_code == 200
        assert "@article{" in res_bib.text
        assert "Graph Neural Networks" in res_bib.text
        assert ".bib" in res_bib.headers.get("content-disposition", "")

        res_ris = client.get(f"/papers/{paper.id}/citation?format=ris")
        assert res_ris.status_code == 200
        assert "TY  - JOUR" in res_ris.text
        assert ".ris" in res_ris.headers.get("content-disposition", "")

        res_apa = client.get(f"/papers/{paper.id}/citation?format=apa")
        assert res_apa.status_code == 200
        assert "Graph Neural Networks." in res_apa.text

        res_bad = client.get(f"/papers/{paper.id}/citation?format=chicago")
        assert res_bad.status_code == 422

        res_missing = client.get("/papers/99999/citation?format=bibtex")
        assert res_missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()
