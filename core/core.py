from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .gp_config import Config
from .gp_net import http_get_json

DISPLAYCATALOG_URL = "https://displaycatalog.mp.microsoft.com/v7.0/products"


def build_url(base: str, params: Dict[str, str]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def chunked(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def ensure_dirs(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir = out_dir / "_meta"
    meta_dir.mkdir(exist_ok=True)
    return meta_dir


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def write_product(out_dir: Path, product: Dict[str, Any]) -> bool:
    pid = product.get("ProductId")
    if not isinstance(pid, str) or not pid:
        return False
    (out_dir / f"{pid}.json").write_text(json.dumps(product, indent=2), encoding="utf-8")
    return True


def fetch_products(cfg: Config, big_ids: List[str]) -> List[Dict[str, Any]]:
    url = build_url(
        DISPLAYCATALOG_URL,
        {"bigIds": ",".join(big_ids), "market": cfg.market, "languages": cfg.language},
    )
    payload = http_get_json(url, cfg.timeout_s)
    products = payload.get("Products", []) if isinstance(payload, dict) else []
    return products if isinstance(products, list) else []
