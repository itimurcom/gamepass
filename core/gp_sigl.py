from __future__ import annotations

import time
from typing import Any, Dict, Set, Tuple

from .gp_config import Config
from .gp_net import http_get_json
from .core import build_url

SIGL_URL = "https://catalog.gamepass.com/sigls/v2"


def fetch_sigl_big_ids(cfg: Config) -> Tuple[Set[str], Dict[str, Any]]:
    """
    SIGL endpoint may return either:
      - dict with key "products": [ { "id": "..."} ... ]
      - OR directly a list of products
    """
    url = build_url(SIGL_URL, {"id": cfg.sigl_id, "market": cfg.market, "language": cfg.language})
    payload = http_get_json(url, cfg.timeout_s)

    if isinstance(payload, dict):
        products = payload.get("products", [])
        raw_payload = payload
    elif isinstance(payload, list):
        products = payload
        raw_payload = payload
    else:
        products = []
        raw_payload = payload

    big_ids: Set[str] = set()
    for p in products:
        if isinstance(p, dict):
            pid = p.get("id")
            if isinstance(pid, str) and pid:
                big_ids.add(pid)

    meta = {
        "sigl_id": cfg.sigl_id,
        "market": cfg.market,
        "language": cfg.language,
        "count": len(big_ids),
        "timestamp": int(time.time()),
        "raw": raw_payload,
    }
    return big_ids, meta
