from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# PC Game Pass SIGL
PC_GAMEPASS_SIGL = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"


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
