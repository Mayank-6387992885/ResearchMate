"""arXiv and CrossRef/DOI metadata and open-access PDF import service."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

ARXIV_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/[0-9]{7}(?:v\d+)?)(?:\.pdf)?",
    re.IGNORECASE,
)
ARXIV_PREFIX_RE = re.compile(
    r"^arxiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/[0-9]{7}(?:v\d+)?)$",
    re.IGNORECASE,
)
ARXIV_BARE_RE = re.compile(
    r"^([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)$",
    re.IGNORECASE,
)
DOI_URL_RE = re.compile(
    r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
    re.IGNORECASE,
)
DOI_PREFIX_RE = re.compile(
    r"^doi:\s*(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)$",
    re.IGNORECASE,
)
DOI_BARE_RE = re.compile(
    r"^(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)$",
    re.IGNORECASE,
)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
MAX_PDF_BYTES = 10 * 1024 * 1024


@dataclass
class ImportedPaper:
    source: str
    identifier: str
    title: str
    authors: list[str]
    year: int | None
    abstract: str
    pdf_url: str
    pdf_content: bytes
    filename: str

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "identifier": self.identifier,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "abstract": self.abstract,
            "pdf_url": self.pdf_url,
        }


def parse_identifier(raw: str) -> tuple[str, str]:
    """Return ('arxiv' | 'doi', normalized_id) or raise HTTPException(400)."""
    text = (raw or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Please enter an arXiv ID/URL or DOI.")

    for pattern in (ARXIV_URL_RE, ARXIV_PREFIX_RE, ARXIV_BARE_RE):
        match = pattern.search(text)
        if match:
            return "arxiv", match.group(1)

    for pattern in (DOI_URL_RE, DOI_PREFIX_RE, DOI_BARE_RE):
        match = pattern.search(text)
        if match:
            return "doi", match.group(1).rstrip(".")

    raise HTTPException(
        status_code=400,
        detail="Unrecognized identifier. Enter a valid arXiv ID/URL (e.g. 2301.07041) or DOI (e.g. 10.1038/...).",
    )


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", without_tags).strip()


def _safe_pdf_filename(title: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
    base = (slug or fallback)[:120]
    return f"{base}.pdf"


def _download_pdf(client: httpx.Client, url: str) -> bytes:
    try:
        resp = client.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to download PDF from {url}: {exc}") from exc

    content = resp.content
    if not content:
        raise HTTPException(status_code=502, detail="Downloaded PDF is empty.")
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Downloaded PDF exceeds the 10 MB size limit.")
    content_type = resp.headers.get("content-type", "").lower()
    if not content.startswith(b"%PDF") and "pdf" not in content_type:
        raise HTTPException(status_code=422, detail="The linked resource did not return a valid PDF file.")
    return content


def _fetch_arxiv(client: httpx.Client, arxiv_id: str) -> ImportedPaper:
    api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        resp = client.get(api_url, timeout=20.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch arXiv metadata: {exc}") from exc

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise HTTPException(status_code=502, detail="Invalid XML response from arXiv API.") from exc

    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"arXiv paper '{arxiv_id}' not found.")

    title = _clean_text(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    if not title:
        raise HTTPException(status_code=404, detail=f"arXiv paper '{arxiv_id}' not found.")

    authors = [
        _clean_text(a.findtext("atom:name", default="", namespaces=ATOM_NS))
        for a in entry.findall("atom:author", ATOM_NS)
    ]
    authors = [a for a in authors if a]

    published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
    year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
    abstract = _clean_text(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("title") == "pdf" and link.attrib.get("href"):
            pdf_url = link.attrib["href"]
            if not pdf_url.endswith(".pdf"):
                pdf_url = f"{pdf_url}.pdf"
            break

    pdf_content = _download_pdf(client, pdf_url)
    return ImportedPaper(
        source="arxiv",
        identifier=arxiv_id,
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        pdf_url=pdf_url,
        pdf_content=pdf_content,
        filename=_safe_pdf_filename(title, arxiv_id.replace("/", "_")),
    )


def _extract_crossref_year(message: dict[str, Any]) -> int | None:
    for field in ("published-print", "published-online", "issued", "created"):
        parts = (message.get(field) or {}).get("date-parts")
        if parts and isinstance(parts, list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def _fetch_doi(client: httpx.Client, doi: str) -> ImportedPaper:
    api_url = f"https://api.crossref.org/works/{doi}"
    try:
        resp = client.get(api_url, timeout=20.0)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"DOI '{doi}' not found in CrossRef.")
        resp.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch CrossRef metadata: {exc}") from exc

    message = (resp.json() or {}).get("message") or {}
    titles = message.get("title") or []
    title = _clean_text(titles[0]) if titles else doi

    authors: list[str] = []
    for author in message.get("author") or []:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        full_name = f"{given} {family}".strip()
        if full_name:
            authors.append(full_name)

    year = _extract_crossref_year(message)
    abstract = _clean_text(message.get("abstract"))

    pdf_url = ""
    for link in message.get("link") or []:
        if (link.get("content-type") or "").lower() == "application/pdf" and link.get("URL"):
            pdf_url = link["URL"]
            break

    if not pdf_url:
        try:
            unpaywall_resp = client.get(
                f"https://api.unpaywall.org/v2/{doi}",
                params={"email": "researchmate@example.com"},
                timeout=15.0,
            )
            if unpaywall_resp.status_code == 200:
                best_oa = (unpaywall_resp.json() or {}).get("best_oa_location") or {}
                pdf_url = best_oa.get("url_for_pdf") or ""
        except httpx.HTTPError:
            pdf_url = ""

    if not pdf_url:
        raise HTTPException(
            status_code=422,
            detail="No open-access PDF found for this DOI. Please download the PDF manually and upload it.",
        )

    pdf_content = _download_pdf(client, pdf_url)
    return ImportedPaper(
        source="doi",
        identifier=doi,
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        pdf_url=pdf_url,
        pdf_content=pdf_content,
        filename=_safe_pdf_filename(title, doi.replace("/", "_")),
    )


def fetch_paper_from_identifier(identifier: str) -> ImportedPaper:
    """Resolve an arXiv ID/URL or DOI, fetch metadata, and download its PDF."""
    source, normalized = parse_identifier(identifier)
    with httpx.Client(headers={"User-Agent": "ResearchMate/1.0"}) as client:
        if source == "arxiv":
            return _fetch_arxiv(client, normalized)
        return _fetch_doi(client, normalized)
