from __future__ import annotations

import os
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.research_paper import ResearchPaper
from models.user import User
import services.citation_service as citation_service
import services.paper_service as paper_service
from services.assistant_chat import answer_workspace_question
from services.paper_chat import (
    PaperChunk,
    answer_paper_question,
    extract_chunks_from_pdf,
    retrieve_relevant_chunks_with_embeddings,
)
from services.semantic_search import semantic_search_papers
from summarizer import compare_papers

router = APIRouter()


class PaperChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list)


class ComparePapersRequest(BaseModel):
    paper_ids: list[int] = Field(..., min_length=2, max_length=4)


def _paper_to_dict(paper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "filename": paper.filename,
        "pages": paper.pages,
        "summary": paper.summary,
        "is_saved": paper.is_saved,
        "category": paper.category,
        "classification": paper.classification,
        "figures": getattr(paper, "figures", None) or [],
        "chart_data": getattr(paper, "chart_data", None) or [],
        "uploaded_at": paper.uploaded_at.isoformat() if paper.uploaded_at else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
    }


@router.get("/papers/search")
@router.get("/api/papers/search")
def search_papers_endpoint(
    q: str = "",
    mode: str = "semantic",
    saved_only: bool = False,
    category: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    papers = getattr(paper_service, "list_papers")(
        db, user.id, search=None, saved_only=saved_only, category=category
    )
    ranked, backend_used = semantic_search_papers(
        db, papers, query=q, mode=mode, limit=max(1, min(limit, 100))
    )
    results = []
    for item in ranked:
        data = _paper_to_dict(item["paper"])
        data["relevance_score"] = item["score"]
        data["snippet"] = item["snippet"]
        results.append(data)
    return {
        "papers": results,
        "total": len(results),
        "mode": mode,
        "backend": backend_used,
    }


@router.post("/api/papers/compare")
async def compare_selected_papers(
    payload: ComparePapersRequest,
    x_ai_provider: str | None = Header(default=None),
    x_ai_model: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    unique_ids = list(dict.fromkeys(payload.paper_ids))
    if len(unique_ids) < 2 or len(unique_ids) > 4:
        raise HTTPException(
            status_code=422,
            detail="Select between 2 and 4 unique papers to compare.",
        )

    papers = [
        getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
        for paper_id in unique_ids
    ]
    papers_data = [
        {
            "id": paper.id,
            "title": paper.title,
            "summary": paper.summary,
            "pages": paper.pages,
            "category": paper.category,
            "classification": paper.classification or {},
        }
        for paper in papers
    ]

    try:
        return await run_in_threadpool(
            compare_papers,
            papers_data,
            provider=x_ai_provider,
            model=x_ai_model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not compare papers: {exc}",
        ) from exc


@router.post("/assistant/chat")
@router.post("/api/assistant/chat")
async def chat_with_workspace_assistant(
    payload: PaperChatRequest,
    x_ai_provider: str | None = Header(default=None),
    x_ai_model: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    papers = getattr(paper_service, "list_papers")(db, user.id, search=None, saved_only=False)
    try:
        return await run_in_threadpool(
            answer_workspace_question,
            db,
            papers,
            question,
            history=payload.history,
            provider=x_ai_provider,
            model=x_ai_model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Assistant chat failed: {exc}",
        ) from exc


@router.get("/papers/{paper_id}/pdf")
def view_paper_pdf(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    local_path = getattr(paper_service, "resolve_local_pdf_path")(paper)
    filename = paper.filename or f"paper-{paper.id}.pdf"
    return FileResponse(
        local_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/papers/{paper_id}/citation")
def get_paper_citation(
    paper_id: int,
    format: str = Query(default="bibtex"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    content, media_type, ext = citation_service.format_citation(paper, fmt=format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="paper-{paper.id}.{ext}"'},
    )


@router.post("/papers/{paper_id}/chat")
async def chat_with_paper(
    paper_id: int,
    payload: PaperChatRequest,
    x_ai_provider: str | None = Header(default=None),
    x_ai_model: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty.")

    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    chunks: list[PaperChunk] = []
    try:
        pdf_bytes = getattr(paper_service, "get_pdf_content")(paper)
        if pdf_bytes:
            chunks = extract_chunks_from_pdf(pdf_bytes)
    except Exception:
        chunks = []

    if not chunks and paper.summary:
        chunks = [
            PaperChunk(
                chunk_id=0,
                page=1,
                section="Summary",
                text=paper.summary,
            )
        ]

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No readable PDF text or summary available for this paper.",
        )

    try:
        selected_chunks = await run_in_threadpool(
            retrieve_relevant_chunks_with_embeddings,
            db,
            paper.id,
            question,
            chunks,
            4,
        )
        return await run_in_threadpool(
            answer_paper_question,
            question,
            selected_chunks,
            paper_title=paper.title or paper.filename or f"Paper #{paper.id}",
            history=payload.history,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not answer paper question: {exc}",
        ) from exc


@router.get("/api/users/{user_id}/public-profile")
def get_public_profile(user_id: int, db: Session = Depends(get_db)):
    """Return a researcher's public profile and saved paper titles when opted in."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Researcher profile not found.")

    import json
    raw_privacy = getattr(user, "privacy_settings", None)
    if isinstance(raw_privacy, str):
        try:
            privacy = json.loads(raw_privacy)
        except Exception:
            privacy = {}
    else:
        privacy = raw_privacy or {}
    if not isinstance(privacy, dict) or not privacy.get("public_profile", False):
        raise HTTPException(status_code=403, detail="This researcher profile is private.")

    saved_papers = (
        db.query(ResearchPaper)
        .filter(ResearchPaper.user_id == user_id, ResearchPaper.is_saved.is_(True))
        .all()
    )
    display_name = getattr(user, "full_name", None) or (
        user.email.split("@")[0] if getattr(user, "email", None) else f"Researcher #{user.id}"
    )
    return {
        "id": user.id,
        "display_name": display_name,
        "saved_papers_count": len(saved_papers),
        "saved_papers": [
            {
                "id": p.id,
                "title": p.title,
                "category": p.category,
                "pages": p.pages,
            }
            for p in saved_papers
        ],
    }
