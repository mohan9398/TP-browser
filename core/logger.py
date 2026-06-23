# -*- coding: utf-8 -*-
"""
Lightweight, rotating debug logger.

Disabled by default — file logging only turns on when the environment variable
TELE_BROWSER_DEBUG is set to a truthy value (1/true/yes/on). When disabled the
logger is a no-op so it costs effectively nothing in production.

Usage:
    from secure_browser.core.logger import get_logger
    log = get_logger(__name__)
    log.info("proxy bound on port %s", port)
    log.exception("scan failed")   # inside an except block
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

_DEBUG = os.environ.get("TELE_BROWSER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

_ROOT_NAME = "secure_browser"
_configured = False


def _log_dir() -> str:
    base = os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd()
    path = os.path.join(base, "SecureExamBrowser")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        return base
    return path


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger(_ROOT_NAME)
    root.propagate = False

    if not _DEBUG:
        # Production: swallow everything, no files, no overhead.
        root.addHandler(logging.NullHandler())
        root.setLevel(logging.CRITICAL + 1)
        return

    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
    )

    # Rotating file: 5 files x ~1 MB each.
    try:
        fh = RotatingFileHandler(
            os.path.join(_log_dir(), "secure_browser.log"),
            maxBytes=1_000_000, backupCount=5, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass

    # Also mirror to stderr when debugging.
    try:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    except Exception:
        pass


def get_logger(name: str = _ROOT_NAME) -> logging.Logger:
    """Return a child logger under the shared 'secure_browser' root."""
    _configure_root()
    if name and name != _ROOT_NAME and not name.startswith(_ROOT_NAME + "."):
        name = f"{_ROOT_NAME}.{name.rsplit('.', 1)[-1]}"
    return logging.getLogger(name or _ROOT_NAME)


# Backwards-compatible singleton kept for any existing callers.
class Logger:
    def __init__(self):
        self._log = get_logger(_ROOT_NAME)

    def log(self, msg: str):
        self._log.info(msg)

    def exception(self, msg: str):
        self._log.exception(msg)


logger = Logger()
