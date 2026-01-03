#!/usr/bin/env python3
# gamepass.py
#
# Game Pass catalog -> HTML + CSV
# - Microsoft Store product fetch with per-product cache + autosplit (reliable)
# - SIGL list from catalog.gamepass.com
# - Enrichment via Wikidata:
#     Genre (P136), Platforms (P400), Year (P577), Rating (P444 + optional P447), Description, Wikipedia/Wikidata links
# - Images: fix protocol-relative URLs //... -> https://...
# - Optional Hours via HowLongToBeat (requires: pip install howlongtobeatpy)
# - UI: Table (DataTables) + Tiles view switch; Tiles show Year + Genre badges
# - Table: Description hidden behind per-row toggle
# - Store fetch pass size: 100 (requested)
#
# No f-strings inside HTML template to avoid `{}` brace syntax errors.

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

# ---------------- Settings ----------------
MARKET = "US"
LANGUAGE = "en-us"
SIGL_ALL = "29a81209-df6f-41fd-a528-2ae6b91f719c"  # Game Pass - All games

INITIAL_BATCH_SIZE = 40
MIN_BATCH_SIZE = 1
PASS_SIZE = 100  # requested

REQUEST_TIMEOUT_SEC = 25
RETRIES = 5
BACKOFF_BASE_SEC = 1.6
JITTER_SEC = 0.35
SLEEP_BETWEEN_REQUESTS_SEC = 0.20

# Optional Hours (unofficial)
HLTB_ENABLED = False  # set True if installed howlongtobeatpy

CACHE_DIR = "cache"
STATE_FILE = os.path.join(CACHE_DIR, "state.json")
SIGL_FILE = os.path.join(CACHE_DIR, "sigl_ids.json")

PRODUCTS_DIR = os.path.join(CACHE_DIR, "products")
WIKIDATA_DIR = os.path.join(CACHE_DIR, "wikidata")      # name -> QID
WD_SPARQL_DIR = os.path.join(CACHE_DIR, "wd_sparql")    # QID -> enriched fields
HLTB_DIR = os.path.join(CACHE_DIR, "hltb")              # name -> hours

OUT_HTML = "gamepass_catalog.html"
OUT_CSV = "gamepass_catalog.csv"


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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: str, obj: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def prompt_resume_or_reset() -> str:
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
        if os.path.exists(path):
            os.remove(path)

    for d in (PRODUCTS_DIR, WIKIDATA_DIR, WD_SPARQL_DIR, HLTB_DIR):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".json"):
                    os.remove(os.path.join(d, fn))

    print("Cache reset done.")


def safe_filename(s: str) -> str:
    s = (s or "").strip().lower()
    out = "".join(c for c in s if c.isalnum() or c in ("-", "_"))[:180]
    return out if out else "x"


def product_cache_path(big_id: str) -> str:
    return os.path.join(PRODUCTS_DIR, f"{safe_filename(big_id)}.json")


def load_product_from_cache(big_id: str) -> Optional[dict]:
    obj = read_json(product_cache_path(big_id))
    if isinstance(obj, dict) and obj.get("bigId") == big_id and isinstance(obj.get("product"), dict):
        return obj["product"]
    return None


def save_product_to_cache(big_id: str, product: dict):
    write_json_atomic(product_cache_path(big_id), {
        "bigId": big_id,
        "cached_at": datetime.now().isoformat(),
        "product": product
    })


def wd_name_cache_path(name: str) -> str:
    return os.path.join(WIKIDATA_DIR, f"{safe_filename(name)}.json")


def wd_qid_cache_path(qid: str) -> str:
    return os.path.join(WD_SPARQL_DIR, f"{safe_filename(qid)}.json")


def hltb_name_cache_path(name: str) -> str:
    return os.path.join(HLTB_DIR, f"{safe_filename(name)}.json")


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
            print(f"  ! Request failed (attempt {attempt}/{RETRIES}): {e}")
            print(f"  ! Sleeping {sleep_for:.2f}s then retrying...")
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

    # dedupe, preserve order
    seen = set()
    out = []
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


