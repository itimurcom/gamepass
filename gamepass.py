#!/usr/bin/env python3
"""
PC Game Pass catalog dumper (EN/US only) - stdlib only
Output: .cache directory with one raw Microsoft Store product JSON per game.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SIGL_URL = "https://catalog.gamepass.com/sigls/v2"
DISPLAYCATALOG_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"
PC_GAMEPASS_SIGL = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"

DEFAULT_HEADERS = {
    "User-Agent": "gamepass-catalog-dumper/1.0",
    "Accept": "application/json",
}


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


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _build_url(base: str, params: Dict[str, str]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def _http_get_json(url: str, timeout_s: float) -> Any:
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_sigl_big_ids(cfg: Config) -> Tuple[Set[str], Dict[str, Any]]:
    """
    SIGL endpoint may return either:
      - dict with key "products": [ { "id": "..."} ... ]
      - OR directly a list of products
    We support both to avoid crashes on payload shape differences.
    """
    url = _build_url(SIGL_URL, {"id": cfg.sigl_id, "market": cfg.market, "language": cfg.language})
    payload = _http_get_json(url, cfg.timeout_s)

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


def fetch_products(cfg: Config, big_ids: List[str]) -> List[Dict[str, Any]]:
    url = _build_url(
        DISPLAYCATALOG_URL,
        {"bigIds": ",".join(big_ids), "market": cfg.market, "languages": cfg.language},
    )
    payload = _http_get_json(url, cfg.timeout_s)
    products = payload.get("Products", []) if isinstance(payload, dict) else []
    return products if isinstance(products, list) else []


def chunked(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def run(cfg: Config) -> None:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    meta = cfg.out_dir / "_meta"
    meta.mkdir(exist_ok=True)

    ids, sigl_meta = fetch_sigl_big_ids(cfg)
    (meta / "sigl_US_en-us.json").write_text(json.dumps(sigl_meta, indent=2), encoding="utf-8")

    for batch in chunked(sorted(ids), cfg.batch_size):
        products = fetch_products(cfg, batch)
        for p in products:
            if not isinstance(p, dict):
                continue
            pid = p.get("ProductId")
            if isinstance(pid, str) and pid:
                (cfg.out_dir / f"{pid}.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
        time.sleep(cfg.sleep_s)


def main() -> None:
    cfg = Config(
        market="US",
        language="en-us",
        out_dir=Path(".cache"),
        sigl_id=PC_GAMEPASS_SIGL,
        batch_size=100,
        sleep_s=0.2,
        timeout_s=30.0,
        retries=3,
    )
    run(cfg)


if __name__ == "__main__":
    main()
