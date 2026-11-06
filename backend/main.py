"""ResearchMate API: PDF summarization, progress updates, and paper library."""
import ctypes
import os
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
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import Base, SessionLocal, engine, get_db
from auth import get_current_user, router as auth_router
from classification import CLASSIFICATION_PROGRESS_FIELDS, classify_research_paper
from models.progress_task import ProgressTask
from models.research_paper import ResearchPaper  # Ensure model is registered with SQLAlchemy.
from models.sms_verification import SmsVerification  # Ensure model is registered with SQLAlchemy.
from models.user import User
import services.paper_service as paper_service
from summarizer import summarize_paper

app = FastAPI(title="ResearchMate API")


# app.include_router(auth_router)

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

# BASE_DIR = Path(__file__).resolve().parent


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_FILE_SIZE = 10 * 1024 * 1024


class PaperUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = None
    classification: dict[str, list[str]] | None = None


@app.on_event("startup")
def create_database_tables():
    Base.metadata.create_all(bind=engine)
    paper_columns = {
        column["name"] for column in inspect(engine).get_columns("research_papers")
    }
    if "category" not in paper_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE research_papers "
                    "ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'Uncategorized'"
                )
            )
    if "classification" not in paper_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE research_papers "
                    "ADD COLUMN classification JSON NOT NULL DEFAULT '{}'"
                )
            )
    if "updated_at" not in paper_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE research_papers ADD COLUMN updated_at DATETIME")
            )
    if "user_id" not in paper_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE research_papers ADD COLUMN user_id INTEGER REFERENCES users(id)")
            )

    user_columns = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    if "github_id" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN github_id VARCHAR(255)"))
    if "linkedin_sub" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN linkedin_sub VARCHAR(255)"))
    if "phone_number" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(16)"))
    if "phone_verified" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT 0")
            )
    user_profile_columns = {
        "username": "VARCHAR(30)",
        "profile_data": "TEXT NOT NULL DEFAULT '{}'",
        "profile_image": "BLOB",
        "profile_image_type": "VARCHAR(32)",
        "notification_preferences": "TEXT NOT NULL DEFAULT '{}'",
        "privacy_settings": "TEXT NOT NULL DEFAULT '{}'",
    }
    for column_name, column_definition in user_profile_columns.items():
        if column_name not in user_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")
                )
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_github_id ON users (github_id)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_linkedin_sub ON users (linkedin_sub)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone_number ON users (phone_number)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)")
        )
    sms_verification_columns = {
        column["name"] for column in inspect(engine).get_columns("sms_verifications")
    }
    if "used_at" not in sms_verification_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE sms_verifications ADD COLUMN used_at DATETIME")
            )

    progress_columns = {
        column["name"] for column in inspect(engine).get_columns("progress_tasks")
    }
    if "started_at" not in progress_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE progress_tasks ADD COLUMN started_at FLOAT"))
    if "owner_user_id" not in progress_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE progress_tasks ADD COLUMN owner_user_id INTEGER")
            )

    with SessionLocal() as db:
        interrupted_tasks = db.query(ProgressTask).filter(
            ProgressTask.status == "processing",
        ).all()
        for task in interrupted_tasks:
            if not _process_is_running(task.owner_pid):
                task.status = "error"
                task.message = "Backend stopped before this analysis completed."
                task.updated_at = time.time()
        db.commit()


