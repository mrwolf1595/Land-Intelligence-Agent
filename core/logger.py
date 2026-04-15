"""
Centralized structured logger for all agent modules.
Usage: from core.logger import get_logger; logger = get_logger(__name__)
"""
import logging
import sys
from pathlib import Path

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

_FMT = logging.Formatter(
    "[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that writes to stdout and logs/agent.log."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_FMT)
    # Force UTF-8 on Windows terminals (avoids cp1252 crash with Arabic text)
    if hasattr(ch.stream, "reconfigure"):
        try:
            ch.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logger.addHandler(ch)

    fh = logging.FileHandler(_LOG_DIR / "agent.log", encoding="utf-8")
    fh.setFormatter(_FMT)
    logger.addHandler(fh)

    return logger
