#!/usr/bin/env python3
# gamepass.py
#
# Game Pass catalog -> HTML + CSV (table + tiles + filters + favorites)
#
# Key features:
# - Fetch list of Game Pass games from SIGL endpoint (catalog.gamepass.com)
# - Fetch product metadata from Microsoft DisplayCatalog API with autosplit (reliable)
# - Cache (resume-safe): products, wikidata search, wikidata enrich, optional HLTB hours
# - Cache self-healing: if cached JSON is invalid/missing keys -> invalidate and refetch
# - Enrichment via Wikidata (SPARQL): Genre (P136), Platforms (P400), Year (P577), Description, Wikipedia link, Review score (P444)
# - Progress indication: tqdm if installed; otherwise lightweight text progress + heartbeat
# - HTML UI: view switch (Table/Tiles), filters (Years/Genres/Rating), Favorites mode, per-row description toggle
#
# Notes:
# - Hours (HowLongToBeat) are OPTIONAL and require: pip install howlongtobeatpy (use venv on Ubuntu/Debian with PEP 668)
# - This script avoids f-string brace issues in HTML by using a static template + placeholder replacement.
#
# Usage:
#   chmod +x gamepass.py
#   ./gamepass.py
#   ./gamepass.py --quiet
#   ./gamepass.py --reset-cache
#   ./gamepass.py --no-wikidata   (skip wikidata enrichment)
#   ./gamepass.py --hltb          (enable hours if howlongtobeatpy installed)

import argparse
import csv
import html
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------- CLI ----------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true", help="Less console output (still prints milestones).")
    p.add_argument("--reset-cache", action="store_true", help="Delete cache and start over.")
    p.add_argument("--no-wikidata", action="store_true", help="Skip Wikidata enrichment.")
    p.add_argument("--hltb", action="store_true", help="Try to fetch hours from HowLongToBeat (requires howlongtobeatpy).")
    p.add_argument("--market", default="US", help="Market code (default: US).")
    p.add_argument("--language", default="en-us", help="Language (default: en-us).")
    p.add_argument("--pass-size", type=int, default=100, help="Store fetch pass size (default: 100).")
    p.add_argument("--sleep", type=float, default=0.20, help="Sleep between requests (default: 0.20).")
    return p.parse_args()

ARGS = parse_args()

# Optional tqdm
try:
    from tqdm import tqdm  # type: ignore
except Exception:
    tqdm = None

# ---------------- Settings ----------------
MARKET = ARGS.market
LANGUAGE = ARGS.language
SIGL_ALL = "29a81209-df6f-41fd-a528-2ae6b91f719c"  # Game Pass - All games

PASS_SIZE = max(1, int(ARGS.pass_size))

INITIAL_BATCH_SIZE = 40
MIN_BATCH_SIZE = 1

REQUEST_TIMEOUT_SEC = 25
RETRIES = 5
BACKOFF_BASE_SEC = 1.6
JITTER_SEC = 0.35
SLEEP_BETWEEN_REQUESTS_SEC = max(0.0, float(ARGS.sleep))

CACHE_DIR = "cache"
STATE_FILE = os.path.join(CACHE_DIR, "state.json")
SIGL_FILE = os.path.join(CACHE_DIR, "sigl_ids.json")

PRODUCTS_DIR = os.path.join(CACHE_DIR, "products")
WIKIDATA_DIR = os.path.join(CACHE_DIR, "wikidata")      # name -> QID
WD_SPARQL_DIR = os.path.join(CACHE_DIR, "wd_sparql")    # QID -> enriched fields
HLTB_DIR = os.path.join(CACHE_DIR, "hltb")              # name -> hours

OUT_HTML = "gamepass_catalog.html"
OUT_CSV = "gamepass_catalog.csv"

CACHE_SCHEMA_VERSION = 2

# ---------------- Console helpers ----------------
_last_heartbeat = 0.0
def heartbeat(force: bool = False):
    global _last_heartbeat
    now = time.time()
    if force or (now - _last_heartbeat) >= 10.0:
        print("[INFO] still working...")
        _last_heartbeat = now

def info(msg: str):
    if not ARGS.quiet:
        print(msg)

def warn(msg: str):
    print(msg)

# ---------------- Cache helpers ----------------
def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(PRODUCTS_DIR, exist_ok=True)
    os.makedirs(WIKIDATA_DIR, exist_ok=True)
    os.makedirs(WD_SPARQL_DIR, exist_ok=True)
    os.makedirs(HLTB_DIR, exist_ok=True)

