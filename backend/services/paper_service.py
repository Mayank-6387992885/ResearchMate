
"""Database and file operations for the ResearchMate paper library."""
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from classification import validate_classification
from models.research_paper import ResearchPaper

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads" / "research_papers"
SUMMARY_DIR = BASE_DIR / "generated" / "summaries"


def _safe_filename(filename: str | None) -> str:
    # Remove both Unix and Windows path components supplied by the client.
    name = (filename or "research-paper.pdf").replace("\\", "/").split("/")[-1]
    return name[:255] or "research-paper.pdf"


def create_paper(
    db: Session,
    pdf_content: bytes,
    original_filename: str | None,
    summary: str,
    pages: int,
    user_id: int,
    classification: dict[str, list[str]] | None = None,
) -> ResearchPaper:
    """Save the PDF and its summary record after summarization succeeds."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(original_filename)
    title = Path(filename).stem[:255] or "Untitled Research Paper"
    stored_filename = f"{uuid4().hex}.pdf"
    file_path = UPLOAD_DIR / stored_filename

    file_path.write_bytes(pdf_content)

    paper = ResearchPaper(
        title=title,
        filename=filename,
        stored_filename=stored_filename,
        file_path=str(file_path),
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
        file_path.unlink(missing_ok=True)
        raise

    return paper


PAPER_CATEGORIES = ("Uncategorized", "Industry", "Technology", "Product", "Importance")


def list_papers(
    db: Session,
    user_id: int,
    search: str | None = None,
    saved_only: bool = False,
    category: str | None = None,
):
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
        ResearchPaper.id == paper_id,
        ResearchPaper.user_id == user_id,
    ).first()
    if paper is None:
        raise HTTPException(status_code=404, detail="Research paper not found.")
    return paper


def toggle_saved(db: Session, paper_id: int, user_id: int) -> ResearchPaper:
    paper = get_paper_or_404(db, paper_id, user_id)
    setattr(paper, "is_saved", not bool(paper.is_saved))
    db.commit()
    db.refresh(paper)
    return paper


def update_paper(
    db: Session,
    paper_id: int,
    user_id: int,
    title: str | None = None,
    category: str | None = None,
    classification: dict[str, list[str]] | None = None,
) -> ResearchPaper:
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
    file_path = Path(str(paper.file_path))

    db.delete(paper)
    db.commit()

    # Remove the PDF after the database record has been deleted.
    resolved_file = file_path.resolve()
    if resolved_file.parent == UPLOAD_DIR.resolve():
        resolved_file.unlink(missing_ok=True)