def fetch_products_reliably(request_ids: List[str], batch_size: int) -> Tuple[Dict[str, dict], List[str]]:
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

        # split larger chunk
        if len(chunk) > current_batch:
            for i in range(0, len(chunk), current_batch):
                process_chunk(chunk[i:i + current_batch], current_batch)
            return

        got = fetch_products_once(chunk)

        for bid, pobj in got.items():
            products[bid] = pobj
            save_product_to_cache(bid, pobj)

        not_returned = [bid for bid in chunk if bid not in got]
        if not not_returned:
            return

        # if still missing: split further
        if current_batch > MIN_BATCH_SIZE and len(chunk) > 1:
            next_batch = max(MIN_BATCH_SIZE, current_batch // 2)
            process_chunk(not_returned, next_batch)
            return

        # final missing
        for bid in not_returned:
            if bid not in missing:
                missing.append(bid)

    process_chunk(to_fetch, batch_size)
    return products, missing


# ---------------- Extractors ----------------
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


def extract_store_fields(product: dict) -> dict:
    localized = pick_first(product.get("LocalizedProperties")) or {}
    props = pick_first(product.get("Properties")) or {}

    title = localized.get("ProductTitle") or product.get("ProductTitle") or ""
    publisher = localized.get("PublisherName") or ""
    developer = localized.get("DeveloperName") or ""
    short_desc = localized.get("ShortDescription") or ""

    release_date = props.get("OriginalReleaseDate") or props.get("ReleaseDate") or props.get("ReleaseDateUtc") or ""
    store_year = release_date[:4] if isinstance(release_date, str) and len(release_date) >= 4 else ""

    image_url_final = normalize_image_url(pick_best_image_url(product))

    return {
        "Name": title,
        "Publisher": publisher,
        "Developer": developer,
        "ReleaseDate": release_date,
        "StoreYear": store_year,
        "ImageUrl": image_url_final,
        "ShortDescription": short_desc,
    }


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

    write_json_atomic(cache_path, {"name": name, "qid": qid, "cached_at": datetime.now().isoformat()})
    return qid


def sparql_query(q: str) -> Any:
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format": "json", "query": q})
    return http_get_json(url, headers={"Accept": "application/sparql-results+json"})


def wikidata_enrich(qid: str) -> dict:
    cache_path = wd_qid_cache_path(qid)
    cached = read_json(cache_path)
    if isinstance(cached, dict) and cached.get("qid") == qid and isinstance(cached.get("data"), dict):
        return cached["data"]

    # P136 genre, P400 platform, P577 publication date, P444 review score, P447 reviewed by
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
        if not year and y and len(y) >= 4:
            year = y[:4]

    # Prefer Metacritic if present
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
        "Genres_WD": (genres or "").strip(),
        "Platforms_WD": (platforms or "").strip(),
        "Description_WD": (desc or "").strip(),
        "Year_WD": (year or "").strip(),
        "Rating": (score_best or "").strip(),
        "RatingSource": (reviewer_best or "").strip(),
        "WikipediaUrl": (wikipedia or "").strip(),
        "WikidataUrl": f"https://www.wikidata.org/wiki/{qid}",
    }
    write_json_atomic(cache_path, {"qid": qid, "data": out, "cached_at": datetime.now().isoformat()})
    return out


# ---------------- Hours via HowLongToBeat (optional) ----------------
def get_hours_hltb(name: str) -> str:
    cache_path = hltb_name_cache_path(name)
    cached = read_json(cache_path)
    if isinstance(cached, dict) and cached.get("name") == name and "hours" in cached:
        return str(cached.get("hours") or "")

    if not HLTB_ENABLED:
        return ""

    try:
        from howlongtobeatpy import HowLongToBeat
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

    write_json_atomic(cache_path, {"name": name, "hours": hours, "cached_at": datetime.now().isoformat()})
    return hours


