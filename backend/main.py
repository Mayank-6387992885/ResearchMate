"""ResearchMate API: PDF summarization, progress updates, and paper library."""
import ctypes
import os
import threading
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import Base, SessionLocal, engine, get_db
from auth import get_current_user, router as auth_router
from classification import CLASSIFICATION_PROGRESS_FIELDS, classify_research_paper
from models.paper_embedding import PaperEmbedding  # Ensure model is registered with SQLAlchemy.
from models.progress_task import ProgressTask
from models.paper_chunk_embedding import PaperChunkEmbedding  # Ensure model is registered with SQLAlchemy.
from models.research_paper import ResearchPaper  # Ensure model is registered with SQLAlchemy.
from models.sms_verification import SmsVerification  # Ensure model is registered with SQLAlchemy.
from models.user import User
import services.citation_service as citation_service
import services.import_service as import_service
import services.paper_service as paper_service
from core.config import settings
from core.exceptions import register_exception_handlers
from core.logging_config import configure_logging
from core.rate_limit import RateLimitMiddleware
from core.startup import init_database_and_tasks
from routers.papers_extras import router as papers_extras_router
from services.progress_service import get_progress_state, set_progress

configure_logging()
from figures import extract_paper_figures
from summarizer import (
    compare_papers,
    extract_research_metrics,
    get_last_fallback_notice,
    set_last_fallback_notice,
    summarize_paper,
)

app = FastAPI(title="ResearchMate API")

# Register authentication routes
app.include_router(auth_router)
app.include_router(papers_extras_router)
app.include_router(papers_extras_router, prefix=settings.api_v1_prefix)
register_exception_handlers(app)
app.add_middleware(RateLimitMiddleware)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",

#         "http://localhost:5173",
#         "http://127.0.0.1:5173",

#         "http://localhost:5500",
#         "http://127.0.0.1:5500",

#         "http://localhost:8000",
#         "http://127.0.0.1:8000",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

BASE_DIR = Path(__file__).resolve().parent


# Get deployed frontend URL from environment variables
frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

# Allowed frontend origins
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Add deployed frontend URL
if frontend_url:
    allowed_origins.append(frontend_url)
else:
    print("[WARNING] FRONTEND_URL is not set; deployed frontend may be blocked by CORS.", flush=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_FILE_SIZE = 10 * 1024 * 1024


class PaperUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = None
    classification: dict[str, list[str]] | None = None


class PaperImportRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=500)


@app.on_event("startup")
def create_database_tables():
    init_database_and_tasks()


def paper_to_dict(paper: ResearchPaper) -> dict:
    raw_classification = dict(paper.classification or {})
    figures = raw_classification.get("figures", [])
    chart_data = raw_classification.get("chart_data", [])
    clean_classification = {
        k: v for k, v in raw_classification.items()
        if k not in ("figures", "chart_data")
    }
    return {
        "id": paper.id,
        "title": paper.title,
        "filename": paper.filename,
        "pages": paper.pages,
        "summary": paper.summary,
        "is_saved": paper.is_saved,
        "category": paper.category,
        "classification": clean_classification,
        "figures": figures,
        "chart_data": chart_data,
        "uploaded_at": paper.uploaded_at.isoformat() if paper.uploaded_at is not None else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at is not None else None,
    }


@app.get("/")
def home():
    return {"message": "ResearchMate API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/progress/{task_id}")
def get_progress(task_id: str, user: User = Depends(get_current_user)):
    task = get_progress_state(task_id, user.id)
    if task is None:
        raise HTTPException(status_code=404, detail="Progress task not found.")
    return task


def validate_pdf_signature(content: bytes) -> None:
    """Verify the uploaded bytes begin with a valid PDF %PDF- header."""
    if not content or not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF file signature.")


