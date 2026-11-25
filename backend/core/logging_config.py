import logging
import sys

from core.config import settings


def configure_logging() -> None:
    """Configure structured application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=False,
    )
