"""Unit tests for arXiv / DOI direct import."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pymupdf
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_import.db")

import main  # noqa: E402
from auth import get_current_user  # noqa: E402
from services import import_service  # noqa: E402


def _make_sample_pdf_bytes(text: str = "Attention Is All You Need") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


ARXIV_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture, the Transformer.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


def test_parse_identifier_variants():
    assert import_service.parse_identifier("2301.07041") == ("arxiv", "2301.07041")
    assert import_service.parse_identifier("https://arxiv.org/abs/2301.07041v2") == ("arxiv", "2301.07041v2")
    assert import_service.parse_identifier("https://arxiv.org/pdf/2301.07041.pdf") == ("arxiv", "2301.07041")
    assert import_service.parse_identifier("arXiv:2301.07041") == ("arxiv", "2301.07041")
    assert import_service.parse_identifier("10.1038/s41586-021-03819-2") == ("doi", "10.1038/s41586-021-03819-2")
    assert import_service.parse_identifier("https://doi.org/10.1038/s41586-021-03819-2") == (
        "doi",
        "10.1038/s41586-021-03819-2",
    )


def test_fetch_arxiv_metadata_and_pdf():
    pdf_bytes = _make_sample_pdf_bytes()
    xml_resp = MagicMock(status_code=200, text=ARXIV_ATOM_XML)
    xml_resp.raise_for_status.return_value = None
    pdf_resp = MagicMock(
        status_code=200,
        content=pdf_bytes,
        headers={"content-type": "application/pdf"},
    )
    pdf_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = [xml_resp, pdf_resp]

    with patch("services.import_service.httpx.Client", return_value=mock_client):
        imported = import_service.fetch_paper_from_identifier("https://arxiv.org/abs/1706.03762")

    assert imported.source == "arxiv"
    assert imported.identifier == "1706.03762"
    assert imported.title == "Attention Is All You Need"
    assert imported.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert imported.year == 2017
    assert "Transformer" in imported.abstract
    assert imported.pdf_content == pdf_bytes


def test_fetch_doi_metadata_and_open_access_pdf():
    pdf_bytes = _make_sample_pdf_bytes("AlphaFold paper")
    crossref_resp = MagicMock(status_code=200)
    crossref_resp.raise_for_status.return_value = None
    crossref_resp.json.return_value = {
        "message": {
            "title": ["Highly accurate protein structure prediction with AlphaFold"],
            "author": [{"given": "John", "family": "Jumper"}],
            "published-print": {"date-parts": [[2021, 7, 15]]},
            "abstract": "<jats:p>Proteins are essential to life.</jats:p>",
            "link": [{"content-type": "application/pdf", "URL": "https://example.org/alphafold.pdf"}],
        }
    }
    pdf_resp = MagicMock(
        status_code=200,
        content=pdf_bytes,
        headers={"content-type": "application/pdf"},
    )
    pdf_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = [crossref_resp, pdf_resp]

    with patch("services.import_service.httpx.Client", return_value=mock_client):
        imported = import_service.fetch_paper_from_identifier("10.1038/s41586-021-03819-2")

    assert imported.source == "doi"
    assert imported.title == "Highly accurate protein structure prediction with AlphaFold"
    assert imported.authors == ["John Jumper"]
    assert imported.year == 2021
    assert imported.abstract == "Proteins are essential to life."
    assert imported.pdf_content == pdf_bytes


def test_import_endpoint_runs_pipeline():
    pdf_bytes = _make_sample_pdf_bytes("Imported paper text")
    fake_imported = import_service.ImportedPaper(
        source="arxiv",
        identifier="2301.07041",
        title="Sample Imported Paper",
        authors=["Jane Doe"],
        year=2023,
        abstract="Sample abstract.",
        pdf_url="https://arxiv.org/pdf/2301.07041.pdf",
        pdf_content=pdf_bytes,
        filename="Sample_Imported_Paper.pdf",
    )
    fake_paper = SimpleNamespace(
        id=42,
        title="Sample Imported Paper",
        filename="Sample_Imported_Paper.pdf",
        summary="Mocked summary",
        pages=1,
        is_saved=False,
        category="Technology",
        classification={},
        uploaded_at=None,
        updated_at=None,
    )

    main.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, email="test@example.com")
    try:
        with (
            patch("main.import_service.fetch_paper_from_identifier", return_value=fake_imported),
            patch("main.extract_paper_figures", return_value=[]),
            patch("main.summarize_paper", return_value="Mocked summary"),
            patch("main.extract_research_metrics", return_value={}),
            patch("main.classify_research_paper", return_value={"domain": ["AI"]}),
            patch("main.paper_service.create_paper", return_value=fake_paper),
            patch("main.paper_service.update_paper", return_value=fake_paper),
        ):
            with TestClient(main.app) as client:
                response = client.post(
                    "/api/papers/import",
                    json={"identifier": "2301.07041"},
                )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 42
    assert data["summary"] == "Mocked summary"
    assert data["import_metadata"]["source"] == "arxiv"
    assert data["import_metadata"]["identifier"] == "2301.07041"
    assert data["import_metadata"]["authors"] == ["Jane Doe"]