async def _process_pdf_pipeline(
    content: bytes,
    original_filename: str | None,
    task_id: str,
    start_time: float,
    x_ai_provider: str | None,
    x_ai_model: str | None,
    db: Session,
    user: User,
    extra_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run text extraction, figure extraction, summarization, metrics, storage, and classification."""
    validate_pdf_signature(content)
    user_id = int(getattr(user, "id", 0) or 0)

    def report_progress(
        progress: int,
        message: str,
        partial_result: dict[str, Any] | None = None,
    ) -> None:
        set_progress(task_id, progress, message, result=partial_result, user_id=user_id)

    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise HTTPException(status_code=400, detail="Encrypted PDFs are not supported.")
            page_count = len(pdf)
            text = "\n".join(str(page.get_text("text")) for page in pdf)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read this PDF. Please upload a valid PDF file.",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No selectable text found in the PDF. OCR may be required for scanned documents.",
        )

    report_progress(12, "Extracting figures, plots, and architecture diagrams...")
    figures = await run_in_threadpool(extract_paper_figures, content, 8)

    report_progress(15, "Text extracted. Preparing AI summarization...")

    set_last_fallback_notice(None)
    summary = await run_in_threadpool(
        summarize_paper,
        text,
        report_progress,
        x_ai_provider,
        x_ai_model,
    )

    report_progress(93, "Extracting numerical statistics and benchmark metrics...")
    chart_data = await run_in_threadpool(
        extract_research_metrics,
        text,
        summary,
        x_ai_provider,
        x_ai_model,
    )

    initial_meta = {
        "figures": figures,
        "chart_data": chart_data,
    }
    paper = getattr(paper_service, "create_paper")(
        db=db,
        pdf_content=content,
        original_filename=original_filename,
        summary=summary,
        pages=page_count,
        user_id=user.id,
        classification=initial_meta,
    )

    classification_error = None
    report_progress(94, "Classifying research domains and paper type...")
    try:
        def report_classification_progress(
            completed: int,
            total: int,
            dimension: str,
        ) -> None:
            progress = 94 + round((completed / total) * 5)
            set_progress(
                task_id,
                progress,
                f"Classifying {dimension.replace('_', ' ')} ({completed}/{total})",
                result={
                    "classification_progress": {
                        "completed": completed,
                        "total": total,
                        "current_dimension": dimension,
                    }
                },
                user_id=user.id,
            )

        classification = await run_in_threadpool(
            classify_research_paper,
            text,
            summary,
            report_classification_progress,
            x_ai_provider,
            x_ai_model,
        )
    except RuntimeError as exc:
        classification_error = str(exc)
        print(f"[WARNING] Paper saved without AI classification: {exc}", flush=True)
    else:
        paper = getattr(paper_service, "update_paper")(
            db,
            paper.id,
            user_id=user.id,
            classification=classification,
            figures=figures,
            chart_data=chart_data,
        )

    total_time = time.time() - start_time
    fallback_notice = get_last_fallback_notice()
    result = {
        "task_id": task_id,
        **paper_to_dict(paper),
        "characters": len(text),
        "preview": text[:1000],
        "processing_time_seconds": round(total_time, 2),
    }
    if extra_result:
        result.update(extra_result)
    if fallback_notice:
        result["fallback_notice"] = fallback_notice
    if classification_error:
        result["classification_error"] = classification_error
    set_progress(
        task_id,
        100,
        (
            "Summary saved. AI classification can be retried from My Summaries."
            if classification_error
            else "Summary completed and saved to your library."
        ),
        "completed",
        result,
    )
    return result


@app.post("/upload")
async def upload_paper(
    file: UploadFile = File(...),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    x_ai_provider: str | None = Header(default=None, alias="X-AI-Provider"),
    x_ai_model: str | None = Header(default=None, alias="X-AI-Model"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload, extract, summarize, then save the PDF and summary in the library."""
    start_time = time.time()
    task_id = x_task_id or str(uuid.uuid4())
    user_id = int(getattr(user, "id", 0) or 0)
    with SessionLocal() as task_db:
        if task_db.get(ProgressTask, task_id) is not None:
            raise HTTPException(status_code=409, detail="This analysis task ID has already been used.")

    set_progress(task_id, 0, "Starting upload...", user_id=user_id)

    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")

        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB size limit.")
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        set_progress(task_id, 5, "PDF uploaded. Extracting text...", user_id=user_id)
        return await _process_pdf_pipeline(
            content=content,
            original_filename=file.filename,
            task_id=task_id,
            start_time=start_time,
            x_ai_provider=x_ai_provider,
            x_ai_model=x_ai_model,
            db=db,
            user=user,
        )

    except HTTPException as exc:
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), str(exc.detail), "error")
        raise
    except RuntimeError as exc:
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), str(exc), "error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Upload failed: {exc!r}", flush=True)
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), "An unexpected error occurred.", "error")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the paper.",
        ) from exc
    finally:
        await file.close()


