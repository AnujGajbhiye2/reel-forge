"""
Central logging setup for ReelForge.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def setup_logging(mode: str = "dev", logs_dir: str = "logs") -> Tuple[logging.Logger, Path]:
    """
    Configure a dedicated application logger.

    Dev mode: file + console.
    Prod mode: file only.
    """
    normalized = (mode or "dev").strip().lower()
    if normalized not in {"dev", "prod"}:
        normalized = "dev"

    log_dir = Path(logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"reelforge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("reelforge")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Reset handlers so repeated command invocations don't duplicate logs.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_level = logging.DEBUG if normalized == "dev" else logging.INFO
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if normalized == "dev":
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger, log_path


def get_logger() -> logging.Logger:
    """Return the shared ReelForge logger."""
    return logging.getLogger("reelforge")

