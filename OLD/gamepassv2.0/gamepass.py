#!/usr/bin/env python3
# gamepass.py — Game Pass каталог (v4.3 Modular)
# Вимагає поруч файл: gp_logic.py

import argparse
import csv
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# Імпорт нашої нової бібліотеки
from core import gp_logic

# Спроба імпорту необов'язкових бібліотек
try: from tqdm import tqdm
except ImportError: tqdm = None

HLTB_AVAILABLE = False
try:
    from howlongtobeatpy import HowLongToBeat
    HLTB_AVAILABLE = True
except ImportError: pass

# ---------- CLI & CONFIG ----------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true", help="Вимкнути вивід")
    p.add_argument("--no-color", action="store_true", help="Вимкнути кольори")
    p.add_argument("--reset-cache", action="store_true", help="Скинути кеш")
    p.add_argument("--render-only", action="store_true", help="Тільки генерація (офлайн)")
    p.add_argument("--no-wikidata", action="store_true", help="Без Wikidata")
    p.add_argument("--hltb", action="store_true", help="З HowLongToBeat")
    p.add_argument("--market", default="US")
    p.add_argument("--pass-size", type=int, default=20)
    return p.parse_args()

ARGS = parse_args()

# Глобальні налаштування
MARKET = ARGS.market
DATA_LANG = "uk-ua"
DISPLAY_LANGS = "uk-ua,en-us"
SIGL_ALL = "29a81209-df6f-41fd-a528-2ae6b91f719c"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".gamepass")

DIRS = {
    "products": os.path.join(CACHE_DIR, "products"),
    "wikidata": os.path.join(CACHE_DIR, "wikidata"),
    "wd_sparql": os.path.join(CACHE_DIR, "wd_sparql"),
    "hltb": os.path.join(CACHE_DIR, "hltb")
}
FILES = {
    "sigl": os.path.join(CACHE_DIR, "sigl_ids.json"),
    "template": "core/template.html",
    "out_html": "gamepass_catalog.html",
    "out_csv": "gamepass_catalog.csv"
}
SCHEMA_VER = 3

# ---------- VISUALS ----------
IS_TTY = sys.stdout.isatty()
USE_COLOR = (not ARGS.no_color) and IS_TTY

def _c(txt, kind):
    if not USE_COLOR: return txt
    colors = {
        "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
        "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
        "blue": "\033[34m", "cyan": "\033[36m"
    }
    return f"{colors.get(kind, '')}{txt}{colors['reset']}"

def _tag(label, color="blue"):
    return _c(f"[{label}]", color)

def log(msg, tag_txt=None, tag_color="blue"):
    if ARGS.quiet: return
    prefix = f"{_tag(tag_txt, tag_color)} " if tag_txt else ""
    print(f"{prefix}{msg}")

def log_warn(msg):
    log(msg, "УВАГА", "yellow")

def log_err(msg):
    print(f"{_tag('ПОМИЛКА', 'red')} {msg}")

# ---------- NETWORK & FETCHING ----------
# Мережеві функції лишаємо тут, бо це "дії", а не "логіка даних"

def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    for d in DIRS.values(): os.makedirs(d, exist_ok=True)

def http_get_json(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if headers: h.update(headers)
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read())
        except Exception:
            time.sleep(1 + random.random())
    return None

def get_sigl_ids():
    cached = gp_logic.rw_json(FILES["sigl"])
    if cached and cached.get("ids") and cached.get("market") == MARKET:
        log(f"Завантажено з кешу: {_c(str(len(cached['ids'])), 'bold')} ігор", "SIGL", "green")
        return [str(x) for x in cached["ids"]]
    
    log("Отримання списку ігор з серверів Xbox...", "SIGL", "cyan")
    url = "https://catalog.gamepass.com/sigls/v2?" + urllib.parse.urlencode({"id": SIGL_ALL, "language": DATA_LANG, "market": MARKET})
    data = http_get_json(url)
    ids = []
    if isinstance(data, list):
        ids = list(set(str(item.get("id") or item.get("productId") or "") for item in data if item.get("id") or item.get("productId")))
    
    ids = [x for x in ids if x]
    if ids:
        gp_logic.rw_json(FILES["sigl"], {"_schema": SCHEMA_VER, "market": MARKET, "ids": ids})
        log(f"Отримано нових ID: {_c(str(len(ids)), 'bold')}", "SIGL", "green")
    else:
        log_err("Не вдалося отримати список ID.")
    return ids

