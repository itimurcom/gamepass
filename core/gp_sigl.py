from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Tuple

from .gp_config import Config
from .gp_net import http_get_json

SIGL_V2_URL = "https://catalog.gamepass.com/sigls/v2"


def _build_sigl_url(*, sigl_id: str, market: str, language: str) -> str:
    return SIGL_V2_URL + "?" + urllib.parse.urlencode({"id": sigl_id, "market": market, "language": language})


def _extract_ids(payload: Any) -> List[str]:
    """Extract ProductIds from SIGL v2 response.

    Observed shape (SIGL v2):
      [
        { "siglId": "...", "title": "...", ... },   # metadata
        { "id": "9NPDN9R45JX4" },
        { "id": "BQ1W1T1FC14W" },
        ...
      ]
    Some other endpoints/variants may return dicts or arrays of strings/objects.
    """
    if isinstance(payload, list):
        out: List[str] = []
        for x in payload:
            if isinstance(x, str) and x:
                out.append(x)
                continue
            if isinstance(x, dict):
                v = x.get("id") or x.get("Id") or x.get("productId") or x.get("ProductId")
                if isinstance(v, str) and v:
                    out.append(v)

        # de-dup while preserving order
        seen = set()
        uniq: List[str] = []
        for v in out:
            if v in seen:
                continue
            seen.add(v)
            uniq.append(v)
        return uniq

    if not isinstance(payload, dict):
        return []

    for key in ("ids", "Ids", "Products", "products"):
        v = payload.get(key)
        if isinstance(v, list):
            out: List[str] = []
            for x in v:
                if isinstance(x, str) and x:
                    out.append(x)
                elif isinstance(x, dict):
                    vv = x.get("id") or x.get("Id") or x.get("productId") or x.get("ProductId")
                    if isinstance(vv, str) and vv:
                        out.append(vv)
            if out:
                seen = set()
                uniq: List[str] = []
                for vv in out:
                    if vv in seen:
                        continue
                    seen.add(vv)
                    uniq.append(vv)
                return uniq

    for key in ("sigl", "data", "result"):
        v = payload.get(key)
        if isinstance(v, dict):
            out = _extract_ids(v)
            if out:
                return out

    return []


def fetch_sigl_ids(cfg: Config, *, sigl_id: str) -> Tuple[List[str], Dict[str, Any]]:
    url = _build_sigl_url(sigl_id=sigl_id, market=cfg.market, language=cfg.language)
    payload = http_get_json(url, cfg.timeout_s)
    ids = _extract_ids(payload)
    meta: Dict[str, Any] = {
        "url": url,
        "sigl_id": sigl_id,
        "market": cfg.market,
        "language": cfg.language,
        "ids_count": len(ids),
        "payload_type": type(payload).__name__,
    }
    return ids, meta
