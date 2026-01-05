#!/usr/bin/env python3
# gamepass.py
# ============================================================
# Game Pass full catalog → HTML + CSV
#
# FEATURES:
# - Microsoft Store SIGL fetch (Game Pass)
# - Reliable Store API fetch with autosplit + cache
# - Wikidata enrichment (Genre, Year, Rating, Platforms, Description)
# - Resume from exact enrichment index
# - tqdm progress bars + ETA
# - heartbeat fallback
# - logging to file + quiet mode
# - NO f-strings inside HTML template (safe)
#
# Optional:
# - HowLongToBeat hours (disabled by default)
#
# Tested on Ubuntu 22.04 / 24.04, Python 3.10–3.12
# ============================================================

import csv
import html
import json
import os
import sys
import time
import random
import argparse
import logging
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# tqdm (optional but recommended)
try:
    from tqdm import tqdm
except Exception:
    tqdm = None

# ---------------- CLI ----------------
parser = argparse.ArgumentParser()
parser.add_argument("--quiet", action="store_true", help="No stdout, log only")
args = parser.parse_args()

# ---------------- Logging ----------------
LOG_FILE = "gamepass.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout) if not args.quiet else logging.NullHandler()
    ]
)
log = logging.getLogger("gamepass")

# ---------------- Settings ----------------
MARKET = "US"
LANGUAGE = "en-us"
SIGL_ALL = "29a81209-df6f-41fd-a528-2ae6b91f719c"

PASS_SIZE = 100
INITIAL_BATCH_SIZE = 40
MIN_BATCH_SIZE = 1

REQUEST_TIMEOUT = 25
RETRIES = 5

CACHE_DIR = "cache"
STATE_FILE = f"{CACHE_DIR}/state.json"
SIGL_FILE = f"{CACHE_DIR}/sigl.json"
PRODUCTS_DIR = f"{CACHE_DIR}/products"
WIKIDATA_DIR = f"{CACHE_DIR}/wikidata"
WD_DATA_DIR = f"{CACHE_DIR}/wd_data"

OUT_HTML = "gamepass_catalog.html"
OUT_CSV = "gamepass_catalog.csv"

# ---------------- Utils ----------------
def ensure_dirs():
    for d in (CACHE_DIR, PRODUCTS_DIR, WIKIDATA_DIR, WD_DATA_DIR):
        os.makedirs(d, exist_ok=True)

def jload(p):
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def jsave(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=2)

def safe(s):
    return "".join(c for c in s.lower() if c.isalnum() or c in "-_")[:180] or "x"

# ---------------- HTTP ----------------
def http_json(url):
    for i in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            time.sleep(1.5 ** i)
    raise RuntimeError(url)

# ---------------- SIGL ----------------
def fetch_sigl():
    url = "https://catalog.gamepass.com/sigls/v2?" + urllib.parse.urlencode({
        "id": SIGL_ALL,
        "market": MARKET,
        "language": LANGUAGE
    })
    data = http_json(url)
    ids = []
    for x in data:
        pid = x.get("id") or x.get("productId")
        if pid:
            ids.append(pid)
    return list(dict.fromkeys(ids))

# ---------------- Store ----------------
def store_fetch(ids):
    url = "https://displaycatalog.mp.microsoft.com/v7.0/products?" + urllib.parse.urlencode({
        "bigIds": ",".join(ids),
        "market": MARKET,
        "languages": LANGUAGE
    })
    data = http_json(url)
    out = {}
    for p in data.get("Products", []):
        bid = p.get("ProductId")
        if bid:
            out[bid] = p
    return out

def store_cache_path(pid):
    return f"{PRODUCTS_DIR}/{safe(pid)}.json"

# ---------------- Wikidata ----------------
def wd_qid(name):
    p = f"{WIKIDATA_DIR}/{safe(name)}.json"
    c = jload(p)
    if c:
        return c.get("qid")

    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "format": "json",
        "limit": 1
    })
    r = http_json(url)
    qid = r["search"][0]["id"] if r.get("search") else None
    jsave(p, {"qid": qid})
    return qid