def fetch_store_batch(ids):
    if not ids: return
    # Правильне кодування URL (без %2C для ком)
    base_params = urllib.parse.urlencode({"market": MARKET, "languages": DISPLAY_LANGS})
    ids_str = ",".join(ids)
    url = f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={ids_str}&{base_params}"
    
    data = http_get_json(url)
    if not data or "Products" not in data: return
    
    for p in data["Products"]:
        bid = p.get("ProductId") or p.get("BigId")
        if bid:
            gp_logic.rw_json(os.path.join(DIRS["products"], f"{gp_logic.safe_name(bid)}.json"), 
                   {"_schema": SCHEMA_VER, "display_langs": DISPLAY_LANGS, "product": p})

def enrich_one(name):
    # Wikidata
    if not ARGS.no_wikidata:
        path_n = os.path.join(DIRS["wikidata"], f"{gp_logic.safe_name(name)}.json")
        if not os.path.exists(path_n):
            u = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "wbsearchentities", "search": name, "language": "en", "format": "json", "limit": 1, "type": "item"})
            d = http_get_json(u)
            qid = d["search"][0]["id"] if d and d.get("search") else None
            gp_logic.rw_json(path_n, {"_schema": SCHEMA_VER, "name": name, "qid": qid})
            
            if qid:
                path_q = os.path.join(DIRS["wd_sparql"], f"{gp_logic.safe_name(qid)}.json")
                if not os.path.exists(path_q):
                    q = f"""SELECT ?item ?desc_uk (GROUP_CONCAT(DISTINCT ?genreLabel_uk; separator=", ") AS ?genres_uk) (MIN(?pubDate) AS ?pubDateMin) ?score ?reviewerLabel ?wikipedia WHERE {{
                      BIND(wd:{qid} AS ?item)
                      OPTIONAL {{ ?item schema:description ?desc_uk FILTER(LANG(?desc_uk)="uk") }}
                      OPTIONAL {{ ?item wdt:P136 ?genre . OPTIONAL {{ ?genre rdfs:label ?genreLabel_uk FILTER(LANG(?genreLabel_uk)="uk") }} }}
                      OPTIONAL {{ ?item wdt:P577 ?pubDate . }}
                      OPTIONAL {{ ?item p:P444 ?s . ?s ps:P444 ?score . OPTIONAL {{ ?s pq:P447 ?reviewer . }} }}
                      OPTIONAL {{ ?wikipedia schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
                      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "uk". ?reviewer rdfs:label ?reviewerLabel . }}
                    }} GROUP BY ?item ?desc_uk ?score ?reviewerLabel ?wikipedia"""
                    wd_res = http_get_json("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format":"json", "query":q}))
                    
                    data_parsed = {}
                    if wd_res:
                        try:
                            r = wd_res["results"]["bindings"][0]
                            data_parsed = {
                                "Genres_UK": r.get("genres_uk",{}).get("value",""),
                                "Description_UK": r.get("desc_uk",{}).get("value",""),
                                "Year_WD": (r.get("pubDateMin",{}).get("value","") or "")[:4],
                                "Rating": r.get("score",{}).get("value",""),
                                "RatingSource": r.get("reviewerLabel",{}).get("value",""),
                                "WikipediaUrl": r.get("wikipedia",{}).get("value",""),
                                "WikidataUrl": f"https://www.wikidata.org/wiki/{qid}"
                            }
                        except: pass
                    gp_logic.rw_json(path_q, {"_schema": SCHEMA_VER, "qid": qid, "data": data_parsed})

    # HowLongToBeat
    if ARGS.hltb and HLTB_AVAILABLE:
        path_h = os.path.join(DIRS["hltb"], f"{gp_logic.safe_name(name)}.json")
        if not os.path.exists(path_h):
            try:
                res = HowLongToBeat().search(name)
                h = str(res[0].main_story) if res else ""
                gp_logic.rw_json(path_h, {"_schema": SCHEMA_VER, "name": name, "hours": h})
            except Exception: pass

