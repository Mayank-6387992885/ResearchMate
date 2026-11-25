from __future__ import annotations

from sqlalchemy.orm import Session

import summarizer
from models.research_paper import ResearchPaper
from services.semantic_search import semantic_search_papers

PROJECT_CAPABILITIES = """ResearchMate is an AI-powered research paper workspace. Key features:
- Upload PDFs or import directly via arXiv ID/URL or DOI for section-by-section AI summarization.
- Automatic AI model failover (Ollama, Gemini, Groq) with real-time progress tracking.
- Save papers to a private library, organize by category/classification, and search with keyword or semantic search.
- Extract numerical metrics for charts and embedded figures for a paper gallery.
- Ask Paper (RAG) chat with clickable [Page X · Section Y] citations opening an inline PDF viewer.
- Cross-Paper Comparison matrix for 2-4 selected papers.
- Citation export in BibTeX (.bib), RIS (.ris), and APA formats.
- KaTeX math rendering in summaries and Q&A."""


def answer_workspace_question(
    db: Session,
    papers: list[ResearchPaper],
    question: str,
    history: list[dict[str, str]] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Answer a user query strictly grounded in ResearchMate features and saved papers."""
    cleaned = (question or "").strip()
    if not cleaned:
        raise ValueError("Question cannot be empty.")

    ranked, _ = semantic_search_papers(db, papers, query=cleaned, mode="semantic", limit=5)
    selected_papers = [item["paper"] for item in ranked]

    if selected_papers:
        library_context = "\n\n".join(
            f"[Paper ID {p.id}: {p.title}]\n"
            f"Category: {p.category or 'Uncategorized'} | Pages: {p.pages or 'N/A'}\n"
            f"Summary:\n{(p.summary or '')[:1200]}"
            for p in selected_papers
        )
    else:
        library_context = "No saved papers in the user's library yet."

    history_lines = []
    for turn in (history or [])[-6:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = (turn.get("content") or "").strip()
        if content:
            history_lines.append(f"{role}: {content}")
    history_block = "\n".join(history_lines)

    prompt = (
        "You are the ResearchMate Workspace Assistant.\n"
        "SCOPE RULE: Answer everything related to:\n"
        "1) The ResearchMate project (its features, workflows, architecture, and usage), OR\n"
        "2) The user's saved research papers and data provided below.\n"
        "If the question is out of topic, out of scope, or you do not have a data-driven answer from the project info or saved papers, reply strictly with: 'not known'.\n"
        "When citing a saved paper, mention its title.\n\n"
        f"=== RESEARCHMATE PROJECT ===\n{PROJECT_CAPABILITIES}\n\n"
        f"=== USER'S SAVED PAPERS ({len(papers)} total, top matches shown) ===\n{library_context}\n\n"
        + (f"=== CONVERSATION HISTORY ===\n{history_block}\n\n" if history_block else "")
        + f"User Question: {cleaned}\n\nAnswer:"
    )

    answer = summarizer.call_ollama(
        prompt,
        provider=provider,
        model=model,
    )

    referenced = [
        {"id": p.id, "title": p.title}
        for p in selected_papers
        if p.title and p.title.lower() in answer.lower()
    ]
    if not referenced and selected_papers and any(
        kw in cleaned.lower() for kw in ("paper", "summary", "library", "saved", "compare", "attention", "rag")
    ):
        referenced = [{"id": p.id, "title": p.title} for p in selected_papers[:2]]

    return {
        "answer": answer.strip(),
        "referenced_papers": referenced,
    }