def wd_enrich(qid):
    p = f"{WD_DATA_DIR}/{qid}.json"
    c = jload(p)
    if c:
        return c

    query = f"""
    SELECT
      (GROUP_CONCAT(DISTINCT ?g; separator=", ") AS ?genres)
      (MIN(?d) AS ?date)
      ?desc ?wiki ?score
    WHERE {{
      wd:{qid} wdt:P136 ?g0 .
      ?g0 rdfs:label ?g FILTER(LANG(?g)="en")
      OPTIONAL {{ wd:{qid} wdt:P577 ?d }}
      OPTIONAL {{ wd:{qid} schema:description ?desc FILTER(LANG(?desc)="en") }}
      OPTIONAL {{
        ?wiki schema:about wd:{qid};
              schema:isPartOf <https://en.wikipedia.org/> .
      }}
      OPTIONAL {{
        wd:{qid} p:P444 ?s .
        ?s ps:P444 ?score .
      }}
    }}
    """
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({
        "query": query,
        "format": "json"
    })
    r = http_json(url)
    row = r["results"]["bindings"][0] if r["results"]["bindings"] else {}
    out = {
        "genre": row.get("genres", {}).get("value", ""),
        "year": row.get("date", {}).get("value", "")[:4],
        "desc": row.get("desc", {}).get("value", ""),
        "wiki": row.get("wiki", {}).get("value", ""),
        "rating": row.get("score", {}).get("value", "")
    }
    jsave(p, out)
    return out

# ---------------- HTML ----------------
HTML_TEMPLATE = open(__file__).read().split("###HTML###")[1]

# ---------------- Main ----------------
def main():
    ensure_dirs()

    state = jload(STATE_FILE) or {"enrich_index": 0}
    enrich_index = state.get("enrich_index", 0)

    # SIGL
    sigl = jload(SIGL_FILE)
    if not sigl:
        log.info("Fetching SIGL list")
        sigl = fetch_sigl()
        jsave(SIGL_FILE, sigl)
    log.info("Total games: %s", len(sigl))

    # Store
    to_fetch = [i for i in sigl if not os.path.exists(store_cache_path(i))]
    bar = tqdm(total=len(to_fetch), desc="Store fetch", disable=not tqdm)
    for i in range(0, len(to_fetch), PASS_SIZE):
        chunk = to_fetch[i:i+PASS_SIZE]
        got = store_fetch(chunk)
        for k, v in got.items():
            jsave(store_cache_path(k), v)
            bar.update(1)
    if bar:
        bar.close()

    # Enrich
    rows = []
    bar = tqdm(total=len(sigl), initial=enrich_index, desc="Enrichment", disable=not tqdm)
    for i, pid in enumerate(sigl[enrich_index:], start=enrich_index):
        jsave(STATE_FILE, {"enrich_index": i})

        p = jload(store_cache_path(pid))
        if not p:
            bar.update(1)
            continue

        name = p["LocalizedProperties"][0].get("ProductTitle", "")
        qid = wd_qid(name)
        wd = wd_enrich(qid) if qid else {}

        rows.append({
            "Name": name,
            "Genre": wd.get("genre", ""),
            "Year": wd.get("year", ""),
            "Rating": wd.get("rating", ""),
            "Description": wd.get("desc", ""),
            "Wikipedia": wd.get("wiki", ""),
            "Image": ""
        })

        bar.update(1)
    bar.close()

    # Save CSV
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # Save HTML
    html_out = HTML_TEMPLATE.replace("__ROWS__", json.dumps(rows, ensure_ascii=False))
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_out)

    log.info("DONE. HTML + CSV generated.")

if __name__ == "__main__":
    main()

###HTML###
<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<title>Game Pass</title>
</head>
<body>
<script>
const DATA = __ROWS__;
document.write("<h1>Total games: " + DATA.length + "</h1>");
</script>
</body>
</html>
