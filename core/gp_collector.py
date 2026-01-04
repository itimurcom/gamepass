# core/gp_collector.py
# Версія: 11.5 (Clean Path: index.html)

import os
import json
import time
import html
import re
import csv
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- ДЖЕРЕЛА (Updated with Xbox lists) ---
SIGL_SOURCES = {
    "PC Games":      "fdd9e2a7-0fee-49f6-ad69-4354098401ff",
    "Console/Ult":   "29a81209-df6f-41fd-a528-2ae6b91f719c",
    "EA Play":       "1084205d-3543-4537-97d5-d32247fb7280",
    "Bethesda":      "25654f59-002d-4522-a89e-2710dc25c68f",
    # Lists from Xbox.com
    "Leaving Soon":  "393f05bf-158a-4677-827e-854941a4253c",
    "Coming Soon":   "095bda36-f587-4631-9ea6-a496d6695508",
    "Most Played":   "50190333-6625-46d5-af90-33630a916327",
    "New Added":     "85639a09-90c7-4340-8452-9720498b58a1"
}

# --- SYSTEM ---
def safe_name(s):
    return "".join(c for c in (s or "").lower() if c.isalnum() or c in "-_")[:180] or "x"

def atomic_save(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

def setup_paths(base_dir):
    dirs = {
        "root": base_dir,
        "products": os.path.join(base_dir, "products"),
        "wikidata": os.path.join(base_dir, "wikidata"),
        "wd_sparql": os.path.join(base_dir, "wd_sparql"),
        "hltb": os.path.join(base_dir, "hltb")
    }
    for d in dirs.values(): os.makedirs(d, exist_ok=True)
    files = {
        "sigl": os.path.join(base_dir, "sigl_merged.json"),
        # ЗМІНА: тепер посилаємось на core/index.html
        "master_html": "core/index.html", 
        "out_csv": "gamepass_catalog.csv",
        "missing_log": "missing_ids_report.txt"
    }
    return dirs, files

# --- NETWORK ---
def http_get_json(url, headers=None, retries=3):
    h = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if headers: h.update(headers)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=30) as r: 
                return json.loads(r.read())
        except Exception:
            time.sleep(1 + i)
    return None

# --- COLLECTOR ---
def get_all_ids(market, lang, log_func=print):
    all_ids = set()
    log_func(f"Опитування каталогів...", "МЕРЕЖА", "36")
    
    for name, uuid in SIGL_SOURCES.items():
        url = "https://catalog.gamepass.com/sigls/v2?" + urllib.parse.urlencode({
            "id": uuid, "language": lang, "market": market
        })
        data = http_get_json(url)
        c = 0
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    gid = item.get("id") or item.get("productId")
                    if gid: 
                        all_ids.add(str(gid))
                        c += 1
        print(f"   > {name:<15}: {c}")
    return list(all_ids)

def download_store_batch(ids, dirs, market, lang):
    if not ids: return
    base_params = urllib.parse.urlencode({"market": market, "languages": lang})
    ids_str = ",".join(ids)
    url = f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={ids_str}&{base_params}"
    data = http_get_json(url)
    if data and "Products" in data:
        for p in data["Products"]:
            bid = p.get("ProductId") or p.get("BigId")
            if bid:
                atomic_save(os.path.join(dirs["products"], f"{safe_name(bid)}.json"), {"product": p})

def download_single_item(bid, dirs, market, lang):
    url = f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={bid}&market={market}&languages={lang}"
    data = http_get_json(url)
    if not data or "Products" not in data or not data["Products"]:
        if market != "US":
            url = f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={bid}&market=US&languages=en-us"
            data = http_get_json(url)

    if data and "Products" in data and len(data["Products"]) > 0:
        p = data["Products"][0]
        atomic_save(os.path.join(dirs["products"], f"{safe_name(bid)}.json"), {"product": p})
        return True
    return False

def retry_missing_files(all_ids, dirs, market, lang, log_func=print):
    missing = [bid for bid in all_ids if not os.path.exists(os.path.join(dirs["products"], f"{safe_name(bid)}.json"))]
    if not missing: return []

    log_func(f"Порятунок {len(missing)} ігор...", "РЯТУВАЛЬНИК", "33")
    still_missing = []
    total = len(missing)
    
    for i, bid in enumerate(missing, 1):
        success = download_single_item(bid, dirs, market, lang)
        if not success:
            still_missing.append(bid)
        
        if i % 5 == 0 or i == total:
            p = int((i / total) * 100)
            print(f"\r   > Докачка: {i}/{total} ({p}%)", end="", flush=True)
            
    print()
    return still_missing

