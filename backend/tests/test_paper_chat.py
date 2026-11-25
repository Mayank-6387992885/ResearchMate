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


class PaperChunkEmbeddingRetrievalTests(unittest.TestCase):
    def test_embedding_retrieval_caches_chunks_and_returns_accurate_citations(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import Base
        from models.paper_chunk_embedding import PaperChunkEmbedding
        from services.paper_chat import PaperChunk, retrieve_relevant_chunks_with_embeddings

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()

        chunks = [
            PaperChunk(chunk_id=0, page=1, section="Introduction", text="Overview of climate models."),
            PaperChunk(chunk_id=1, page=3, section="Experiments", text="Solar cells reached 29.1% efficiency."),
            PaperChunk(chunk_id=2, page=5, section="Conclusion", text="Future work on stability."),
        ]

        def fake_embed(text, model=None):
            if "efficiency" in text.lower() or "solar" in text.lower():
                return [1.0, 0.0, 0.0]
            if "climate" in text.lower():
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        with patch("services.paper_chat.fetch_ollama_embedding", side_effect=fake_embed) as mock_embed:
            first_top = retrieve_relevant_chunks_with_embeddings(
                db, paper_id=101, question="What solar efficiency was achieved?", chunks=chunks, top_k=1
            )
            self.assertEqual(len(first_top), 1)
            self.assertEqual(first_top[0].page, 3)
            self.assertEqual(first_top[0].section, "Experiments")
            self.assertEqual(db.query(PaperChunkEmbedding).count(), 3)
            first_calls = mock_embed.call_count  # 1 query + 3 chunks = 4

            second_top = retrieve_relevant_chunks_with_embeddings(
                db, paper_id=101, question="What solar efficiency was achieved?", chunks=chunks, top_k=1
            )
            self.assertEqual(second_top[0].page, 3)
            # Only 1 additional call for the query; all 3 chunks were served from DB cache.
            self.assertEqual(mock_embed.call_count, first_calls + 1)

    def test_embedding_retrieval_falls_back_to_tfidf_when_ollama_unavailable(self):
        from services.paper_chat import PaperChunk, retrieve_relevant_chunks_with_embeddings

        chunks = [
            PaperChunk(chunk_id=0, page=1, section="Abstract", text="General introduction."),
            PaperChunk(chunk_id=1, page=4, section="Results", text="Transformer BLEU score reached 28.4."),
        ]
        with patch("services.paper_chat.fetch_ollama_embedding", return_value=None):
            top = retrieve_relevant_chunks_with_embeddings(
                None, paper_id=None, question="What BLEU score did Transformer reach?", chunks=chunks, top_k=1
            )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].page, 4)
        self.assertEqual(top[0].section, "Results")
