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
        "FORMAT RULE: Present your answer using clear, concise bullet points (e.g. '- **Point**: detail') instead of long paragraphs so it is easy to scan.\n"
        "EVIDENCE RULE: Give a complete, well-finished answer backed by concrete data, numbers, and facts from the saved papers or project details. Never cut off mid-sentence.\n"
        "FOLLOW-UP RULE: At the very end of your response, on a new line, output 'FOLLOW_UP_QUESTIONS:' followed by 3 short, specific follow-up questions (one per line starting with '- ') that deepen the exact topic just discussed. Do NOT repeat any question already asked.\n"
        "When citing a saved paper, mention its title.\n\n"
        f"=== RESEARCHMATE PROJECT ===\n{PROJECT_CAPABILITIES}\n\n"
        f"=== USER'S SAVED PAPERS ({len(papers)} total, top matches shown) ===\n{library_context}\n\n"
        + (f"=== CONVERSATION HISTORY ===\n{history_block}\n\n" if history_block else "")
        + f"User Question: {cleaned}\n\nAnswer:"
    )

    raw_response = summarizer.stream_ollama(
        prompt,
        max_tokens=1500,
        json_format=False,
        provider=provider,
        model=model,
    )

    answer, llm_suggestions = _split_answer_and_suggestions(raw_response)
    asked = _collect_asked_questions(cleaned, history)
    filtered_llm = [s for s in llm_suggestions if s.strip().lower() not in asked][:3]
    suggestions = filtered_llm if filtered_llm else _build_follow_up_suggestions(cleaned, selected_papers, history)

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
        "suggested_questions": suggestions,
    }


def _collect_asked_questions(question: str, history: list[dict[str, str]] | None = None) -> set[str]:
    asked = {question.strip().lower()}
    for turn in history or []:
        if turn.get("role") == "user":
            content = (turn.get("content") or "").strip().lower()
            if content:
                asked.add(content)
    return asked


def _split_answer_and_suggestions(raw_text: str) -> tuple[str, list[str]]:
    marker = "FOLLOW_UP_QUESTIONS:"
    if marker not in raw_text:
        return raw_text, []
    answer_part, _, suggestions_part = raw_text.partition(marker)
    parsed: list[str] = []
    for line in suggestions_part.splitlines():
        cleaned_line = line.strip().lstrip("-*•0123456789. ").strip()
        if cleaned_line:
            parsed.append(cleaned_line)
    return answer_part.strip(), parsed[:3]


def _build_follow_up_suggestions(
    question: str,
    papers: list[ResearchPaper],
    history: list[dict[str, str]] | None = None,
) -> list[str]:
    """Predict 3 relevant follow-up questions, excluding any already asked."""
    asked = {question.strip().lower()}
    for turn in history or []:
        if turn.get("role") == "user":
            content = (turn.get("content") or "").strip().lower()
            if content:
                asked.add(content)

    q_lower = question.lower()
    candidates: list[str] = []

    if papers:
        top_title = papers[0].title
        if "compare" not in q_lower and len(papers) >= 2:
            candidates.append(f"Compare {papers[0].title[:28]} and {papers[1].title[:28]}")
        if "metric" not in q_lower and "data" not in q_lower:
            candidates.append(f"What key metrics or results are in {top_title[:32]}?")
        if "limitation" not in q_lower:
            candidates.append(f"What are the limitations of {top_title[:32]}?")

    candidates.extend([
        "Summarize my saved papers",
        "What can ResearchMate do?",
        "How do I export BibTeX citations?",
        "How do I import a paper from arXiv or DOI?",
        "How does semantic search work in ResearchMate?",
    ])

    suggestions: list[str] = []
    for item in candidates:
        if len(suggestions) >= 3:
            break
        if item.strip().lower() not in asked and item not in suggestions:
            suggestions.append(item)

    return suggestions