def _process_is_running(process_id: int) -> bool:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_exit_code.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        handle = open_process(0x1000, False, process_id)
        if not handle:
            return ctypes.get_last_error() == 5

        try:
            exit_code = wintypes.DWORD()
            if not get_exit_code(handle, ctypes.byref(exit_code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return exit_code.value == 259
        finally:
            close_handle(handle)

    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def set_progress(
    task_id: str,
    progress: int,
    message: str,
    status: str = "processing",
    result: dict[str, Any] | None = None,
    user_id: int | None = None,
):
    progress = max(0, min(100, int(progress)))
    if status == "processing":
        progress = min(progress, 99)
    elif status == "completed":
        progress = 100

    timestamp = time.time()
    with SessionLocal() as db:
        existing_task = db.get(ProgressTask, task_id)
        task_result = result
        if task_result is None and existing_task is not None:
            task_result = existing_task.result
        db.merge(ProgressTask(
            task_id=task_id,
            progress=progress,
            message=message,
            status=status,
            updated_at=timestamp,
            started_at=(
                existing_task.started_at
                if existing_task is not None and existing_task.started_at is not None
                else timestamp
            ),
            owner_pid=os.getpid(),
            owner_user_id=(
                user_id
                if user_id is not None
                else existing_task.owner_user_id if existing_task is not None else None
            ),
            result=task_result,
        ))
        db.commit()
    print(f"[PROGRESS][{task_id[:8]}] {progress}% | {message}", flush=True)


def get_progress_state(task_id: str, user_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        task = db.get(ProgressTask, task_id)
        if task is None or task.owner_user_id != user_id:
            return None
        if task.status == "processing" and not _process_is_running(task.owner_pid):
            task.status = "error"
            task.message = "Backend stopped before this analysis completed."
            task.updated_at = time.time()
            db.commit()
        return task.to_dict()


def paper_to_dict(paper: ResearchPaper) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "filename": paper.filename,
        "pages": paper.pages,
        "summary": paper.summary,
        "is_saved": paper.is_saved,
        "category": paper.category,
        "classification": paper.classification or {},
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


@app.post("/upload")
async def upload_paper(
    file: UploadFile = File(...),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload, extract, summarize, then save the PDF and summary in the library."""
    start_time = time.time()
    task_id = x_task_id or str(uuid.uuid4())
    with SessionLocal() as task_db:
        if task_db.get(ProgressTask, task_id) is not None:
            raise HTTPException(status_code=409, detail="This analysis task ID has already been used.")

    def report_progress(
        progress: int,
        message: str,
        partial_result: dict[str, Any] | None = None,
    ) -> None:
        set_progress(task_id, progress, message, result=partial_result, user_id=user.id)

    set_progress(task_id, 0, "Starting upload...", user_id=user.id)

    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")

        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB size limit.")
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        report_progress(5, "PDF uploaded. Extracting text...")

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

        report_progress(15, "Text extracted. Preparing AI summarization...")

        # Persist chunk-level updates so every frontend poll sees the same task state.
        summary = await run_in_threadpool(
            summarize_paper,
            text,
            report_progress,
        )

        paper = getattr(paper_service, "create_paper")(
            db=db,
            pdf_content=content,
            original_filename=file.filename,
            summary=summary,
            pages=page_count,
            user_id=user.id,
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
            )
        except RuntimeError as exc:
            classification_error = str(exc)
            print(f"[WARNING] Paper saved without AI classification: {exc}", flush=True)
        else:
            paper = getattr(paper_service, "update_paper")(
                db, paper.id, user_id=user.id, classification=classification
            )

        total_time = time.time() - start_time
        result = {
            "task_id": task_id,
            **paper_to_dict(paper),
            "characters": len(text),
            "preview": text[:1000],
            "processing_time_seconds": round(total_time, 2),
        }
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
    path = Path(paper.file_path)
    upload_dir = (BASE_DIR / "uploads" / "research_papers").resolve()
    if not path.is_file() or path.parent.resolve() != upload_dir:
        raise HTTPException(status_code=404, detail="The stored PDF file is missing.")

    try:
        with pymupdf.open(path) as pdf:
            paper_text = "\n".join(page.get_text("text") for page in pdf)
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
    path = Path(paper.file_path)

    # Protect against stale or manually edited database paths.
    if not path.is_file() or path.parent.resolve() != (BASE_DIR / "uploads" / "research_papers").resolve():
        raise HTTPException(status_code=404, detail="The stored PDF file is missing.")

    return FileResponse(path, media_type="application/pdf", filename=paper.filename)


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


@app.delete("/papers/{paper_id}")
def remove_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    getattr(paper_service, "delete_paper")(db, paper_id, user.id)
    return {"message": "Paper deleted successfully.", "id": paper_id}