# ---------- MAIN ----------
def main():
    if ARGS.hltb and not HLTB_AVAILABLE:
        log_warn("Бібліотека howlongtobeatpy не знайдена. Прапор --hltb проігноровано.")

    ensure_dirs()
    print()
    if ARGS.reset_cache:
        import shutil
        shutil.rmtree(CACHE_DIR)
        ensure_dirs()
        log_warn("Кеш повністю очищено!")

    # 1. SIGL
    ids = get_sigl_ids()

    if not ARGS.render_only:
        # 2. STORE
        missing_store = []
        log("Перевірка кешу магазину...", "CACHE", "cyan")
        
        for bid in ids:
            path = os.path.join(DIRS["products"], f"{gp_logic.safe_name(bid)}.json")
            if not os.path.exists(path):
                missing_store.append(bid)
            elif os.path.getsize(path) < 10: # Битий файл
                os.remove(path)
                missing_store.append(bid)
        
        if missing_store:
            log(f"Потрібно завантажити: {_c(str(len(missing_store)), 'bold')}", "МАГАЗИН", "blue")
            bs = ARGS.pass_size
            chunks = [missing_store[i:i + bs] for i in range(0, len(missing_store), bs)]
            
            iter_obj = tqdm(chunks, desc=f"{_tag('МАГАЗИН', 'blue')} Завантаження", unit="пак") if tqdm else chunks
            for chunk in iter_obj:
                fetch_store_batch(chunk)
                time.sleep(0.5)
        else:
            log("Кеш магазину актуальний.", "МАГАЗИН", "green")
        
        # 3. ENRICH
        log("Збагачення метаданих...", "ДЕТАЛІ", "cyan")
        cached_ids = [x for x in ids if os.path.exists(os.path.join(DIRS["products"], f"{gp_logic.safe_name(x)}.json"))]
        
        iter_obj = tqdm(cached_ids, desc=f"{_tag('ДЕТАЛІ', 'cyan')} Аналіз", unit="гра") if tqdm else cached_ids
        for bid in iter_obj:
            # Викликаємо функцію з модуля, передаючи шляхи
            d = gp_logic.get_product_data(bid, DIRS, DATA_LANG)
            if d:
                enrich_one(d["name"].replace("(Game Preview)", "").replace("(PC)", "").strip())

    # 4. EXPORT
    log("Генерація звітів...", "ЕКСПОРТ", "yellow")
    rows = []
    bad_cache_count = 0
    
    for bid in ids:
        row = gp_logic.get_product_data(bid, DIRS, DATA_LANG)
        if row: 
            rows.append(row)
        else:
            bad_cache_count += 1
            try: os.remove(os.path.join(DIRS["products"], f"{gp_logic.safe_name(bid)}.json"))
            except: pass

    if bad_cache_count > 0:
        log_warn(f"Пропущено ігор (бітий кеш): {bad_cache_count}.")

    # CSV
    cols = ["id","name","genre","tier","rating","ratingSource","year","hours","publisher","developer","description","wikipedia","wikidata","image"]
    try:
        with open(FILES["out_csv"], "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows: w.writerow({k: r.get(k,"") for k in cols})
    except Exception as e:
        log_err(f"Помилка запису CSV: {e}")

    # HTML
    if not os.path.exists(FILES["template"]):
        log_err(f"Файл {FILES['template']} не знайдено!")
    else:
        try:
            with open(FILES["template"], "r", encoding="utf-8") as f: tmpl = f.read()
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            html_out = tmpl.replace("__TITLE__", f"Game Pass {MARKET} ({now})")
            html_out = html_out.replace("__DATA_JSON__", json.dumps(rows, ensure_ascii=False))
            with open(FILES["out_html"], "w", encoding="utf-8") as f: f.write(html_out)
            log(f"HTML: {_c(FILES['out_html'], 'bold')}", "ГОТОВО", "green")
        except Exception as e:
             log_err(f"Помилка запису HTML: {e}")
             
    log(f"CSV:  {_c(FILES['out_csv'], 'bold')}", "ГОТОВО", "green")
    log(f"Всього записів: {_c(str(len(rows)), 'bold')}", "СТАТ", "green")
    print()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print()
        log_warn("Зупинено користувачем.")
        sys.exit(0)