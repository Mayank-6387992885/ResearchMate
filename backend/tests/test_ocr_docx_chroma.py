from types import SimpleNamespace

import fitz
from fastapi.testclient import TestClient

from auth import get_current_user
from database import get_db
from main import app
from routers import papers_extras
from services.chroma_service import ChromaVectorStore
from services.pdf_service import ocr_page_with_tesseract


def test_ocr_page_with_tesseract_graceful_fallback(monkeypatch):
    doc = fitz.open()
    page = doc.new_page()
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda img: "Scanned OCR Text")
    assert ocr_page_with_tesseract(page) == "Scanned OCR Text"
    doc.close()


def test_docx_export_endpoint(monkeypatch):
    fake_user = SimpleNamespace(id=1, email="docx_test@example.com")
    fake_paper = SimpleNamespace(
        id=99,
        title="DOCX Export Paper",
        category="ML",
        pages=5,
        summary="Summary content for DOCX export.",
    )
    monkeypatch.setattr(papers_extras.paper_service, "get_paper_or_404", lambda db, pid, uid: fake_paper)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = lambda: None
    try:
        client = TestClient(app)
        res = client.get("/api/papers/99/export-docx")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert res.content[:2] == b"PK"  # DOCX is a ZIP archive
    finally:
        app.dependency_overrides.clear()


def test_chroma_vector_store_upsert_and_query():
    store = ChromaVectorStore(collection_name="test_researchmate_chunks")
    count = store.upsert_paper_chunks(
        paper_id=7,
        chunks=["Transformers use self-attention.", "CNNs use spatial convolutions."],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    assert count == 2
    results = store.query_paper_chunks(query_embedding=[0.9, 0.1, 0.0], paper_id=7, n_results=1)
    assert results["documents"][0][0] == "Transformers use self-attention."
