

def ocr_page_with_tesseract(page) -> str:
    """Run OCR on a PyMuPDF page pixmap using pytesseract, returning extracted text or empty string."""
    try:
        import io
        from PIL import Image
        import pytesseract

        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""