# ---------------- Output (NO f-string braces issues) ----------------
HTML_TEMPLATE = """<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables.net-dt@2.1.8/css/dataTables.dataTables.min.css">
  <script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/datatables.net@2.1.8/js/dataTables.min.js"></script>

  <style>
    body {
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      margin: 16px;
    }
    h1 { font-size: 18px; margin: 0 0 8px 0; }
    .meta { color: #555; margin: 0 0 16px 0; font-size: 13px; }

    .viewbar {
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 12px 0 14px 0;
    }
    .viewbtn {
      padding: 6px 12px;
      border: 1px solid #bbb;
      border-radius: 10px;
      background: #f7f7f7;
      cursor: pointer;
      font-size: 13px;
    }
    .viewbtn.active {
      background: #e9e9e9;
      border-color: #999;
    }

    table.dataTable td { vertical-align: top; }
    td { max-width: 520px; }
    .toggle-btn {
      padding: 4px 10px;
      border: 1px solid #bbb;
      border-radius: 8px;
      background: #f7f7f7;
      cursor: pointer;
      font-size: 12px;
    }
    .desc-hidden {
      display: none;
      margin-top: 8px;
      white-space: pre-wrap;
      color: #333;
      font-size: 13px;
      line-height: 1.35;
    }
    .desc-shown { display: block; }

    #tilesView { display: none; }
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 14px;
    }
    .tile {
      border: 1px solid #e3e3e3;
      border-radius: 16px;
      overflow: hidden;
      background: #fff;
      box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    }
    .tile-media {
      position: relative;
      padding: 10px 10px 0 10px;
    }
    .tile-badges {
      position: absolute;
      top: 16px;
      left: 16px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .badge {
      background: rgba(0,0,0,0.65);
      color: #fff;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
    }
    .tile-body { padding: 10px 12px 12px 12px; }
    .tile-title {
      font-weight: 600;
      font-size: 14px;
      line-height: 1.2;
      margin-bottom: 6px;
      min-height: 34px;
    }
    .tile-meta {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 12px;
      margin-bottom: 8px;
    }
    .muted { color: #666; }
    .tile-links a {
      font-size: 12px;
      color: #1a73e8;
      text-decoration: none;
    }
    .tile-links a:hover { text-decoration: underline; }
    .tile-noimg {
      width:100%;
      aspect-ratio:3/4;
      border-radius:14px;
      background:#f2f2f2;
      display:flex;
      align-items:center;
      justify-content:center;
      color:#777;
      font-size:12px;
    }
  </style>
</head>
<body>
  <h1>__TITLE__</h1>
  <p class="meta">
    Вигляд: таблиця або плитки. Рік береться з Wikidata (publication date), якщо є — інакше з Microsoft Store.
    Години — опційно через HowLongToBeat (якщо увімкнено).
  </p>

  <div class="viewbar">
    <button id="btnTable" class="viewbtn active" type="button">Таблиця</button>
    <button id="btnTiles" class="viewbtn" type="button">Плитки</button>
  </div>

  <div id="tableView">
    <table id="gp" class="display" style="width:100%">
      <thead>
        <tr>
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
      <tbody>
        __TABLE_ROWS__
      </tbody>
    </table>
  </div>

  <div id="tilesView">
    <div class="tiles">
      __TILES__
    </div>
  </div>

  __MISSING_BLOCK__

  <script>
    $(function() {
      new DataTable('#gp', {
        pageLength: 50,
        order: [[1, 'asc']],
        deferRender: true
      });

      // Description toggles (table only)
      document.addEventListener('click', function(e) {
        const btn = e.target.closest('.toggle-btn');
        if (!btn) return;

        const id = btn.getAttribute('data-target');
        const el = document.getElementById(id);
        if (!el) return;

        const isShown = el.classList.contains('desc-shown');
        if (isShown) {
          el.classList.remove('desc-shown');
          btn.textContent = 'Показати';
        } else {
          el.classList.add('desc-shown');
          btn.textContent = 'Сховати';
        }
      });

      // View switch
      const btnTable = document.getElementById('btnTable');
      const btnTiles = document.getElementById('btnTiles');
      const tableView = document.getElementById('tableView');
      const tilesView = document.getElementById('tilesView');

      function setView(view) {
        const isTable = view === 'table';
        tableView.style.display = isTable ? 'block' : 'none';
        tilesView.style.display = isTable ? 'none' : 'block';
        btnTable.classList.toggle('active', isTable);
        btnTiles.classList.toggle('active', !isTable);
        localStorage.setItem('gp_view', view);
      }

      btnTable.addEventListener('click', () => setView('table'));
      btnTiles.addEventListener('click', () => setView('tiles'));

      const saved = localStorage.getItem('gp_view') || 'table';
      setView(saved);
    });
  </script>
</body>
</html>
"""


