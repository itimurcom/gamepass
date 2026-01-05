from __future__ import annotations

import os
import sys
from typing import Final

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


_last_progress_len: int = 0
_progress_active: bool = False


def _progress_done_internal() -> None:
    global _last_progress_len, _progress_active
    if not _progress_active:
        return
    sys.stderr.write("\n")
    sys.stderr.flush()
    _last_progress_len = 0
    _progress_active = False


def _progress_clear_line() -> None:
    if _progress_active:
        _progress_done_internal()


def _emit(tag: str, color: str, msg: str) -> None:
    # Ensure normal logs don't collide with progress bar line
    _progress_clear_line()

    if _use_color():
        print(f"{color}{tag}{ANSI_RESET} {msg}", file=sys.stderr)
    else:
        print(f"{tag} {msg}", file=sys.stderr)


def log_process(msg: str) -> None:
    _emit("[PROCESS]", ANSI_GREEN_LIGHT, msg)


def log_info(msg: str) -> None:
    _emit("[INFO]", ANSI_BLUE, msg)


def log_warn(msg: str) -> None:
    _emit("[WARN]", ANSI_YELLOW, msg)


def log_error(msg: str) -> None:
    _emit("[ERROR]", ANSI_RED, msg)


def print_project(title_with_version: str) -> None:
    log_info(f"Project: {title_with_version}")


def print_stage(stage_no: int, title: str) -> None:
    log_process(f"Stage {stage_no}. {title}")


def print_stage_result(stage_no: int, result_text: str) -> None:
    log_info(f"Stage {stage_no} result: {result_text}")


def print_overall_result(result_text: str) -> None:
    log_info(f"Overall result: {result_text}")


def progress_update(current: int, total: int, *, text: str = "", width: int = 24) -> None:
    """
    Draw a single-line progress bar WITH a [PROCESS] tag and optional text.
    Uses '-=' characters (filled='=', empty='-').
    Each update overwrites the same line using carriage return.
    """
    global _last_progress_len, _progress_active

    if total <= 0:
        return

    current = max(0, min(current, total))
    ratio = current / total
    filled = int(ratio * width)
    bar = "=" * filled + "-" * (width - filled)
    pct = int(ratio * 100)

    tag = "[PROCESS]"
    msg = f"{bar} {current}/{total} {pct}%"
    if text:
        msg = f"{msg} | {text}"

    if _use_color():
        line = f"{ANSI_GREEN_LIGHT}{tag}{ANSI_RESET} {msg}"
    else:
        line = f"{tag} {msg}"

    _progress_active = True
    sys.stderr.write("\r" + line)
    pad = max(0, _last_progress_len - len(line))
    if pad:
        sys.stderr.write(" " * pad)
    sys.stderr.flush()
    _last_progress_len = len(line)


def progress_done(*, final_text: str = "") -> None:
    """
    Finish the progress bar line with a newline.
    If final_text is provided, it will replace the progress line one last time.
    """
    global _last_progress_len, _progress_active
    if not _progress_active:
        return

    if final_text:
        tag = "[PROCESS]"
        if _use_color():
            line = f"{ANSI_GREEN_LIGHT}{tag}{ANSI_RESET} {final_text}"
        else:
            line = f"{tag} {final_text}"
        sys.stderr.write("\r" + line)
        pad = max(0, _last_progress_len - len(line))
        if pad:
            sys.stderr.write(" " * pad)
        sys.stderr.flush()
        _last_progress_len = len(line)

    _progress_done_internal()
