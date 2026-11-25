"""Lightweight semantic search service with Ollama embeddings and TF-IDF fallback."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from models.paper_embedding import PaperEmbedding
from models.research_paper import ResearchPaper

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_EMBED_TIMEOUT", "2.0"))

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _paper_text(paper: ResearchPaper) -> str:
    classification = paper.classification if isinstance(paper.classification, dict) else {}
    domains = classification.get("research_domains") or []
    domain_str = " ".join(str(d) for d in domains) if isinstance(domains, list) else ""
    return f"{paper.title or ''}\n{paper.category or ''}\n{domain_str}\n{paper.summary or ''}".strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def fetch_ollama_embedding(text: str, model: str = OLLAMA_EMBED_MODEL) -> list[float] | None:
    """Request an embedding vector from Ollama `/api/embeddings`. Returns None on failure."""
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        embedding = data.get("embedding")
        if isinstance(embedding, list) and embedding and all(isinstance(x, (int, float)) for x in embedding):
            return [float(x) for x in embedding]
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return None


def _get_or_create_embedding(db: Session, paper: ResearchPaper, model: str) -> list[float] | None:
    text = _paper_text(paper)
    c_hash = _content_hash(text)
    cached = db.query(PaperEmbedding).filter(PaperEmbedding.paper_id == paper.id).first()
    if cached and cached.model_name == model and cached.content_hash == c_hash and isinstance(cached.embedding, list):
        return [float(x) for x in cached.embedding]

    vec = fetch_ollama_embedding(text, model=model)
    if vec is None:
        return None

    if cached:
        cached.model_name = model
        cached.content_hash = c_hash
        cached.embedding = vec
    else:
        db.add(PaperEmbedding(
            paper_id=paper.id,
            model_name=model,
            content_hash=c_hash,
            embedding=vec,
        ))
    db.commit()
    return vec


def _tfidf_scores(query: str, papers: list[ResearchPaper]) -> list[float]:
    """Compute TF-IDF cosine similarity between query and each paper."""
    query_tokens = _tokenize(query)
    if not query_tokens or not papers:
        return [0.0] * len(papers)

    docs_tokens = [_tokenize(_paper_text(p)) for p in papers]
    n_docs = len(docs_tokens)

    df: Counter[str] = Counter()
    for tokens in docs_tokens:
        df.update(set(tokens))

    def idf(term: str) -> float:
        return math.log((1 + n_docs) / (1 + df.get(term, 0))) + 1.0

    def tfidf_vec(tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        total = len(tokens)
        return {term: (count / total) * idf(term) for term, count in tf.items()}

    q_vec = tfidf_vec(query_tokens)
    q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
    if q_norm == 0.0:
        return [0.0] * len(papers)

    scores: list[float] = []
    for tokens in docs_tokens:
        d_vec = tfidf_vec(tokens)
        d_norm = math.sqrt(sum(v * v for v in d_vec.values()))
        if d_norm == 0.0:
            scores.append(0.0)
            continue
        dot = sum(q_vec[t] * d_vec.get(t, 0.0) for t in q_vec)
        scores.append(max(0.0, min(1.0, dot / (q_norm * d_norm))))
    return scores


def extract_snippet(paper: ResearchPaper, query: str, max_len: int = 180) -> str:
    """Return a concise snippet from the paper summary around the best matching query term."""
    summary = (paper.summary or "").strip()
    if not summary:
        return (paper.title or "")[:max_len]

    tokens = [t for t in _tokenize(query) if len(t) > 2]
    lower = summary.lower()
    best_idx = -1
    for token in tokens:
        idx = lower.find(token)
        if idx != -1 and (best_idx == -1 or idx < best_idx):
            best_idx = idx

    if best_idx == -1:
        snippet = summary[:max_len].strip()
        return f"{snippet}..." if len(summary) > max_len else snippet

    start = max(0, best_idx - 50)
    end = min(len(summary), start + max_len)
    snippet = summary[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(summary):
        snippet = f"{snippet}..."
    return snippet


def semantic_search_papers(
    db: Session,
    papers: list[ResearchPaper],
    query: str,
    mode: str = "semantic",
    limit: int = 20,
) -> tuple[list[dict[str, Any]], str]:
    """Rank papers by semantic similarity (Ollama embeddings with TF-IDF fallback) or keyword match.

    Returns (ranked_items, backend_used) where each item is {"paper": ResearchPaper, "score": float, "snippet": str}.
    """
    q = (query or "").strip()
    if not q:
        items = [
            {"paper": p, "score": 1.0, "snippet": extract_snippet(p, "")}
            for p in papers[:limit]
        ]
        return items, "none"

    if mode == "keyword":
        q_lower = q.lower()
        scored = []
        for p in papers:
            text = _paper_text(p).lower()
            if q_lower in (p.title or "").lower():
                score = 1.0
            elif q_lower in text:
                score = 0.7
            else:
                score = 0.0
            if score > 0.0:
                scored.append({"paper": p, "score": score, "snippet": extract_snippet(p, q)})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit], "keyword"

    # Try Ollama embeddings first
    backend_used = "ollama"
    query_vec = fetch_ollama_embedding(q)
    scores: list[float] | None = None

    if query_vec is not None:
        ollama_scores: list[float] = []
        for p in papers:
            p_vec = _get_or_create_embedding(db, p, OLLAMA_EMBED_MODEL)
            if p_vec is None:
                ollama_scores = []
                break
            ollama_scores.append(_cosine_similarity(query_vec, p_vec))
        if ollama_scores:
            scores = ollama_scores

    if scores is None:
        backend_used = "tfidf"
        scores = _tfidf_scores(q, papers)

    ranked = [
        {
            "paper": p,
            "score": round(float(score), 4),
            "snippet": extract_snippet(p, q),
        }
        for p, score in zip(papers, scores)
    ]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit], backend_used
