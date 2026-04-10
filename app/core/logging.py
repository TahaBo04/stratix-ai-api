"""Logging helpers for STRATIX AI."""
from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import get_settings


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


@lru_cache(maxsize=1)
def configure_logging() -> None:
    settings = get_settings()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
