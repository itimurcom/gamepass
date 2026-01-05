from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "gamepass-catalog-dumper/1.0",
    "Accept": "application/json",
}


def http_get_json(url: str, timeout_s: float) -> Any:
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))