@app.post("/api/papers/import")
async def import_paper_by_identifier(
    payload: PaperImportRequest,
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    x_ai_provider: str | None = Header(default=None, alias="X-AI-Provider"),
    x_ai_model: str | None = Header(default=None, alias="X-AI-Model"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch metadata and open-access PDF from arXiv or CrossRef/DOI, then run the summarization pipeline."""
    start_time = time.time()
    task_id = x_task_id or str(uuid.uuid4())
    user_id = int(getattr(user, "id", 0) or 0)
    with SessionLocal() as task_db:
        if task_db.get(ProgressTask, task_id) is not None:
            raise HTTPException(status_code=409, detail="This analysis task ID has already been used.")

    set_progress(task_id, 0, "Resolving paper identifier...", user_id=user_id)

    try:
        imported = await run_in_threadpool(
            import_service.fetch_paper_from_identifier,
            payload.identifier,
        )
        set_progress(
            task_id,
            5,
            f"Fetched '{imported.title[:60]}' ({imported.source.upper()}). Extracting text...",
            user_id=user_id,
        )
        return await _process_pdf_pipeline(
            content=imported.pdf_content,
            original_filename=imported.filename,
            task_id=task_id,
            start_time=start_time,
            x_ai_provider=x_ai_provider,
            x_ai_model=x_ai_model,
            db=db,
            user=user,
            extra_result={"import_metadata": imported.to_metadata_dict()},
        )
    except HTTPException as exc:
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), str(exc.detail), "error")
        raise
    except RuntimeError as exc:
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), str(exc), "error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Import failed: {exc!r}", flush=True)
        previous = get_progress_state(task_id, user.id) or {}
        set_progress(task_id, previous.get("progress", 0), "An unexpected error occurred.", "error")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while importing the paper.",
        ) from exc


@app.get("/papers")
def get_papers(
    search: str | None = None,
    saved_only: bool = False,
    category: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    papers = getattr(paper_service, "list_papers")(
        db, user.id, search=search, saved_only=saved_only, category=category
    )
    return {"papers": [paper_to_dict(paper) for paper in papers], "total": len(papers)}


@app.get("/papers/{paper_id}")
def get_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return paper_to_dict(getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id))


@app.put("/papers/{paper_id}/save")
def save_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "toggle_saved")(db, paper_id, user.id)
    return {"id": paper.id, "is_saved": paper.is_saved}


@app.patch("/papers/{paper_id}")
def update_paper(
    paper_id: int,
    updates: PaperUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    update_fields = updates.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=422, detail="Provide a title or classification to update.")
    if any(value is None for value in update_fields.values()):
        raise HTTPException(status_code=422, detail="Paper update values cannot be empty.")
    paper = getattr(paper_service, "update_paper")(
        db, paper_id, user_id=user.id, **update_fields
    )
    return paper_to_dict(paper)


def run_saved_paper_classification(
    paper_id: int,
    task_id: str,
    user_id: int,
    paper_text: str,
    summary: str,
) -> None:
    def report_progress(completed: int, total: int, dimension: str) -> None:
        progress = round((completed / total) * 95)
        set_progress(
            task_id,
            progress,
            f"Classifying {dimension.replace('_', ' ')} ({completed}/{total})",
            result={
                "classification_progress": {
                    "completed": completed,
                    "total": total,
                    "current_dimension": dimension,
                }
            },
            user_id=user_id,
        )

    try:
        classification = classify_research_paper(
            paper_text,
            summary,
            report_progress,
        )
        with SessionLocal() as db:
            paper = getattr(paper_service, "update_paper")(
                db, paper_id, user_id=user_id, classification=classification
            )
            result = {
                "paper_id": paper.id,
                "classification": paper.classification,
            }
        set_progress(
            task_id,
            100,
            "Paper classification completed.",
            "completed",
            result,
            user_id=user_id,
        )
    except Exception as exc:
        print(f"[ERROR] Classification task {task_id[:8]} failed: {exc!r}", flush=True)
        previous = get_progress_state(task_id, user_id) or {}
        set_progress(
            task_id,
            previous.get("progress", 0),
            str(exc) if isinstance(exc, RuntimeError) else "Paper classification failed.",
            "error",
            user_id=user_id,
        )


@app.post("/papers/{paper_id}/classify")
def classify_saved_paper(
    paper_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    try:
        pdf_content = paper_service.get_pdf_content(paper)
        with pymupdf.open(stream=pdf_content, filetype="pdf") as pdf:
            paper_text = "\\n".join(page.get_text("text") for page in pdf)
    except (pymupdf.FileDataError, RuntimeError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to extract text from this PDF for classification.",
        ) from exc
    if not paper_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No selectable text found in this PDF. OCR may be required.",
        )

    task_id = str(uuid.uuid4())
    set_progress(
        task_id,
        0,
        "Preparing paper classification...",
        result={
            "classification_progress": {
                "completed": 0,
                "total": len(CLASSIFICATION_PROGRESS_FIELDS),
                "current_dimension": CLASSIFICATION_PROGRESS_FIELDS[0],
            }
        },
        user_id=user.id,
    )
    background_tasks.add_task(
        run_saved_paper_classification,
        paper_id,
        task_id,
        user.id,
        paper_text,
        paper.summary,
    )
    return {"task_id": task_id, "status": "processing"}


@app.get("/papers/{paper_id}/download")
def download_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    pdf_content = paper_service.get_pdf_content(paper)
    safe_filename = Path(paper.filename or "research-paper.pdf").name.replace('"', "")
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@app.get("/papers/{paper_id}/pdf")
def view_paper_pdf(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    pdf_content = paper_service.get_pdf_content(paper)
    safe_filename = Path(paper.filename or "research-paper.pdf").name.replace('"', "")
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
    )


@app.get("/papers/{paper_id}/download-summary")
def download_summary(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    content = f"{paper.title}\n{'=' * len(paper.title)}\n\n{paper.summary}\n"
    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="researchmate-summary-{paper.id}.txt"'
        },
    )


@app.get("/papers/{paper_id}/citation")
def get_paper_citation(
    paper_id: int,
    format: str = "bibtex",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    paper = getattr(paper_service, "get_paper_or_404")(db, paper_id, user.id)
    content, media_type, ext = citation_service.format_citation(paper, fmt=format)
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="researchmate-citation-{paper.id}.{ext}"'
        },
    )


@app.delete("/papers/{paper_id}")
def remove_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    getattr(paper_service, "delete_paper")(db, paper_id, user.id)
    return {"message": "Paper deleted successfully.", "id": paper_id}
