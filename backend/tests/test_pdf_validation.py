import sys
from pathlib import Path
import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import validate_pdf_signature  # noqa: E402


def test_validate_pdf_signature_accepts_valid_pdf_header():
    validate_pdf_signature(b"%PDF-1.7\n...")


def test_validate_pdf_signature_rejects_non_pdf_bytes():
    with pytest.raises(HTTPException) as exc_info:
        validate_pdf_signature(b"<html>not a pdf</html>")
    assert exc_info.value.status_code == 400
    assert "Invalid PDF file signature" in exc_info.value.detail
