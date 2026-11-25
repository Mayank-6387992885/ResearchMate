"""Citation formatting utilities for BibTeX, RIS, and APA exports."""
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

SUPPORTED_FORMATS = ("bibtex", "ris", "apa")


def _extract_year(paper: Any) -> int:
    year = getattr(paper, "year", None)
    if isinstance(year, int) and 1900 <= year <= 2100:
        return year
    if isinstance(year, str) and year.isdigit() and 1900 <= int(year) <= 2100:
        return int(year)
    uploaded_at = getattr(paper, "uploaded_at", None)
    if isinstance(uploaded_at, datetime):
        return uploaded_at.year
    return datetime.now(timezone.utc).year


def _extract_authors(paper: Any) -> list[str]:
    raw = getattr(paper, "authors", None)
    if isinstance(raw, list):
        cleaned = [str(a).strip() for a in raw if str(a).strip()]
        if cleaned:
            return cleaned
    elif isinstance(raw, str) and raw.strip():
        parts = [p.strip() for p in re.split(r"\s*;\s*|\s+and\s+", raw.strip()) if p.strip()]
        if parts:
            return parts
    return ["Unknown Author"]


def _bibtex_key(paper: Any, authors: list[str], year: int) -> str:
    first_author = authors[0] if authors else "paper"
    last_word = re.sub(r"[^a-zA-Z0-9]", "", first_author.split()[-1].lower()) or "paper"
    paper_id = getattr(paper, "id", None)
    suffix = f"_{paper_id}" if paper_id is not None else ""
    return f"{last_word}{year}{suffix}"


def _escape_bibtex(value: str) -> str:
    return value.replace("{", "\\{").replace("}", "\\}")


def format_bibtex(paper: Any) -> str:
    title = (getattr(paper, "title", None) or "Untitled Research Paper").strip()
    authors = _extract_authors(paper)
    year = _extract_year(paper)
    key = _bibtex_key(paper, authors, year)

    fields = [
        f"  author = {{{_escape_bibtex(' and '.join(authors))}}}",
        f"  title = {{{_escape_bibtex(title)}}}",
        f"  year = {{{year}}}",
    ]

    doi = getattr(paper, "doi", None)
    if doi and str(doi).strip():
        fields.append(f"  doi = {{{str(doi).strip()}}}")

    arxiv_id = getattr(paper, "arxiv_id", None)
    if arxiv_id and str(arxiv_id).strip():
        fields.append(f"  eprint = {{{str(arxiv_id).strip()}}}")
        fields.append("  archivePrefix = {arXiv}")

    pages = getattr(paper, "pages", None)
    if isinstance(pages, int) and pages > 0:
        fields.append(f"  pages = {{1--{pages}}}")

    journal = getattr(paper, "journal", None) or getattr(paper, "venue", None)
    if journal and str(journal).strip():
        fields.append(f"  journal = {{{_escape_bibtex(str(journal).strip())}}}")

    return f"@article{{{key},\n" + ",\n".join(fields) + "\n}\n"


def format_ris(paper: Any) -> str:
    title = (getattr(paper, "title", None) or "Untitled Research Paper").strip()
    authors = _extract_authors(paper)
    year = _extract_year(paper)

    lines = ["TY  - JOUR"]
    for author in authors:
        lines.append(f"AU  - {author}")
    lines.append(f"TI  - {title}")
    lines.append(f"PY  - {year}")

    journal = getattr(paper, "journal", None) or getattr(paper, "venue", None)
    if journal and str(journal).strip():
        lines.append(f"JO  - {str(journal).strip()}")

    doi = getattr(paper, "doi", None)
    if doi and str(doi).strip():
        lines.append(f"DO  - {str(doi).strip()}")

    arxiv_id = getattr(paper, "arxiv_id", None)
    if arxiv_id and str(arxiv_id).strip():
        lines.append(f"N1  - arXiv:{str(arxiv_id).strip()}")

    pages = getattr(paper, "pages", None)
    if isinstance(pages, int) and pages > 0:
        lines.append("SP  - 1")
        lines.append(f"EP  - {pages}")

    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def format_apa(paper: Any) -> str:
    title = (getattr(paper, "title", None) or "Untitled Research Paper").strip()
    authors = _extract_authors(paper)
    year = _extract_year(paper)

    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        author_str = f"{authors[0]}, & {authors[1]}"
    else:
        author_str = f"{', '.join(authors[:-1])}, & {authors[-1]}"

    citation = f"{author_str} ({year}). {title}."

    journal = getattr(paper, "journal", None) or getattr(paper, "venue", None)
    if journal and str(journal).strip():
        citation += f" {str(journal).strip()}."

    doi = getattr(paper, "doi", None)
    arxiv_id = getattr(paper, "arxiv_id", None)
    if doi and str(doi).strip():
        citation += f" https://doi.org/{str(doi).strip()}"
    elif arxiv_id and str(arxiv_id).strip():
        citation += f" arXiv:{str(arxiv_id).strip()}"

    return citation + "\n"


def format_citation(paper: Any, fmt: str = "bibtex") -> tuple[str, str, str]:
    """Return (content, media_type, file_extension) for the requested citation format."""
    normalized = (fmt or "bibtex").strip().lower()
    if normalized == "bibtex":
        return format_bibtex(paper), "application/x-bibtex; charset=utf-8", "bib"
    if normalized == "ris":
        return format_ris(paper), "application/x-research-info-systems; charset=utf-8", "ris"
    if normalized == "apa":
        return format_apa(paper), "text/plain; charset=utf-8", "txt"
    raise HTTPException(
        status_code=422,
        detail="Unsupported citation format. Choose 'bibtex', 'ris', or 'apa'.",
    )