def build_html(rows: List[dict], missing_ids: List[str]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Game Pass Catalog ({MARKET}/{LANGUAGE}) — {now}"

    tr_list: List[str] = []
    tiles_list: List[str] = []

    for idx, r in enumerate(rows):
        img_url = (r.get("ImageUrl") or "").strip()
        img_cell = ""
        tile_img = ""
        if img_url:
            img_u = html.escape(img_url)
            img_cell = (
                f'<a href="{img_u}" target="_blank" rel="noopener">'
                f'<img src="{img_u}" alt="cover" loading="lazy" style="height:64px;border-radius:6px;">'
                f"</a>"
            )
            tile_img = (
                f'<a href="{img_u}" target="_blank" rel="noopener">'
                f'<img src="{img_u}" alt="cover" loading="lazy" '
                f'style="width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:14px;">'
                f"</a>"
            )
        else:
            tile_img = '<div class="tile-noimg">No image</div>'

        rating = (r.get("Rating") or "").strip()
        rsrc = (r.get("RatingSource") or "").strip()
        rating_cell = html.escape(rating)
        if rating and rsrc:
            rating_cell = html.escape(f"{rating} ({rsrc})")

        year = (r.get("Year") or "").strip()
        genre = (r.get("Genre") or "").strip()
        hours = (r.get("Hours") or "").strip()

        wiki = (r.get("WikipediaUrl") or "").strip()
        wd = (r.get("WikidataUrl") or "").strip()
        links = []
        if wiki:
            links.append(f'<a href="{html.escape(wiki)}" target="_blank" rel="noopener">Wikipedia</a>')
        if wd:
            links.append(f'<a href="{html.escape(wd)}" target="_blank" rel="noopener">Wikidata</a>')
        links_cell = " | ".join(links)

        desc_id = f"desc_{idx}"
        desc = (r.get("Description") or "").strip()
        desc_safe = html.escape(desc)
        desc_cell = (
            f'<button class="toggle-btn" data-target="{desc_id}">Показати</button>'
            f'<div id="{desc_id}" class="desc-hidden">{desc_safe}</div>'
        )

        tr_list.append(
            "<tr>"
            f"<td>{img_cell}</td>"
            f"<td>{html.escape(r.get('Name',''))}</td>"
            f"<td>{html.escape(genre)}</td>"
            f"<td>{rating_cell}</td>"
            f"<td>{html.escape(year)}</td>"
            f"<td>{html.escape(hours)}</td>"
            f"<td>{html.escape(r.get('Publisher',''))}</td>"
            f"<td>{html.escape(r.get('Developer',''))}</td>"
            f"<td>{html.escape(r.get('Platforms',''))}</td>"
            f"<td>{desc_cell}</td>"
            f"<td>{links_cell}</td>"
            "</tr>"
        )

        tiles_list.append(
            '<div class="tile">'
            '  <div class="tile-media">'
            f'    {tile_img}'
            '    <div class="tile-badges">'
            f'      <span class="badge">{html.escape(year) if year else "—"}</span>'
            f'      <span class="badge">{html.escape(genre) if genre else "Unknown"}</span>'
            '    </div>'
            '  </div>'
            '  <div class="tile-body">'
            f'    <div class="tile-title">{html.escape(r.get("Name",""))}</div>'
            '    <div class="tile-meta">'
            f'      <span class="muted">{html.escape((hours + " h") if hours else "")}</span>'
            f'      <span class="muted">{html.escape(rating if rating else "")}</span>'
            '    </div>'
            f'    <div class="tile-links">{links_cell}</div>'
            '  </div>'
            '</div>'
        )

    missing_block = ""
    if missing_ids:
        missing_block = (
            "<details style='margin-top:12px'>"
            f"<summary>Missing products from Store API: {len(missing_ids)} (click to expand)</summary>"
            "<pre style='white-space:pre-wrap'>"
            + html.escape("\n".join(missing_ids))
            + "</pre></details>"
        )

    out = HTML_TEMPLATE
    out = out.replace("__TITLE__", html.escape(title))
    out = out.replace("__TABLE_ROWS__", "".join(tr_list))
    out = out.replace("__TILES__", "".join(tiles_list))
    out = out.replace("__MISSING_BLOCK__", missing_block)
    return out


def save_outputs(rows: List[dict], missing_ids: List[str]):
    rows.sort(key=lambda x: (x.get("Name") or "").lower())

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(build_html(rows, missing_ids))

    cols = [
        "Name", "Genre", "Rating", "RatingSource",
        "Year", "Hours",
        "Publisher", "Developer", "Platforms",
        "Description", "WikipediaUrl", "WikidataUrl", "ImageUrl"
    ]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})

    print(f"Saved: {OUT_HTML}")
    print(f"Saved: {OUT_CSV}")


