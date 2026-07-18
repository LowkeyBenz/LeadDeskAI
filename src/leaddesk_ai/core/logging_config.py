from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from .paths import LOG_DIR


def configure_logging() -> None:
    log_file = LOG_DIR / "leaddesk.log"
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
