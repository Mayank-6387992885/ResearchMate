"""Extraction of embedded diagrams, figures, and charts from research paper PDFs using PyMuPDF."""

import base64
import hashlib
import io
import re
from typing import Any

import pymupdf


def _clean_caption(text: str) -> str:
    """Normalize figure caption extracted from PDF text blocks."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    single_line = " ".join(lines)
    # Truncate at reasonable length
    if len(single_line) > 160:
        return single_line[:157] + "..."
    return single_line


def extract_paper_figures(pdf_bytes: bytes, max_figures: int = 8) -> list[dict[str, Any]]:
    """Extract diagrams, plots, architecture drawings, and figures from a PDF.
    
    Extracts both embedded raster images and rendered figure regions, pairing them
    with any detected figure captions on the corresponding page.
    """
    if not pdf_bytes:
        return []

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        print(f"[FIGURES] Could not open PDF for figure extraction: {exc}", flush=True)
        return []

    figures: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for page_idx in range(len(doc)):
        if len(figures) >= max_figures:
            break

        try:
            page = doc[page_idx]
            page_num = page_idx + 1

            # Extract captions from text blocks on this page
            text_blocks = page.get_text("blocks") or []
            caption_blocks = []
            for b in text_blocks:
                if len(b) >= 5 and isinstance(b[4], str):
                    raw_text = b[4].strip()
                    if re.match(r"^(figure|fig\.|chart|diagram|table)\s*\d+", raw_text, re.IGNORECASE):
                        caption_blocks.append({
                            "rect": pymupdf.Rect(b[:4]),
                            "text": _clean_caption(raw_text),
                        })

            caption_iter = iter(caption_blocks)

            # 1. Try to extract embedded raster images
            images = page.get_images(full=True) or []
            page_extracted_any = False

            for img_info in images:
                if len(figures) >= max_figures:
                    break
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter out tiny icons, logos, equation fragments, and thin separator bars
                    if width < 120 or height < 120:
                        continue

                    raw_bytes = base_image.get("image", b"")
                    if not raw_bytes:
                        continue

                    # Deduplicate identical images across pages (e.g. repeated header graphics)
                    img_hash = hashlib.md5(raw_bytes).hexdigest()
                    if img_hash in seen_hashes:
                        continue
                    seen_hashes.add(img_hash)

                    ext = base_image.get("ext", "png").lower()
                    if ext not in ("png", "jpeg", "jpg", "webp"):
                        ext = "png"
                    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

                    matched_caption = next(caption_iter, None)
                    caption_text = (
                        matched_caption["text"]
                        if matched_caption
                        else f"Figure {len(figures) + 1} (Page {page_num})"
                    )

                    b64 = base64.b64encode(raw_bytes).decode("utf-8")
                    figures.append({
                        "id": len(figures) + 1,
                        "page": page_num,
                        "caption": caption_text,
                        "width": width,
                        "height": height,
                        "data_url": f"data:{mime};base64,{b64}",
                    })
                    page_extracted_any = True
                except Exception as exc:
                    print(f"[FIGURES] Notice: image xref {xref} extract error: {exc}", flush=True)

            # 2. If this page has a Figure caption block but no raster images were extracted
            # (common for vector diagrams like neural network architectures), render the figure clip
            if not page_extracted_any and caption_blocks:
                for cap in caption_blocks:
                    if len(figures) >= max_figures:
                        break
                    try:
                        cap_rect = cap["rect"]
                        # Bounding region right above the caption where the diagram resides
                        clip_top = max(0, cap_rect.y0 - 380)
                        clip_rect = pymupdf.Rect(
                            max(0, cap_rect.x0 - 40),
                            clip_top,
                            min(page.rect.width, cap_rect.x1 + 400),
                            min(page.rect.height, cap_rect.y1 + 10),
                        )
                        # Ensure reasonable dimensions
                        if clip_rect.width < 100 or clip_rect.height < 100:
                            clip_rect = pymupdf.Rect(0, clip_top, page.rect.width, cap_rect.y1 + 10)

                        pix = page.get_pixmap(clip=clip_rect, dpi=130)
                        raw_bytes = pix.tobytes("png")
                        if not raw_bytes or len(raw_bytes) < 1500:
                            continue

                        img_hash = hashlib.md5(raw_bytes).hexdigest()
                        if img_hash in seen_hashes:
                            continue
                        seen_hashes.add(img_hash)

                        b64 = base64.b64encode(raw_bytes).decode("utf-8")
                        figures.append({
                            "id": len(figures) + 1,
                            "page": page_num,
                            "caption": cap["text"],
                            "width": pix.width,
                            "height": pix.height,
                            "data_url": f"data:image/png;base64,{b64}",
                        })
                    except Exception as exc:
                        print(f"[FIGURES] Notice: vector figure clip render error: {exc}", flush=True)

        except Exception as exc:
            print(f"[FIGURES] Notice: page {page_idx + 1} figure processing error: {exc}", flush=True)

    print(f"[FIGURES] Successfully extracted {len(figures)} figures from PDF.", flush=True)
    return figures