# ---------------- Main ----------------
def main():
    ensure_dirs()

    mode = prompt_resume_or_reset()
    if mode == "reset":
        reset_cache()

    # SIGL ids
    sigl_cache = read_json(SIGL_FILE)
    if isinstance(sigl_cache, dict) and isinstance(sigl_cache.get("ids"), list):
        ids = [str(x) for x in sigl_cache["ids"]]
        print(f"Loaded SIGL ids from cache: {len(ids)}")
    else:
        print(f"Fetching SIGL ids... MARKET={MARKET} LANGUAGE={LANGUAGE}")
        ids = get_sigl_ids(SIGL_ALL)
        write_json_atomic(SIGL_FILE, {"market": MARKET, "language": LANGUAGE, "sigl": SIGL_ALL, "ids": ids})
        print(f"Fetched SIGL ids: {len(ids)}")

    # Fetch missing Store products into cache
    cached_count = 0
    to_fetch = []
    for bid in ids:
        if load_product_from_cache(bid):
            cached_count += 1
        else:
            to_fetch.append(bid)
    print(f"Total ids: {len(ids)} | Cached products: {cached_count} | To fetch: {len(to_fetch)}")

    remaining = to_fetch[:]
    pass_no = 0
    missing_store: List[str] = []

    while remaining:
        pass_no += 1
        chunk = remaining[:PASS_SIZE]
        remaining = remaining[len(chunk):]
        print(f"\n=== Store Pass {pass_no}: fetching {len(chunk)} ids (autosplit) ===")
        _, missing = fetch_products_reliably(chunk, INITIAL_BATCH_SIZE)
        if missing:
            print(f"  ! Still missing from Store after autosplit: {len(missing)}")
            missing_store.extend(missing)
        time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

    # Build rows (from cache + enrichment)
    rows: List[dict] = []
    truly_missing: List[str] = []

    for bid in ids:
        prod = load_product_from_cache(bid)
        if not prod:
            truly_missing.append(bid)
            continue

        store = extract_store_fields(prod)

        name = (store.get("Name") or "").strip()
        name_for_search = (
            name.replace("(Game Preview)", "")
                .replace("(PC)", "")
                .replace("(Xbox Series X|S)", "")
                .replace("(Xbox One)", "")
                .strip()
        )

        qid = wikidata_search_qid(name_for_search) if name_for_search else None
        wd = {
            "Genres_WD": "", "Platforms_WD": "", "Description_WD": "",
            "Year_WD": "", "Rating": "", "RatingSource": "",
            "WikipediaUrl": "", "WikidataUrl": ""
        }

        if qid:
            try:
                wd = wikidata_enrich(qid)
            except Exception as e:
                print(f"  ! Wikidata enrich failed for {name_for_search} ({qid}): {e}")

        year = (wd.get("Year_WD") or "").strip() or (store.get("StoreYear") or "").strip()
        genre = (wd.get("Genres_WD") or "").strip() or "Unknown"
        platforms = (wd.get("Platforms_WD") or "").strip()
        desc = (wd.get("Description_WD") or "").strip() or (store.get("ShortDescription") or "").strip()

        hours = ""
        if name_for_search:
            hours = get_hours_hltb(name_for_search)

        rows.append({
            "Name": store.get("Name", ""),
            "Genre": genre,
            "Rating": (wd.get("Rating") or "").strip(),
            "RatingSource": (wd.get("RatingSource") or "").strip(),
            "Year": year,
            "Hours": hours,
            "Publisher": store.get("Publisher", ""),
            "Developer": store.get("Developer", ""),
            "Platforms": platforms,
            "Description": desc,
            "WikipediaUrl": wd.get("WikipediaUrl", ""),
            "WikidataUrl": wd.get("WikidataUrl", ""),
            "ImageUrl": store.get("ImageUrl", ""),
        })

    write_json_atomic(STATE_FILE, {
        "market": MARKET,
        "language": LANGUAGE,
        "sigl": SIGL_ALL,
        "total_ids": len(ids),
        "missing_store": len(truly_missing),
        "hltb_enabled": HLTB_ENABLED,
        "updated_at": datetime.now().isoformat()
    })

    print(f"\nRows built: {len(rows)} | Missing store products: {len(truly_missing)}")
    save_outputs(rows, truly_missing)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is cached. Re-run to continue.")
        sys.exit(1)
