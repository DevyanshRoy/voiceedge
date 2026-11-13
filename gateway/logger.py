# gateway/logger.py
"""Rotating gateway log configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(path=None):
    log_path = Path(path or "voiceedge.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return handler