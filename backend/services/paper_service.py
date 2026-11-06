"""Database and Supabase Storage operations for the ResearchMate paper library."""
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session
from supabase import Client, create_client

from classification import validate_classification
from models.research_paper import ResearchPaper

BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_UPLOAD_DIR = BASE_DIR / "uploads" / "research_papers"
BUCKET_NAME = os.getenv("SUPABASE_STORAGE_BUCKET", "research-papers")


def _storage_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend environment.")
    return create_client(url, key)


def _safe_filename(filename: str | None) -> str:
    name = (filename or "research-paper.pdf").replace("\\\\", "/").split("/")[-1]
    return name[:255] or "research-paper.pdf"


def _is_legacy_local_path(value: str) -> bool:
    try:
        return Path(value).resolve().parent == LEGACY_UPLOAD_DIR.resolve()
    except (OSError, RuntimeError):
        return False


def get_pdf_content(paper: ResearchPaper) -> bytes:
    location = str(paper.file_path or "")
    if _is_legacy_local_path(location):
        old_file = Path(location)
        if old_file.is_file():
            return old_file.read_bytes()
    try:
        data = _storage_client().storage.from_(BUCKET_NAME).download(location)
        return data if isinstance(data, bytes) else bytes(data)
    except Exception as exc:
        print(f"[STORAGE ERROR] PDF download failed: {exc!r}", flush=True)
        raise HTTPException(status_code=404, detail="The stored PDF is unavailable in cloud storage.") from exc


def create_paper(
    db: Session,
    pdf_content: bytes,
    original_filename: str | None,
    summary: str,
    pages: int,
    user_id: int,
    classification: dict[str, list[str]] | None = None,
) -> ResearchPaper:
    filename = _safe_filename(original_filename)
    title = Path(filename).stem[:255] or "Untitled Research Paper"
    stored_filename = f"{uuid4().hex}.pdf"
    object_key = f"user-{user_id}/{stored_filename}"

    try:
        _storage_client().storage.from_(BUCKET_NAME).upload(
            path=object_key,
            file=pdf_content,
            file_options={"content-type": "application/pdf", "upsert": "false"},
        )
    except Exception as exc:
        print(f"[STORAGE ERROR] PDF upload failed: {exc!r}", flush=True)
        raise HTTPException(status_code=502, detail="Could not save the PDF to cloud storage.") from exc

    paper = ResearchPaper(
        title=title,
        filename=filename,
        stored_filename=stored_filename,
        file_path=object_key,
        summary=summary,
        pages=pages,
        user_id=user_id,
        classification=classification or {},
    )
    try:
        db.add(paper)
        db.commit()
        db.refresh(paper)
    except Exception:
        db.rollback()
        try:
            _storage_client().storage.from_(BUCKET_NAME).remove([object_key])
        except Exception as cleanup_exc:
            print(f"[STORAGE WARNING] Orphan cleanup failed: {cleanup_exc!r}", flush=True)
        raise
    return paper


PAPER_CATEGORIES = ("Uncategorized", "Industry", "Technology", "Product", "Importance")


def list_papers(db: Session, user_id: int, search: str | None = None,
                saved_only: bool = False, category: str | None = None):
    query = db.query(ResearchPaper).filter(ResearchPaper.user_id == user_id)
    if search and search.strip():
        query = query.filter(ResearchPaper.title.ilike(f"%{search.strip()}%"))
    if saved_only:
        query = query.filter(ResearchPaper.is_saved.is_(True))
    if category:
        if category not in PAPER_CATEGORIES:
            raise HTTPException(status_code=422, detail="Choose a valid paper category.")
        query = query.filter(ResearchPaper.category == category)
    return query.order_by(ResearchPaper.uploaded_at.desc()).all()


def get_paper_or_404(db: Session, paper_id: int, user_id: int) -> ResearchPaper:
    paper = db.query(ResearchPaper).filter(
        ResearchPaper.id == paper_id, ResearchPaper.user_id == user_id
    ).first()
    if paper is None:
        raise HTTPException(status_code=404, detail="Research paper not found.")
    return paper


def toggle_saved(db: Session, paper_id: int, user_id: int) -> ResearchPaper:
    paper = get_paper_or_404(db, paper_id, user_id)
    paper.is_saved = not bool(paper.is_saved)
    db.commit()
    db.refresh(paper)
    return paper


def update_paper(db: Session, paper_id: int, user_id: int,
                 title: str | None = None, category: str | None = None,
                 classification: dict[str, list[str]] | None = None) -> ResearchPaper:
    paper = get_paper_or_404(db, paper_id, user_id)
    if title is not None:
        title = title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Paper title cannot be empty.")
        if len(title) > 255:
            raise HTTPException(status_code=422, detail="Paper title cannot exceed 255 characters.")
        paper.title = title
    if category is not None:
        if category not in PAPER_CATEGORIES:
            raise HTTPException(status_code=422, detail="Choose a valid paper category.")
        paper.category = category
    if classification is not None:
        try:
            paper.classification = validate_classification(classification)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(paper)
    return paper


def delete_paper(db: Session, paper_id: int, user_id: int) -> None:
    paper = get_paper_or_404(db, paper_id, user_id)
    location = str(paper.file_path or "")
    db.delete(paper)
    db.commit()
    if _is_legacy_local_path(location):
        Path(location).unlink(missing_ok=True)
        return
    try:
        _storage_client().storage.from_(BUCKET_NAME).remove([location])
    except Exception as exc:
        print(f"[STORAGE WARNING] Storage cleanup failed for {location!r}: {exc!r}", flush=True)