# --- META ---
def clean_game_title(name):
    if not name: return ""
    name = re.sub(r'\(.*?\)', '', name)
    for t in ["Edition", "Standard", "Deluxe", "Premium", "Ultimate", "Game of the Year", "GOTY", "Bundle", "Windows 10", "for Windows"]:
        name = re.sub(f"(?i){t}", "", name)
    name = re.sub(r'[™®©:–-]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()

def download_wiki_data(name, clean_id, dirs):
    path_wd = os.path.join(dirs["wikidata"], f"{clean_id}.json")
    qid = None
    if os.path.exists(path_wd):
        try:
            with open(path_wd, "r") as f:
                qid = json.load(f).get("qid")
        except: pass
    else:
        u = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({
            "action": "wbsearchentities", "search": clean_game_title(name), "language": "en", "format": "json", "limit": 1, "type": "item"
        })
        d = http_get_json(u)
        if d and d.get("search"):
            qid = d["search"][0]["id"]
            atomic_save(path_wd, {"qid": qid, "name": name})

    if qid:
        path_sp = os.path.join(dirs["wd_sparql"], f"{safe_name(qid)}.json")
        if not os.path.exists(path_sp):
            q = f"""SELECT ?desc_uk ?wikipedia (MIN(?pubDate) as ?date) WHERE {{
              BIND(wd:{qid} AS ?item)
              OPTIONAL {{ ?item schema:description ?desc_uk FILTER(LANG(?desc_uk)="uk") }}
              OPTIONAL {{ ?item wdt:P577 ?pubDate . }}
              OPTIONAL {{ ?wikipedia schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
            }} GROUP BY ?item ?desc_uk ?wikipedia"""
            u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"format":"json", "query":q})
            res = http_get_json(u)
            data_p = {}
            if res and "results" in res and res["results"]["bindings"]:
                r = res["results"]["bindings"][0]
                data_p = {
                    "Description_UK": r.get("desc_uk", {}).get("value", ""),
                    "WikiUrl": r.get("wikipedia", {}).get("value", ""),
                    "Year_WD": r.get("date", {}).get("value", "")[:4]
                }
            atomic_save(path_sp, {"data": data_p})

def download_hltb_data(name, clean_id, dirs, status_cb=None):
    try:
        from howlongtobeatpy import HowLongToBeat
    except ImportError:
        return

    path = os.path.join(dirs["hltb"], f"{clean_id}.json")
    if os.path.exists(path):
        return

    if name.startswith("UnknownID"):
        return

    clean_search = clean_game_title(name)
    hours = "0"
    try:
        res = HowLongToBeat().search(clean_search)
        if res:
            best = max(res, key=lambda x: x.similarity)
            hours = str(best.main_story)
    except Exception:
        pass

    atomic_save(path, {"hours": hours})

# --- MULTI-THREADING HANDLERS ---

def _worker_metadata(task):
    # task = (bid, name, clean_id, dirs)
    bid, name, clean_id, dirs = task
    
    # 1. Wiki
    try:
        download_wiki_data(name, clean_id, dirs)
    except Exception:
        pass
    
    # 2. HLTB
    try:
        download_hltb_data(name, clean_id, dirs)
    except Exception:
        pass
    
    return bid

def download_metadata_threaded(tasks, dirs, log_func=print):
    """
    Виконує завантаження метаданих паралельно.
    tasks: список кортежів (bid, name, clean_id)
    """
    if not tasks:
        return
    
    total = len(tasks)
    log_func(f"Паралельне завантаження для {total} ігор...", "ПОТОКИ", "35")
    
    # Підготовка повних даних для воркерів
    worker_tasks = [(t[0], t[1], t[2], dirs) for t in tasks]
    
    completed = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_worker_metadata, t): t for t in worker_tasks}
        
        for future in as_completed(futures):
            completed += 1
            if completed % 5 == 0 or completed == total:
                p = int((completed / total) * 100)
                # Виводимо прогрес бар
                bar = '=' * int(20 * completed // total) + '-' * (20 - int(20 * completed // total))
                print(f"\r   > Прогрес: |{bar}| {completed}/{total} ({p}%)", end="", flush=True)
    
    print() # New line after bar

# --- EXPORTER ---
def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\xa0', ' ').replace('\r', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'(\n\s*){3,}', '\n\n', text)
    return text.strip()

def save_html_report(rows, template_path, out_path):
    return False, "DEPRECATED: Use gp_export.save_static_web_report"

def save_csv_report(rows, out_path):
    return False, "DEPRECATED: Use gp_export.save_csv_report"