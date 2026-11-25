"""RAG-based Q&A over a research paper using section/page chunking and TF-IDF retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pymupdf

from summarizer import call_ollama

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "what", "which", "who", "whom", "this", "these", "those",
    "how", "why", "when", "where", "can", "could", "would", "should", "do",
    "does", "did", "have", "had", "not", "or", "but", "if", "then", "than",
    "about", "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "once", "here", "there", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "only", "own", "same", "so", "too", "very", "just", "paper",
})

_KNOWN_HEADINGS = (
    "abstract",
    "introduction",
    "background",
    "related work",
    "literature review",
    "methodology",
    "methods",
    "materials and methods",
    "experimental setup",
    "experiments",
    "evaluation",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "future work",
    "limitations",
    "acknowledgments",
    "acknowledgements",
    "references",
    "appendix",
)

_NUMBERED_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXLCDM]+\.\s+)([A-Z][A-Za-z0-9\s\-:,/]{2,60})$"
)


@dataclass(frozen=True)
class PaperChunk:
    """A text chunk from a research paper with page and section metadata."""

    chunk_id: int
    page: int
    section: str
    text: str


def _detect_section_heading(line: str) -> str | None:
    """Return a normalized section heading if the line looks like an academic heading."""
    cleaned = " ".join(line.strip().split())
    if not cleaned or len(cleaned) > 70 or cleaned.endswith("."):
        return None
    lower = cleaned.lower().rstrip(":")
    if lower in _KNOWN_HEADINGS:
        return cleaned.rstrip(":")
    match = _NUMBERED_HEADING_RE.match(cleaned)
    if match:
        return cleaned
    if cleaned.isupper() and 3 <= len(cleaned) <= 45 and any(c.isalpha() for c in cleaned):
        return cleaned.title()
    return None


def extract_chunks_from_pdf(
    pdf_content: bytes,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[PaperChunk]:
    """Extract overlapping text chunks with 1-based page numbers and section labels."""
    chunks: list[PaperChunk] = []
    current_section = "Document Start"
    chunk_id = 0

    with pymupdf.open(stream=pdf_content, filetype="pdf") as pdf:
        for page_num, page in enumerate(pdf, start=1):
            raw_text = page.get_text("text") or ""
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            if not lines:
                continue

            page_buffer: list[str] = []
            page_section = current_section

            for line in lines:
                heading = _detect_section_heading(line)
                if heading:
                    if page_buffer:
                        chunk_id = _append_text_chunks(
                            chunks,
                            "\n".join(page_buffer),
                            page_num,
                            page_section,
                            chunk_id,
                            chunk_size,
                            overlap,
                        )
                        page_buffer = []
                    current_section = heading
                    page_section = heading
                else:
                    page_buffer.append(line)

            if page_buffer:
                chunk_id = _append_text_chunks(
                    chunks,
                    "\n".join(page_buffer),
                    page_num,
                    page_section,
                    chunk_id,
                    chunk_size,
                    overlap,
                )

    return chunks


def _append_text_chunks(
    chunks: list[PaperChunk],
    text: str,
    page: int,
    section: str,
    start_id: int,
    chunk_size: int,
    overlap: int,
) -> int:
    """Split text into overlapping windows and append PaperChunk instances."""
    normalized = " ".join(text.split())
    if not normalized:
        return start_id

    if len(normalized) <= chunk_size:
        chunks.append(PaperChunk(chunk_id=start_id, page=page, section=section, text=normalized))
        return start_id + 1

    step = max(1, chunk_size - overlap)
    idx = 0
    chunk_id = start_id
    while idx < len(normalized):
        window = normalized[idx : idx + chunk_size].strip()
        if window:
            chunks.append(PaperChunk(chunk_id=chunk_id, page=page, section=section, text=window))
            chunk_id += 1
        if idx + chunk_size >= len(normalized):
            break
        idx += step
    return chunk_id


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]


def retrieve_relevant_chunks(
    question: str,
    chunks: list[PaperChunk],
    top_k: int = 5,
) -> list[PaperChunk]:
    """Rank chunks using TF-IDF cosine similarity + section title match boost."""
    if not chunks:
        return []
    query_tokens = _tokenize(question)
    if not query_tokens:
        return chunks[:top_k]

    doc_tokens = [_tokenize(c.text) for c in chunks]
    num_docs = len(chunks)

    df: Counter[str] = Counter()
    for tokens in doc_tokens:
        df.update(set(tokens))

    idf = {
        term: math.log((num_docs + 1) / (df[term] + 1)) + 1.0
        for term in set(query_tokens) | set(df.keys())
    }

    query_tf = Counter(query_tokens)
    query_vec = {t: (1.0 + math.log(freq)) * idf.get(t, 1.0) for t, freq in query_tf.items()}
    query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1.0

    scored: list[tuple[float, PaperChunk]] = []
    query_token_set = set(query_tokens)

    for chunk, tokens in zip(chunks, doc_tokens):
        if not tokens:
            scored.append((0.0, chunk))
            continue
        tf = Counter(tokens)
        doc_vec = {t: (1.0 + math.log(freq)) * idf.get(t, 1.0) for t, freq in tf.items()}
        doc_norm = math.sqrt(sum(v * v for v in doc_vec.values())) or 1.0

        dot = sum(query_vec[t] * doc_vec.get(t, 0.0) for t in query_vec)
        score = dot / (query_norm * doc_norm)

        section_tokens = set(_tokenize(chunk.section))
        if section_tokens & query_token_set:
            score += 0.15

        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def answer_paper_question(
    question: str,
    chunks: list[PaperChunk],
    paper_title: str = "Research Paper",
    history: list[dict[str, str]] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve top chunks and prompt the active LLM to answer with citations."""
    top_chunks = retrieve_relevant_chunks(question, chunks, top_k=top_k)
    if not top_chunks:
        return {
            "answer": "I could not find any readable text in this paper to answer your question.",
            "citations": [],
        }

    context_blocks = [
        f"[Page {c.page}, Section: {c.section}]\n{c.text}"
        for c in top_chunks
    ]
    context_text = "\n\n---\n\n".join(context_blocks)

    history_block = ""
    if history:
        recent = history[-4:]
        lines = []
        for turn in recent:
            q = (turn.get("question") or "").strip()
            a = (turn.get("answer") or "").strip()
            if q:
                lines.append(f"User: {q}")
            if a:
                lines.append(f"Assistant: {a}")
        if lines:
            history_block = "Previous conversation:\n" + "\n".join(lines) + "\n\n"

    prompt = (
        f"You are a helpful research assistant answering questions about the paper \"{paper_title}\".\n"
        "Use ONLY the provided paper excerpts below to answer the user's question.\n"
        "Cite the relevant page and section in your answer using [Page X, Section Y] format.\n"
        "If the excerpts do not contain enough information to answer, say so clearly.\n\n"
        f"{history_block}"
        f"Paper excerpts:\n{context_text}\n\n"
        f"Question: {question.strip()}\n\n"
        "Answer:"
    )

    answer = call_ollama(prompt, max_tokens=600).strip()
    citations = [
        {
            "page": c.page,
            "section": c.section,
            "excerpt": c.text[:220] + ("..." if len(c.text) > 220 else ""),
        }
        for c in top_chunks
    ]
    return {"answer": answer, "citations": citations}