def read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def write_json_atomic(path: str, obj: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def safe_filename(s: str) -> str:
    s = (s or "").strip().lower()
    out = "".join(c for c in s if c.isalnum() or c in ("-", "_"))[:180]
    return out if out else "x"

def product_cache_path(big_id: str) -> str:
    return os.path.join(PRODUCTS_DIR, f"{safe_filename(big_id)}.json")

def wd_name_cache_path(name: str) -> str:
    return os.path.join(WIKIDATA_DIR, f"{safe_filename(name)}.json")

def wd_qid_cache_path(qid: str) -> str:
    return os.path.join(WD_SPARQL_DIR, f"{safe_filename(qid)}.json")

def hltb_name_cache_path(name: str) -> str:
    return os.path.join(HLTB_DIR, f"{safe_filename(name)}.json")

def invalidate(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def is_valid_cached_product(obj: Any) -> bool:
    # Minimal structure checks to avoid "smіття" from broken cache
    if not isinstance(obj, dict):
        return False
    if obj.get("_schema") != CACHE_SCHEMA_VERSION:
        return False
    product = obj.get("product")
    if not isinstance(product, dict):
        return False
    if not (obj.get("bigId") and isinstance(obj.get("bigId"), str)):
        return False
    # expected keys in product
    if not isinstance(product.get("LocalizedProperties"), list):
        return False
    return True

def load_product_from_cache(big_id: str) -> Optional[dict]:
    path = product_cache_path(big_id)
    obj = read_json(path)
    if not is_valid_cached_product(obj):
        # self-heal: invalidate and refetch later
        if obj is not None:
            invalidate(path)
        return None
    return obj["product"]

def save_product_to_cache(big_id: str, product: dict):
    write_json_atomic(product_cache_path(big_id), {
        "_schema": CACHE_SCHEMA_VERSION,
        "bigId": big_id,
        "cached_at": datetime.now().isoformat(),
        "product": product
    })

def prompt_resume_or_reset() -> str:
    if ARGS.reset_cache:
        return "reset"
    if not os.path.exists(STATE_FILE) and not os.path.exists(SIGL_FILE):
        return "resume"
    while True:
        ans = input("Cache found. Continue (C) or start over (R)? [C/R]: ").strip().lower()
        if ans in ("c", "continue", ""):
            return "resume"
        if ans in ("r", "reset", "restart"):
            return "reset"
        print("Please type C or R.")

def reset_cache():
    for path in (STATE_FILE, SIGL_FILE):
        invalidate(path)
    for d in (PRODUCTS_DIR, WIKIDATA_DIR, WD_SPARQL_DIR, HLTB_DIR):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".json"):
                    invalidate(os.path.join(d, fn))
    print("Cache reset done.")

# ---------------- HTTP ----------------
def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
            if attempt == RETRIES:
                break
            sleep_for = (BACKOFF_BASE_SEC ** attempt) + random.uniform(0, JITTER_SEC)
            warn(f"  ! Request failed (attempt {attempt}/{RETRIES}): {e}")
            warn(f"  ! Sleeping {sleep_for:.2f}s then retrying...")
            time.sleep(sleep_for)
    raise RuntimeError(f"Request failed after {RETRIES} retries: {url}\nLast error: {last_err}")

def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    data = http_get(url, headers=headers or {"Accept": "application/json"})
    return json.loads(data.decode("utf-8", errors="replace"))

# ---------------- SIGL ----------------
def get_sigl_ids(sigl_id: str) -> List[str]:
    url = "https://catalog.gamepass.com/sigls/v2?" + urllib.parse.urlencode(
        {"id": sigl_id, "language": LANGUAGE, "market": MARKET}
    )
    data = http_get_json(url)
    ids: List[str] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            big_id = item.get("id") or item.get("productId") or item.get("bigId")
            if big_id:
                ids.append(str(big_id))
    # dedupe preserve order
    seen = set()
    out: List[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

# ---------------- Store fetch (reliable with autosplit) ----------------
def fetch_products_once(big_ids: List[str]) -> Dict[str, dict]:
    if not big_ids:
        return {}
    url = "https://displaycatalog.mp.microsoft.com/v7.0/products?" + urllib.parse.urlencode(
        {"bigIds": ",".join(big_ids), "market": MARKET, "languages": LANGUAGE},
        quote_via=urllib.parse.quote,
    )
    data = http_get_json(url)
    out: Dict[str, dict] = {}
    plist = data.get("Products") if isinstance(data, dict) else None
    if isinstance(plist, list):
        for p in plist:
            if isinstance(p, dict):
                bid = p.get("ProductId") or p.get("BigId") or p.get("bigId")
                if bid:
                    out[str(bid)] = p
    return out

def fetch_products_reliably(request_ids: List[str], batch_size: int, progress_cb=None) -> Tuple[Dict[str, dict], List[str]]:
    products: Dict[str, dict] = {}
    missing: List[str] = []

    to_fetch: List[str] = []
    for bid in request_ids:
        cached = load_product_from_cache(bid)
        if cached:
            products[bid] = cached
        else:
            to_fetch.append(bid)

    if not to_fetch:
        return products, []

    def process_chunk(chunk: List[str], current_batch: int):
        nonlocal products, missing
        if not chunk:
            return

        if len(chunk) > current_batch:
            for i in range(0, len(chunk), current_batch):
                process_chunk(chunk[i:i + current_batch], current_batch)
            return

        got = fetch_products_once(chunk)

        for bid, pobj in got.items():
            products[bid] = pobj
            save_product_to_cache(bid, pobj)
            if progress_cb:
                progress_cb(1)

        not_returned = [bid for bid in chunk if bid not in got]

        if not not_returned:
            return

        if current_batch > MIN_BATCH_SIZE and len(chunk) > 1:
            next_batch = max(MIN_BATCH_SIZE, current_batch // 2)
            process_chunk(not_returned, next_batch)
            return

        for bid in not_returned:
            if bid not in missing:
                missing.append(bid)
                if progress_cb:
                    progress_cb(1)  # count it as "processed"

    process_chunk(to_fetch, batch_size)
    return products, missing

# ---------------- Extractors / normalization ----------------
def pick_first(lst):
    if isinstance(lst, list) and lst:
        return lst[0]
    return None

def normalize_image_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return u

def iter_localized_images(obj: Any) -> List[dict]:
    images: List[dict] = []
    if isinstance(obj, dict):
        imgs = obj.get("Images")
        if isinstance(imgs, list):
            images.extend([x for x in imgs if isinstance(x, dict)])
    elif isinstance(obj, list):
        for lp in obj:
            if isinstance(lp, dict):
                imgs = lp.get("Images")
                if isinstance(imgs, list):
                    images.extend([x for x in imgs if isinstance(x, dict)])
    return images

def image_tag(img: dict) -> str:
    return str(img.get("ImagePurpose") or img.get("ImagePurposeTag") or img.get("Purpose") or "")

def image_url(img: dict) -> str:
    return str(img.get("Uri") or img.get("Url") or img.get("uri") or img.get("url") or "")

def pick_best_image_from_images(images: List[dict]) -> str:
    if not images:
        return ""
    preferred = ["BoxArt", "Poster", "SuperHeroArt", "BrandedKeyArt", "KeyArt", "Tile", "Screenshot", "Background"]
    for tag in preferred:
        for img in images:
            if image_tag(img).lower() == tag.lower():
                u = normalize_image_url(image_url(img))
                if u:
                    return u
    for img in images:
        u = normalize_image_url(image_url(img))
        if u:
            return u
    return ""

def pick_best_image_url(product: dict) -> str:
    u = pick_best_image_from_images(iter_localized_images(product.get("LocalizedProperties")))
    if u:
        return u
    dsa = product.get("DisplaySkuAvailabilities")
    if isinstance(dsa, list) and dsa:
        sku = (dsa[0] or {}).get("Sku") or {}
        u2 = pick_best_image_from_images(iter_localized_images(sku.get("LocalizedProperties")))
        if u2:
            return u2
    return ""

def normalize_year(y: str) -> str:
    y = (y or "").strip()
    if len(y) >= 4 and y[:4].isdigit():
        yy = int(y[:4])
        if 1970 <= yy <= 2035:
            return str(yy)
    return ""

def normalize_rating(r: str) -> str:
    r = (r or "").strip()
    if not r:
        return ""
    try:
        v = int(float(r))
        if 0 <= v <= 100:
            return str(v)
    except Exception:
        return ""
    return ""

def normalize_genres(g: str) -> str:
    g = (g or "").strip()
    if not g:
        return ""
    parts = [p.strip() for p in g.split(",") if p.strip()]
    # dedupe preserve order
    seen = set()
    out = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return ", ".join(out)

def extract_store_fields(product: dict) -> dict:
    localized = pick_first(product.get("LocalizedProperties")) or {}
    props = pick_first(product.get("Properties")) or {}

    title = localized.get("ProductTitle") or product.get("ProductTitle") or ""
    publisher = localized.get("PublisherName") or ""
    developer = localized.get("DeveloperName") or ""
    short_desc = localized.get("ShortDescription") or ""

    release_date = props.get("OriginalReleaseDate") or props.get("ReleaseDate") or props.get("ReleaseDateUtc") or ""
    store_year = normalize_year(release_date)

    image_url_final = normalize_image_url(pick_best_image_url(product))

    return {
        "Name": (title or "").strip(),
        "Publisher": (publisher or "").strip(),
        "Developer": (developer or "").strip(),
        "ReleaseDate": (release_date or "").strip(),
        "StoreYear": store_year,
        "ImageUrl": (image_url_final or "").strip(),
        "ShortDescription": (short_desc or "").strip(),
    }

def clean_title_for_search(name: str) -> str:
    n = (name or "").strip()
    # common store suffixes
    for s in ["(Game Preview)", "(PC)", "(Xbox Series X|S)", "(Xbox One)"]:
        n = n.replace(s, "")
    return n.strip()

# ---------------- Wikidata enrichment ----------------
def wikidata_search_qid(name: str) -> Optional[str]:
    cache_path = wd_name_cache_path(name)
    cached = read_json(cache_path)
    if isinstance(cached, dict) and cached.get("name") == name and cached.get("qid"):
        return str(cached["qid"])

    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "format": "json",
        "limit": "5",
        "uselang": "en",
        "type": "item",
    }
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
    data = http_get_json(url)

    qid = None
    if isinstance(data, dict) and isinstance(data.get("search"), list) and data["search"]:
        first = data["search"][0]
        if isinstance(first, dict) and first.get("id"):
            qid = str(first["id"])

    write_json_atomic(cache_path, {"name": name, "qid": qid, "cached_at": datetime.now().isoformat(), "_schema": CACHE_SCHEMA_VERSION})
    return qid

def sparql_query(q: str) -> Any:
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": q})
    return http_get_json(url, headers={"Accept": "application/sparql-results+json"})

def wikidata_enrich(qid: str) -> dict:
    cache_path = wd_qid_cache_path(qid)
    cached = read_json(cache_path)
    if isinstance(cached, dict) and cached.get("qid") == qid and isinstance(cached.get("data"), dict) and cached.get("_schema")==CACHE_SCHEMA_VERSION:
        return cached["data"]

    query = f"""
    SELECT ?item ?desc
           (GROUP_CONCAT(DISTINCT ?genreLabel; separator=", ") AS ?genres)
           (GROUP_CONCAT(DISTINCT ?platformLabel; separator=", ") AS ?platforms)
           (MIN(?pubDate) AS ?pubDateMin)
           ?score ?reviewerLabel ?wikipedia
    WHERE {{
      BIND(wd:{qid} AS ?item)
      OPTIONAL {{ ?item schema:description ?desc FILTER(LANG(?desc)="en") }}
      OPTIONAL {{ ?item wdt:P136 ?genre . ?genre rdfs:label ?genreLabel FILTER(LANG(?genreLabel)="en") }}
      OPTIONAL {{ ?item wdt:P400 ?platform . ?platform rdfs:label ?platformLabel FILTER(LANG(?platformLabel)="en") }}
      OPTIONAL {{ ?item wdt:P577 ?pubDate . }}

      OPTIONAL {{
        ?item p:P444 ?scoreStmt .
        ?scoreStmt ps:P444 ?score .
        OPTIONAL {{ ?scoreStmt pq:P447 ?reviewer . ?reviewer rdfs:label ?reviewerLabel FILTER(LANG(?reviewerLabel)="en") }}
      }}

      OPTIONAL {{
        ?wikipedia schema:about ?item ;
                   schema:isPartOf <https://en.wikipedia.org/> .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?desc ?score ?reviewerLabel ?wikipedia
    """
    data = sparql_query(query)

    genres = ""
    platforms = ""
    desc = ""
    wikipedia = ""
    year = ""
    score_best = ""
    reviewer_best = ""

    rows = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    candidates = []
    for r in rows:
        g = r.get("genres", {}).get("value", "")
        p = r.get("platforms", {}).get("value", "")
        d = r.get("desc", {}).get("value", "")
        w = r.get("wikipedia", {}).get("value", "")
        y = r.get("pubDateMin", {}).get("value", "")
        s = r.get("score", {}).get("value", "")
        rv = r.get("reviewerLabel", {}).get("value", "")
        candidates.append((g, p, d, w, y, s, rv))

    for (g, p, d, w, y, s, rv) in candidates:
        if not genres and g:
            genres = g
        if not platforms and p:
            platforms = p
        if not desc and d:
            desc = d
        if not wikipedia and w:
            wikipedia = w
        if not year and y:
            year = normalize_year(y)

    metacritic = [c for c in candidates if (c[6] or "").lower().find("metacritic") >= 0 and c[5]]
    if metacritic:
        score_best = metacritic[0][5]
        reviewer_best = metacritic[0][6] or "Metacritic"
    else:
        anyscore = [c for c in candidates if c[5]]
        if anyscore:
            score_best = anyscore[0][5]
            reviewer_best = anyscore[0][6] or "Review score"

    out = {
        "Genres_WD": normalize_genres(genres),
        "Platforms_WD": (platforms or "").strip(),
        "Description_WD": (desc or "").strip(),
        "Year_WD": normalize_year(year),
        "Rating": normalize_rating(score_best),
        "RatingSource": (reviewer_best or "").strip(),
        "WikipediaUrl": (wikipedia or "").strip(),
        "WikidataUrl": f"https://www.wikidata.org/wiki/{qid}",
    }
    write_json_atomic(cache_path, {"qid": qid, "data": out, "cached_at": datetime.now().isoformat(), "_schema": CACHE_SCHEMA_VERSION})
    return out

# ---------------- Hours via HowLongToBeat (optional) ----------------
def get_hours_hltb(name: str) -> str:
    cache_path = hltb_name_cache_path(name)
    cached = read_json(cache_path)
    if isinstance(cached, dict) and cached.get("name") == name and "hours" in cached and cached.get("_schema")==CACHE_SCHEMA_VERSION:
        return str(cached.get("hours") or "")

    if not ARGS.hltb:
        return ""

    try:
        from howlongtobeatpy import HowLongToBeat  # type: ignore
    except Exception:
        return ""

    hours = ""
    try:
        results = HowLongToBeat().search(name)
        if results:
            best = results[0]
            h = getattr(best, "main_story", None)
            if h:
                hours = str(h)
            else:
                h2 = getattr(best, "main_extra", None)
                if h2:
                    hours = str(h2)
    except Exception:
        hours = ""

    write_json_atomic(cache_path, {"name": name, "hours": hours, "cached_at": datetime.now().isoformat(), "_schema": CACHE_SCHEMA_VERSION})
    return hours

# ---------------- HTML (template + JS rendering) ----------------
HTML_TEMPLATE = """<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root { --fg:#111; --muted:#666; --card:#fff; --line:#e6e6e6; --bg:#fafafa; --accent:#1a73e8; }
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 16px; color: var(--fg); background: var(--bg); }
    h1 { font-size: 18px; margin: 0 0 6px 0; }
    .meta { color: var(--muted); margin: 0 0 14px 0; font-size: 13px; }
    .bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin: 10px 0 14px 0; }
    .btn { padding: 7px 12px; border: 1px solid #bbb; border-radius: 10px; background: #f7f7f7; cursor: pointer; font-size: 13px; }
    .btn.active { background:#e9e9e9; border-color:#999; }
    .filters { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; }
    .field { display:flex; flex-direction:column; gap:4px; }
    label { font-size: 12px; color: var(--muted); }
    select, input[type="number"] { padding: 6px 8px; border: 1px solid #bbb; border-radius: 10px; background:#fff; min-width: 140px; }
    .check { display:flex; gap:8px; align-items:center; padding: 6px 8px; border:1px solid #bbb; border-radius:10px; background:#fff; }
    .count { margin-left:auto; color: var(--muted); font-size: 13px; }

    /* Table */
    table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius: 14px; overflow:hidden; }
    th, td { padding: 10px 10px; border-bottom:1px solid var(--line); vertical-align:top; font-size: 13px; }
    th { background:#f3f3f3; font-weight:600; position:sticky; top:0; z-index:1; }
    tr:hover td { background:#fcfcfc; }
    .cover img { height:64px; border-radius:8px; }
    .links a { color: var(--accent); text-decoration:none; }
    .links a:hover { text-decoration:underline; }
    .toggle-btn { padding: 4px 10px; border: 1px solid #bbb; border-radius: 8px; background: #f7f7f7; cursor: pointer; font-size: 12px; }
    .desc { display:none; margin-top:8px; white-space: pre-wrap; color:#333; line-height:1.35; }
    .desc.show { display:block; }
    .pill { display:inline-block; padding: 2px 8px; border:1px solid #ddd; border-radius:999px; font-size:12px; color:#333; background:#fff; margin-right:6px; }
    .fav { cursor:pointer; border:1px solid #bbb; background:#fff; border-radius:10px; padding:4px 8px; font-size:12px; }
    .fav.on { background:#fff7cc; border-color:#d5b100; }

    /* Tiles */
    #tilesView { display:none; }
    .tiles { display:grid; grid-template-columns:repeat(auto-fill, minmax(210px, 1fr)); gap:14px; }
    .tile { border:1px solid var(--line); border-radius:16px; background:var(--card); overflow:hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
    .tile-media { position:relative; padding:10px 10px 0 10px; }
    .tile-media img { width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:14px; background:#f2f2f2; }
    .tile-badges { position:absolute; top:16px; left:16px; display:flex; gap:6px; flex-wrap:wrap; }
    .badge { background:rgba(0,0,0,0.65); color:#fff; padding:4px 8px; border-radius:999px; font-size:12px; }
    .tile-body { padding:10px 12px 12px 12px; }
    .tile-title { font-weight:600; font-size:14px; line-height:1.2; margin-bottom:6px; min-height:34px; }
    .tile-meta { display:flex; justify-content:space-between; gap:8px; font-size:12px; margin-bottom:8px; color: var(--muted); }
    .tile-links a { font-size:12px; color: var(--accent); text-decoration:none; }
    .tile-links a:hover { text-decoration:underline; }
  </style>
</head>
<body>
  <h1>__TITLE__</h1>
  <div class="meta">
    Перемикай вигляд: таблиця / плитки. Фільтри: рік, жанр, рейтинг. Обране ⭐ зберігається у localStorage.
  </div>

  <div class="bar">
    <button id="btnTable" class="btn active" type="button">Таблиця</button>
    <button id="btnTiles" class="btn" type="button">Плитки</button>

    <div class="filters">
      <div class="field">
        <label for="filterYear">Роки</label>
        <select id="filterYear" multiple size="1"></select>
      </div>
      <div class="field">
        <label for="filterGenre">Жанри</label>
        <select id="filterGenre" multiple size="1"></select>
      </div>
      <div class="field">
        <label for="filterRating">Рейтинг ≥</label>
        <input id="filterRating" type="number" min="0" max="100" step="1" placeholder="0">
      </div>
      <div class="check">
        <input id="filterFav" type="checkbox">
        <label for="filterFav" style="margin:0; color:var(--fg);">Тільки обрані ⭐</label>
      </div>
      <button id="btnResetFilters" class="btn" type="button">Скинути фільтри</button>
    </div>

    <div class="count" id="countBox"></div>
  </div>

  <div id="tableView">
    <div style="overflow:auto; border-radius:14px;">
      <table>
        <thead>
          <tr>
            <th>⭐</th>
            <th>Обкладинка</th>
            <th>Назва</th>
            <th>Жанр</th>
            <th>Рейтинг</th>
            <th>Рік</th>
            <th>Годин</th>
            <th>Видавець</th>
            <th>Розробник</th>
            <th>Платформи</th>
            <th>Опис</th>
            <th>Посилання</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <div id="tilesView">
    <div class="tiles" id="tiles"></div>
  </div>

<script>
const DATA = __DATA_JSON__;

function esc(s){ return (s||"").toString()
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;"); }

function getFavs(){
  try { return new Set(JSON.parse(localStorage.getItem("gp_favs") || "[]")); }
  catch { return new Set(); }
}
function setFavs(set){
  localStorage.setItem("gp_favs", JSON.stringify(Array.from(set)));
}
function toggleFav(id){
  const favs = getFavs();
  favs.has(id) ? favs.delete(id) : favs.add(id);
  setFavs(favs);
}

function uniqSorted(arr){
  const s = new Set(arr.filter(Boolean));
  return Array.from(s).sort((a,b)=>a.localeCompare(b, undefined, {numeric:true, sensitivity:"base"}));
}

function splitGenres(g){
  if(!g) return [];
  return g.split(",").map(x=>x.trim()).filter(Boolean);
}

function populateFilters(){
  const years = uniqSorted(DATA.map(x=>x.year).filter(Boolean));
  const genres = uniqSorted(DATA.flatMap(x=>splitGenres(x.genre)));

  const fy = document.getElementById("filterYear");
  fy.innerHTML = years.map(y=>`<option value="${esc(y)}">${esc(y)}</option>`).join("");

  const fg = document.getElementById("filterGenre");
  fg.innerHTML = genres.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join("");
}

function getSelected(selectId){
  const el = document.getElementById(selectId);
  return Array.from(el.selectedOptions).map(o=>o.value);
}

function applyFilters(){
  let list = DATA.slice();

  const years = getSelected("filterYear");
  if(years.length){
    list = list.filter(x => years.includes(x.year));
  }

  const genres = getSelected("filterGenre");
  if(genres.length){
    list = list.filter(x => splitGenres(x.genre).some(g => genres.includes(g)));
  }

  const minR = Number(document.getElementById("filterRating").value || 0);
  if(minR){
    list = list.filter(x => (Number(x.rating)||0) >= minR);
  }

  const onlyFav = document.getElementById("filterFav").checked;
  if(onlyFav){
    const favs = getFavs();
    list = list.filter(x => favs.has(x.id));
  }

  render(list);
}

function renderTable(list){
  const favs = getFavs();
  const tb = document.getElementById("tbody");
  tb.innerHTML = list.map((x, idx)=>{
    const favOn = favs.has(x.id);
    const img = x.image ? `<a href="${esc(x.image)}" target="_blank" rel="noopener" class="cover"><img src="${esc(x.image)}" loading="lazy" alt="cover"></a>` : "";
    const links = [
      x.wikipedia ? `<a href="${esc(x.wikipedia)}" target="_blank" rel="noopener">Wikipedia</a>` : "",
      x.wikidata ? `<a href="${esc(x.wikidata)}" target="_blank" rel="noopener">Wikidata</a>` : "",
      x.storeUrl ? `<a href="${esc(x.storeUrl)}" target="_blank" rel="noopener">Store</a>` : ""
    ].filter(Boolean).join(" | ");

    const descId = `d_${idx}`;
    const descBtn = x.description ? `<button class="toggle-btn" data-target="${descId}">Показати</button>` : "";
    const descDiv = x.description ? `<div id="${descId}" class="desc">${esc(x.description)}</div>` : "";

    return `<tr>
      <td><button class="fav ${favOn?"on":""}" data-fav="${esc(x.id)}">⭐</button></td>
      <td>${img}</td>
      <td><div><strong>${esc(x.name)}</strong></div></td>
      <td>${esc(x.genre)}</td>
      <td>${esc(x.rating)}${x.ratingSource ? " ("+esc(x.ratingSource)+")":""}</td>
      <td>${esc(x.year)}</td>
      <td>${esc(x.hours)}</td>
      <td>${esc(x.publisher)}</td>
      <td>${esc(x.developer)}</td>
      <td>${esc(x.platforms)}</td>
      <td>${descBtn}${descDiv}</td>
      <td class="links">${links}</td>
    </tr>`;
  }).join("");

  document.getElementById("countBox").textContent = `Показано: ${list.length} / ${DATA.length}`;
}

function renderTiles(list){
  const favs = getFavs();
  const grid = document.getElementById("tiles");
  grid.innerHTML = list.map((x)=>{
    const favOn = favs.has(x.id);
    const img = x.image ? `<a href="${esc(x.image)}" target="_blank" rel="noopener"><img src="${esc(x.image)}" loading="lazy" alt="cover"></a>` : `<div style="width:100%;aspect-ratio:3/4;border-radius:14px;background:#f2f2f2;"></div>`;
    const links = [
      x.wikipedia ? `<a href="${esc(x.wikipedia)}" target="_blank" rel="noopener">Wikipedia</a>` : "",
      x.wikidata ? `<a href="${esc(x.wikidata)}" target="_blank" rel="noopener">Wikidata</a>` : "",
      x.storeUrl ? `<a href="${esc(x.storeUrl)}" target="_blank" rel="noopener">Store</a>` : ""
    ].filter(Boolean).join(" | ");

    return `<div class="tile">
      <div class="tile-media">
        ${img}
        <div class="tile-badges">
          <span class="badge">${esc(x.year || "—")}</span>
          <span class="badge">${esc((splitGenres(x.genre)[0] || "Unknown"))}</span>
        </div>
      </div>
      <div class="tile-body">
        <div style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start;">
          <div class="tile-title">${esc(x.name)}</div>
          <button class="fav ${favOn?"on":""}" data-fav="${esc(x.id)}">⭐</button>
        </div>
        <div class="tile-meta">
          <span>${esc(x.hours ? x.hours+" h" : "")}</span>
          <span>${esc(x.rating)}</span>
        </div>
        <div class="tile-links">${links}</div>
      </div>
    </div>`;
  }).join("");

  document.getElementById("countBox").textContent = `Показано: ${list.length} / ${DATA.length}`;
}

function render(list){
  const view = localStorage.getItem("gp_view") || "table";
  if(view === "tiles"){
    renderTiles(list);
  }else{
    renderTable(list);
  }
}

function setView(view){
  localStorage.setItem("gp_view", view);
  document.getElementById("tableView").style.display = view==="table" ? "block" : "none";
  document.getElementById("tilesView").style.display = view==="tiles" ? "block" : "none";
  document.getElementById("btnTable").classList.toggle("active", view==="table");
  document.getElementById("btnTiles").classList.toggle("active", view==="tiles");
  applyFilters();
}

document.addEventListener("click", (e)=>{
  const tbtn = e.target.closest(".toggle-btn");
  if(tbtn){
    const id = tbtn.getAttribute("data-target");
    const el = document.getElementById(id);
    if(!el) return;
    const shown = el.classList.toggle("show");
    tbtn.textContent = shown ? "Сховати" : "Показати";
    return;
  }

  const fav = e.target.closest("[data-fav]");
  if(fav){
    const id = fav.getAttribute("data-fav");
    toggleFav(id);
    applyFilters(); // rerender current filtered view, and refresh fav buttons
    return;
  }
});

function debounce(fn, ms){
  let t = null;
  return function(...args){
    clearTimeout(t);
    t = setTimeout(()=>fn.apply(this,args), ms);
  }
}

const debounced = debounce(applyFilters, 120);

document.getElementById("filterYear").addEventListener("change", debounced);
document.getElementById("filterGenre").addEventListener("change", debounced);
document.getElementById("filterRating").addEventListener("input", debounced);
document.getElementById("filterFav").addEventListener("change", debounced);

document.getElementById("btnResetFilters").addEventListener("click", ()=>{
  document.getElementById("filterYear").selectedIndex = -1;
  document.getElementById("filterGenre").selectedIndex = -1;
  document.getElementById("filterRating").value = "";
  document.getElementById("filterFav").checked = false;
  applyFilters();
});

document.getElementById("btnTable").addEventListener("click", ()=>setView("table"));
document.getElementById("btnTiles").addEventListener("click", ()=>setView("tiles"));

populateFilters();
setView(localStorage.getItem("gp_view") || "table");
</script>

</body>
</html>
"""

def build_html(rows: List[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Game Pass Catalog ({MARKET}/{LANGUAGE}) — {now}"
    # Embed JSON safely
    data_json = json.dumps(rows, ensure_ascii=False)
    out = HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
    out = out.replace("__DATA_JSON__", data_json)
    return out

def save_outputs(rows: List[dict]):
    rows.sort(key=lambda x: (x.get("name") or "").lower())

    # CSV
    cols = ["id","name","genre","rating","ratingSource","year","hours","publisher","developer","platforms","description","wikipedia","wikidata","storeUrl","image"]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k,"") for k in cols})

    # HTML
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(build_html(rows))

    print(f"Saved: {OUT_HTML}")
    print(f"Saved: {OUT_CSV}")

# ---------------- Main ----------------
def main():
    ensure_dirs()

    mode = prompt_resume_or_reset()
    if mode == "reset":
        reset_cache()

    # SIGL
    sigl_cache = read_json(SIGL_FILE)
    if isinstance(sigl_cache, dict) and isinstance(sigl_cache.get("ids"), list) and sigl_cache.get("_schema")==CACHE_SCHEMA_VERSION:
        ids = [str(x) for x in sigl_cache["ids"]]
        print(f"Loaded SIGL ids from cache: {len(ids)}")
    else:
        print(f"Fetching SIGL ids... MARKET={MARKET} LANGUAGE={LANGUAGE}")
        ids = get_sigl_ids(SIGL_ALL)
        write_json_atomic(SIGL_FILE, {"_schema": CACHE_SCHEMA_VERSION, "market": MARKET, "language": LANGUAGE, "sigl": SIGL_ALL, "ids": ids})
        print(f"Fetched SIGL ids: {len(ids)}")

    # Determine which products need fetching (self-healing invalid cache already removed by load_product_from_cache)
    to_fetch = []
    cached_ok = 0
    for bid in ids:
        if load_product_from_cache(bid):
            cached_ok += 1
        else:
            to_fetch.append(bid)

    total_ids = len(ids)
    print(f"Total ids: {total_ids} | Cached products: {cached_ok} | To fetch: {len(to_fetch)}")

    # Progress helper
    processed_fetch = 0
    pbar = None
    if tqdm and len(to_fetch) > 0:
        pbar = tqdm(total=len(to_fetch), desc="Store fetch", unit="item")
    def progress_cb(n:int):
        nonlocal processed_fetch
        processed_fetch += n
        if pbar:
            pbar.update(n)

    # Store fetch in passes
    remaining = to_fetch[:]
    pass_no = 0
    missing_store: List[str] = []
    while remaining:
        pass_no += 1
        chunk = remaining[:PASS_SIZE]
        remaining = remaining[len(chunk):]
        if not tqdm:
            done = len(to_fetch) - len(remaining)
            pct = int((done / max(1,len(to_fetch))) * 100)
            print(f"[STORE] Pass {pass_no} | {done}/{len(to_fetch)} ({pct}%)")
        _, missing = fetch_products_reliably(chunk, INITIAL_BATCH_SIZE, progress_cb=progress_cb)
        if missing:
            warn(f"  ! Missing after autosplit in this pass: {len(missing)}")
            missing_store.extend(missing)
        heartbeat()
        time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

    if pbar:
        pbar.close()

    # Enrichment progress
    state = read_json(STATE_FILE)
    enrich_start = 0
    if isinstance(state, dict) and state.get("_schema")==CACHE_SCHEMA_VERSION and isinstance(state.get("enrich_index"), int):
        enrich_start = int(state["enrich_index"])
        if enrich_start < 0 or enrich_start > total_ids:
            enrich_start = 0

    if enrich_start > 0:
        print(f"Resuming enrichment from index: {enrich_start}/{total_ids}")

    rows: List[dict] = []
    truly_missing: List[str] = []

    ebar = None
    if tqdm:
        ebar = tqdm(total=total_ids, initial=enrich_start, desc="Enrichment", unit="game")

    for idx in range(enrich_start, total_ids):
        bid = ids[idx]
        # persist enrichment index for resume
        write_json_atomic(STATE_FILE, {"_schema": CACHE_SCHEMA_VERSION, "enrich_index": idx})

        prod = load_product_from_cache(bid)
        if not prod:
            truly_missing.append(bid)
            if ebar:
                ebar.update(1)
            else:
                if idx % 25 == 0:
                    print(f"[ENRICH] {idx+1}/{total_ids}")
            continue

        store = extract_store_fields(prod)
        name = store.get("Name","")
        if not name:
            # skip garbage
            if ebar:
                ebar.update(1)
            continue

        if not tqdm and idx % 10 == 0:
            print(f"[ENRICH] {idx+1}/{total_ids} | {name}")
        heartbeat()

        # Try Wikidata
        wd = {
            "Genres_WD": "",
            "Platforms_WD": "",
            "Description_WD": "",
            "Year_WD": "",
            "Rating": "",
            "RatingSource": "",
            "WikipediaUrl": "",
            "WikidataUrl": ""
        }
        qid = None
        if not ARGS.no_wikidata:
            try:
                qid = wikidata_search_qid(clean_title_for_search(name))
                if qid:
                    wd = wikidata_enrich(qid)
            except Exception as e:
                warn(f"  ! Wikidata failed: {name}: {e}")

        year = normalize_year(wd.get("Year_WD","")) or store.get("StoreYear","")
        genre = normalize_genres(wd.get("Genres_WD",""))
        rating = normalize_rating(wd.get("Rating",""))
        rating_source = (wd.get("RatingSource","") or "").strip()
        platforms = (wd.get("Platforms_WD","") or "").strip()
        desc = (wd.get("Description_WD","") or "").strip() or store.get("ShortDescription","")
        wiki = (wd.get("WikipediaUrl","") or "").strip()
        wdu = (wd.get("WikidataUrl","") or "").strip()

        # Hours optional
        hours = ""
        try:
            hours = get_hours_hltb(clean_title_for_search(name))
        except Exception:
            hours = ""

        # Store URL (best-effort)
        store_url = ""
        try:
            store_url = f"https://www.xbox.com/{LANGUAGE}/games/store/{urllib.parse.quote(name.lower().replace(' ', '-'))}"
        except Exception:
            store_url = ""

        rows.append({
            "id": bid,
            "name": name,
            "genre": genre,
            "rating": rating,
            "ratingSource": rating_source,
            "year": year,
            "hours": hours,
            "publisher": store.get("Publisher",""),
            "developer": store.get("Developer",""),
            "platforms": platforms,
            "description": desc,
            "wikipedia": wiki,
            "wikidata": wdu,
            "storeUrl": store_url,
            "image": store.get("ImageUrl",""),
        })

        if ebar:
            ebar.update(1)
        time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

    if ebar:
        ebar.close()

    # mark completion
    write_json_atomic(STATE_FILE, {"_schema": CACHE_SCHEMA_VERSION, "enrich_index": total_ids})

    print(f"\nRows built: {len(rows)} | Missing store products: {len(truly_missing)}")
    save_outputs(rows)
    print("Done.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is cached. Re-run to continue.")
        sys.exit(1)
