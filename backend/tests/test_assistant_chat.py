import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from auth import get_current_user  # noqa: E402
from database import get_db  # noqa: E402
from models.research_paper import ResearchPaper  # noqa: E402
from models.user import User  # noqa: E402


def test_assistant_chat_endpoint_returns_answer_and_references():
    mock_user = User(id=1, email="researcher@example.com", password_hash="x")
    mock_papers = [
        ResearchPaper(
            id=10,
            user_id=1,
            title="Attention Is All You Need",
            filename="attention.pdf",
            stored_filename="attention.pdf",
            file_path="/tmp/attention.pdf",
            summary="Introduces the Transformer architecture using self-attention.",
            pages=15,
            category="Technology",
            is_saved=True,
        )
    ]

    main.app.dependency_overrides[get_current_user] = lambda: mock_user
    main.app.dependency_overrides[get_db] = lambda: None
    try:
        with (
            patch("services.paper_service.list_papers", return_value=mock_papers),
            patch(
                "services.assistant_chat.semantic_search_papers",
                return_value=([{"paper": mock_papers[0], "score": 0.9, "snippet": "..."}], "tfidf"),
            ),
            patch(
                "summarizer.call_ollama",
                return_value="Based on Attention Is All You Need, it introduces the Transformer.",
            ),
            TestClient(main.app) as client,
        ):
            res = client.post(
                "/api/assistant/chat",
                json={"question": "What does Attention Is All You Need introduce?", "history": []},
            )
            assert res.status_code == 200
            data = res.json()
            assert "Transformer" in data["answer"]
            assert data["referenced_papers"] == [{"id": 10, "title": "Attention Is All You Need"}]
    finally:
        main.app.dependency_overrides.clear()


def test_assistant_chat_rejects_blank_question():
    mock_user = User(id=1, email="researcher@example.com", password_hash="x")
    main.app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with TestClient(main.app) as client:
            res = client.post("/api/assistant/chat", json={"question": "   "})
            assert res.status_code == 422
    finally:
        main.app.dependency_overrides.clear()
