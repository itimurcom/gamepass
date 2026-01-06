from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .gp_lists import SiglListDef, get_default_sigl_lists


@dataclass(frozen=True)
class LangProfile:
    code: str
    language: str
    market: str


LANGUAGES: List[LangProfile] = [
    LangProfile(code="EN", language="en-us", market="US"),
    LangProfile(code="UA", language="uk-ua", market="UA"),
]


@dataclass(frozen=True)
class Config:
    market: str
    language: str
    out_dir: object  # Path
    sigl_id: str | None = None
    batch_size: int = 100
    sleep_s: float = 0.2
    timeout_s: float = 30.0
    retries: int = 3


SIGL_LISTS: List[SiglListDef] = get_default_sigl_lists()
