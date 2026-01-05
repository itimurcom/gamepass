from __future__ import annotations

import os
import sys
import time
from typing import Final, Optional

# Colors:
# PROCESS - light green, INFO - blue, WARN - yellow, ERROR - red
ANSI_RESET: Final[str] = "\x1b[0m"
ANSI_GREEN_LIGHT: Final[str] = "\x1b[92m"
ANSI_BLUE: Final[str] = "\x1b[94m"
ANSI_YELLOW: Final[str] = "\x1b[93m"
ANSI_RED: Final[str] = "\x1b[91m"


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _emit(tag: str, color: str, msg: str) -> None:
    # If progress bar was on screen, ensure we start on a fresh line
    _progress_clear_line()

    if _use_color():
        print(f"{color}{tag}{ANSI_RESET} {msg}", file=sys.stderr)
    else:
        print(f"{tag} {msg}", file=sys.stderr)


def log_process(msg: str) -> None:
    _emit("[PROCESS]", ANSI_GREEN_LIGHT, f"{_ts()} {msg}")


def log_info(msg: str) -> None:
    _emit("[INFO]", ANSI_BLUE, f"{_ts()} {msg}")


def log_warn(msg: str) -> None:
    _emit("[WARN]", ANSI_YELLOW, f"{_ts()} {msg}")


def log_error(msg: str) -> None:
    _emit("[ERROR]", ANSI_RED, f"{_ts()} {msg}")


# -------------------------
# Progress bar (stderr)
# -------------------------

_last_progress_len: int = 0
_progress_active: bool = False


def progress_update(current: int, total: int, *, prefix: str = "", width: int = 24) -> None:
    """
    Draw a simple progress bar on one stderr line.
    Call repeatedly; call progress_done() when finished.
    """
    global _last_progress_len, _progress_active

    if total <= 0:
        return

    current = max(0, min(current, total))
    ratio = current / total
    filled = int(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    pct = int(ratio * 100)

    text = f"{prefix}[{bar}] {current}/{total} {pct}%"
    _progress_active = True

    # Carriage return and overwrite
    sys.stderr.write("\r" + text)
    pad = max(0, _last_progress_len - len(text))
    if pad:
        sys.stderr.write(" " * pad)
    sys.stderr.flush()
    _last_progress_len = len(text)


def progress_done(*, suffix: str = "") -> None:
    global _last_progress_len, _progress_active
    if not _progress_active:
        return
    if suffix:
        sys.stderr.write("\r" + suffix)
        pad = max(0, _last_progress_len - len(suffix))
        if pad:
            sys.stderr.write(" " * pad)
    sys.stderr.write("\n")
    sys.stderr.flush()
    _last_progress_len = 0
    _progress_active = False


def _progress_clear_line() -> None:
    # If a progress bar is active, move to new line before normal logs.
    if _progress_active:
        progress_done()
