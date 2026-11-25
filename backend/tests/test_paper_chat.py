"""Unit tests for RAG-based paper Q&A (services/paper_chat.py and /papers/{id}/chat)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

import auth
import main
import services.paper_service as paper_service
from services.paper_chat import (
    PaperChunk,
    answer_paper_question,
    extract_chunks_from_pdf,
    retrieve_relevant_chunks,
)


def _build_pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    return doc.tobytes()


class PaperChatUnitTests(unittest.TestCase):
    def test_extract_chunks_from_pdf_tracks_pages_and_sections(self):
        pdf_bytes = _build_pdf_bytes([
            "Abstract\nThis paper introduces a transformer model for protein folding.",
            "2. Methods\nWe trained the model on 10,000 protein structures using AdamW.",
        ])
        chunks = extract_chunks_from_pdf(pdf_bytes, chunk_size=500, overlap=50)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].page, 1)
        self.assertEqual(chunks[0].section, "Abstract")
        self.assertEqual(chunks[1].page, 2)
        self.assertEqual(chunks[1].section, "2. Methods")

    def test_retrieve_relevant_chunks_ranks_matching_chunk_first(self):
        chunks = [
            PaperChunk(0, 1, "Introduction", "Background on climate modeling and ocean currents."),
            PaperChunk(1, 2, "Methods", "We used a convolutional neural network with learning rate 0.001."),
            PaperChunk(2, 3, "Results", "Accuracy reached 94.2% on the benchmark dataset."),
        ]
        top = retrieve_relevant_chunks("What learning rate was used in Methods?", chunks, top_k=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0].chunk_id, 1)

    def test_answer_paper_question_mocks_llm_and_returns_citations(self):
        chunks = [
            PaperChunk(0, 2, "Methods", "We used AdamW optimizer with lr=1e-4."),
            PaperChunk(1, 4, "Results", "F1 score improved by 5.3 points."),
        ]
        with patch("services.paper_chat.call_ollama", return_value="AdamW with lr=1e-4 [Page 2, Section Methods].") as mock_llm:
            result = answer_paper_question(
                question="Which optimizer was used?",
                chunks=chunks,
                paper_title="Test Paper",
                history=[{"question": "Hi", "answer": "Hello"}],
                top_k=2,
            )

        self.assertIn("AdamW", result["answer"])
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(result["citations"][0]["page"], 2)
        self.assertEqual(result["citations"][0]["section"], "Methods")
        prompt_arg = mock_llm.call_args.args[0]
        self.assertIn("Test Paper", prompt_arg)
        self.assertIn("Previous conversation:", prompt_arg)


class PaperChatEndpointTests(unittest.TestCase):
    def setUp(self):
        self.fake_user = SimpleNamespace(id=7, email="researcher@example.com")
        main.app.dependency_overrides[auth.get_current_user] = lambda: self.fake_user
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_chat_endpoint_returns_answer_and_citations(self):
        pdf_bytes = _build_pdf_bytes([
            "Introduction\nOur study evaluates solar cell efficiency.",
            "Results\nPerovskite tandem cells achieved 29.1% efficiency.",
        ])
        fake_paper = SimpleNamespace(
            id=42,
            title="Solar Cell Study",
            summary="Summary text",
            file_path="unused.pdf",
        )

        with (
            patch.object(paper_service, "get_paper_or_404", return_value=fake_paper),
            patch.object(paper_service, "get_pdf_content", return_value=pdf_bytes),
            patch(
                "services.paper_chat.call_ollama",
                return_value="They achieved 29.1% efficiency [Page 2, Section Results].",
            ),
        ):
            res = self.client.post(
                "/papers/42/chat",
                json={"question": "What efficiency was achieved?"},
            )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("29.1%", body["answer"])
        self.assertGreaterEqual(len(body["citations"]), 1)
        self.assertEqual(body["citations"][0]["page"], 2)

    def test_chat_endpoint_rejects_blank_question(self):
        fake_paper = SimpleNamespace(id=42, title="Solar Cell Study", summary="Summary")
        with patch.object(paper_service, "get_paper_or_404", return_value=fake_paper):
            res = self.client.post("/papers/42/chat", json={"question": "   "})
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
