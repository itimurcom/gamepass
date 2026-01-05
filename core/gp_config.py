from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

# PC Game Pass SIGL
PC_GAMEPASS_SIGL = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"


@dataclass(frozen=True)
class LanguageProfile:
    """
    Human-friendly language code -> market + language (as used by Xbox/Game Pass endpoints).
    Example:
      uk-UA -> code "UA", market "UA"
      en-US -> code "EN", market "US"
    """
    code: str
    market: str
    language: str


# Languages to parse (order matters for output)
LANGUAGES: List[LanguageProfile] = [
    LanguageProfile(code="UA", market="UA", language="uk-UA"),
    LanguageProfile(code="EN", market="US", language="en-US"),
]


@dataclass(frozen=True)
class Config:
    market: str
    language: str
    out_dir: Path
    sigl_id: str
    batch_size: int
    sleep_s: float
    timeout_s: float
    retries: int
