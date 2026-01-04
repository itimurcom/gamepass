#!/usr/bin/env python3
# gamepass.py — v11.8 (Fix: No Template Check)

import argparse
import os
import sys
import shutil
import json
import html
import re
import signal
from datetime import datetime

from core import gp_collector 
from core import gp_export

SCRIPT_VERSION = "v11.8"

# --- SIGNAL HANDLER ---
def aggressive_stop(signum, frame):
    sys.stdout.write(f"\n\n\033[31m[СТОП]\033[0m Примусова зупинка.\n")
    os._exit(1)

signal.signal(signal.SIGINT, aggressive_stop)

# CONFIG
MARKET = "US"
DATA_LANG = "uk-ua"
DISPLAY_LANGS = "uk-ua,en-us"

# UI UTILS
CURRENT_STAGE = ""
CURRENT_BID = ""

def set_stage(bid, stage):
    global CURRENT_STAGE, CURRENT_BID
    CURRENT_STAGE = stage
    CURRENT_BID = bid

IS_TTY = sys.stdout.isatty()
def _c(txt, code): return f"\033[{code}m{txt}\033[0m" if IS_TTY else txt

def log(msg, label="ІНФО", color="34"): 
    sys.stdout.write("\r\033[K")
    print(f"{_c('['+label+']', color)} {msg}")

def print_progress(current, total, prefix=""):
    if not IS_TTY: return
    p = 100 * (current / float(total)) if total > 0 else 0
    bar = '=' * int(30 * current // total) + '-' * (30 - int(30 * current // total))
    suffix = f" | {CURRENT_BID} | {CURRENT_STAGE}" if CURRENT_STAGE else ""
    sys.stdout.write(f"\r{prefix}: |{_c(bar, '36')}| {current}/{total} ({p:.0f}%)" + suffix)
    sys.stdout.flush()

def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\xa0', ' ').replace('\r', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'(\n\s*){3,}', '\n\n', text)
    return text.strip()

def make_html_desc(store_txt, wiki_txt, links, lang="uk"):
    html_out = ""
    
    if store_txt and "Опис відсутній" not in store_txt:
        safe_txt = html.escape(store_txt).replace("\n", "<br>")
        url = links.get("store", "#")
        html_out += f'<div class="desc-block"><a href="{url}" target="_blank" class="desc-header">🎮 Microsoft Store</a><div class="desc-body">{safe_txt}</div></div>'
    
    if wiki_txt:
        safe_txt = html.escape(wiki_txt).replace("\n", "<br>")
        url = links.get("wiki", "#")
        label = "Wikipedia (UK)" if lang == "uk" else "Wikipedia"
        html_out += f'<div class="desc-block"><a href="{url}" target="_blank" class="desc-header">📖 {label}</a><div class="desc-body">{safe_txt}</div></div>'
    
    if not html_out:
        html_out = "<div style='color:#888; font-style:italic;'>Опис недоступний / No description.</div>"
        
    return html_out

def get_best_image(store_data, lp_uk, lp_en):
    candidates = []
    if lp_uk.get("Images"): candidates.extend(lp_uk["Images"])
    if lp_en.get("Images"): candidates.extend(lp_en["Images"])
    if store_data.get("Images"): candidates.extend(store_data["Images"])
    
    if not candidates: return ""

    priority_types = ["Poster", "BoxArt", "BrandedKeyArt", "TitledHeroArt", "SuperHeroArt", "Image"]
    target_url = ""
    
    for p_type in priority_types:
        for img in candidates:
            if img.get("ImagePurpose") == p_type and img.get("Uri"):
                target_url = img["Uri"]
                break
        if target_url: break
    
    if not target_url:
        for img in candidates:
            if img.get("Uri"):
                target_url = img["Uri"]
                break
                
    if target_url.startswith("//"):
        target_url = "https:" + target_url
        
    return target_url

def parse_product_local(bid, dirs, tags=None):
    path = os.path.join(dirs["products"], f"{gp_collector.safe_name(bid)}.json")
    
    set_stage(bid, "load product json")
    store_data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            full_json = json.load(f)
            if "product" in full_json:
                store_data = full_json["product"]
    except: return None

    set_stage(bid, "parse properties")
    props = store_data.get("Properties", {})
    lps = store_data.get("LocalizedProperties", [])
    
    lp_uk = next((x for x in lps if x.get("Language","").lower() == "uk-ua"), {})
    lp_en = next((x for x in lps if x.get("Language","").lower() == "en-us"), {})
    if not lp_uk: lp_uk = lp_en

    name = lp_uk.get("ProductTitle") or props.get("ProductTitle") or f"UnknownID_{bid}"
    clean_name = name.replace("(PC)", "").replace("(Windows)", "").strip()
    
    genre = props.get("Category", "Unknown")
    if genre.lower() == "game": genre = "Unknown" 

    desc_store_uk = clean_text(lp_uk.get("ProductDescription") or lp_uk.get("ShortDescription") or "")
    desc_store_en = clean_text(lp_en.get("ProductDescription") or lp_en.get("ShortDescription") or desc_store_uk)

    clean_id = gp_collector.safe_name(clean_name)
    year = (props.get("OriginalReleaseDate") or "")[:4]
    
    set_stage(bid, "wiki check/cache")
    wiki_desc_uk = ""
    wiki_url = ""
    try:
        wd_f = os.path.join(dirs['wikidata'], f'{clean_id}.json')
        if os.path.exists(wd_f):
            with open(wd_f) as f: qid = json.load(f).get('qid')
            if qid:
                sp_f = os.path.join(dirs["wd_sparql"], f"{gp_collector.safe_name(qid)}.json")
                if os.path.exists(sp_f):
                    with open(sp_f) as f:
                        wdata = json.load(f).get('data', {})
                        if wdata.get('Year_WD'): year = wdata['Year_WD']
                        wiki_desc_uk = clean_text(wdata.get('Description_UK', ''))
                        wiki_url = wdata.get('WikiUrl', '')
    except: pass

    set_stage(bid, "hltb check/cache")
    hours = ""
    try:
        h_f = os.path.join(dirs["hltb"], f"{clean_id}.json")
        if os.path.exists(h_f):
            with open(h_f) as f: 
                h_val = json.load(f).get("hours", "0")
                if h_val != "0": hours = h_val
    except: pass

    set_stage(bid, "rating")
    rating = 0.0
    rating_src = ""
    ms_score = store_data.get("MarketProperties", [{}])[0].get("UsageData", [{}])[0].get("AverageRating", 0)
    if ms_score:
        rating = round(ms_score * 20, 1)
        rating_src = "Microsoft"

    set_stage(bid, "images")
    image_url = get_best_image(store_data, lp_uk, lp_en)

    links = { "store": f"https://www.xbox.com/en-us/games/store/{bid}", "wiki": wiki_url }

    set_stage(bid, "assemble html")
    html_uk = make_html_desc(desc_store_uk, wiki_desc_uk, links, "uk")
    html_en = make_html_desc(desc_store_en, "", links, "en")

    set_stage(bid, "done")
    return {
        "id": bid,
        "name": clean_name,
        "clean_id": clean_id,
        "genre": genre,
        "tier": "Standard",
        "rating": rating,
        "ratingSource": rating_src,
        "year": year,
        "hours": hours,
        "tags": tags or [],
        "publisher": props.get("PublisherName", ""),
        "developer": props.get("DeveloperName", ""),
        "image": image_url,
        "i18n": {
            "uk": { "name": clean_name, "genre": genre, "desc": html_uk },
            "en": { "name": clean_name, "genre": genre, "desc": html_en }
        },
        "links": links
    }

def main():
    print(f"\n{_c('=== Game Pass Script '+SCRIPT_VERSION+' ===', '37;1')}")
    
    try: import howlongtobeatpy
    except ImportError: 
        print(f"{_c('[ПОМИЛКА]', '31')} Бібліотеку 'howlongtobeatpy' не знайдено.")
        print(f"          Виконайте: {_c('pip install howlongtobeatpy --break-system-packages', '33')}\n")

    p = argparse.ArgumentParser()
    p.add_argument("--reset-cache", action="store_true", help="Delete EVERYTHING (images, data, list)")
    p.add_argument("--reset-merged", action="store_true", help="Delete only ID list to fetch new sources")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    
    CACHE_DIR = os.path.join(os.getcwd(), ".cache")
    DIRS, FILES = gp_collector.setup_paths(CACHE_DIR)
    
    if args.reset_cache:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        DIRS, FILES = gp_collector.setup_paths(CACHE_DIR)
        log("Повний кеш очищено.", "КЕШ", "33")
    
    if args.reset_merged:
        if os.path.exists(FILES["sigl"]):
            try:
                os.remove(FILES["sigl"])
                log("Список ID очищено (нове сканування джерел).", "КЕШ", "33")
            except Exception as e:
                log(f"Не вдалося видалити файл списку: {e}", "ПОМИЛКА", "31")

    ids = []
    id_tags_map = {}

    if os.path.exists(FILES["sigl"]) and not args.reset_cache:
        try: 
            data = json.load(open(FILES["sigl"]))
            ids = data.get("ids", [])
            id_tags_map = data.get("tags", {})
        except: pass
    
    if not ids:
        ids, id_tags_map = gp_collector.get_all_ids(MARKET, DATA_LANG, log)
        gp_collector.atomic_save(FILES["sigl"], {"ids": ids, "tags": id_tags_map})
    else:
        log(f"Локальний список: {len(ids)}", "КЕШ", "32")

    print(f"{_c('[ВСЬОГО]', '32')} Ігор у базі: {_c(str(len(ids)), '32;1')}")

    missing = [x for x in ids if not os.path.exists(os.path.join(DIRS["products"], f"{gp_collector.safe_name(x)}.json"))]
    if missing:
        log(f"Завантаження {len(missing)} файлів...", "МАГАЗИН", "36")
        batch = 20
        chunks = [missing[i:i+batch] for i in range(0, len(missing), batch)]
        for i, chunk in enumerate(chunks, 1):
            gp_collector.download_store_batch(chunk, DIRS, MARKET, DISPLAY_LANGS)
            print_progress(min(i*batch, len(missing)), len(missing), "Прогрес")
        sys.stdout.write("\n")
        gp_collector.retry_missing_files(ids, DIRS, MARKET, DISPLAY_LANGS, log)
    else:
        log("Всі файли на місці.", "КЕШ", "32")

    # --- ЕТАП 1: Попередній аналіз (Fast Scan) ---
    log("Фаза 1: Швидке сканування локальних файлів...", "АНАЛІЗ", "36")
    
    files_on_disk = set(os.listdir(DIRS["products"]))
    valid_ids = [bid for bid in ids if f"{gp_collector.safe_name(bid)}.json" in files_on_disk]
    
    rows_map = {}
    enrich_queue = [] # (bid, name, clean_id)
    
    total = len(valid_ids)
    for i, bid in enumerate(valid_ids, 1):
        # Pass tags to parser
        tags = id_tags_map.get(str(bid), [])
        row = parse_product_local(bid, DIRS, tags)
        
        if row:
            rows_map[bid] = row
            if not args.quick and not row["name"].startswith("UnknownID"):
                enrich_queue.append((bid, row["i18n"]["en"]["name"], row["clean_id"]))
        
        if i % 50 == 0 or i == total: print_progress(i, total, "Скан")
    sys.stdout.write("\n")

    # --- ЕТАП 2: Паралельне збагачення (Parallel Enrich) ---
    if enrich_queue:
        log(f"Фаза 2: Збагачення даними ({len(enrich_queue)} задач)...", "NET", "35")
        gp_collector.download_metadata_threaded(enrich_queue, DIRS, log)
    else:
        log("Фаза 2: Пропуск (всі дані є або режим quick)", "SKIP", "33")

    # --- ЕТАП 3: Оновлення (Re-Assemble) ---
    if enrich_queue:
        log("Фаза 3: Оновлення змінених записів...", "ОНОВЛЕННЯ", "36")
        count = 0
        total_q = len(enrich_queue)
        for bid, _, _ in enrich_queue:
            count += 1
            tags = id_tags_map.get(str(bid), [])
            new_row = parse_product_local(bid, DIRS, tags)
            if new_row:
                rows_map[bid] = new_row
            if count % 20 == 0 or count == total_q: print_progress(count, total_q, "Re-parse")
        sys.stdout.write("\n")

    final_rows = list(rows_map.values())

    # --- EXPORT TO STATIC WEB ---
    log("Збереження...", "ЕКСПОРТ", "32")
    
    CATALOG_DIR = os.path.join(os.getcwd(), "catalog")
    
    # 1. JS Data Export ONLY
    ok, msg = gp_export.export_data_js(final_rows, CATALOG_DIR)
    if ok: 
        log(f"DATA: {os.path.join(CATALOG_DIR, 'data.js')}", "ГОТОВО", "32")
    else:
        log(f"Помилка JS: {msg}", "ERROR", "31")

    # 2. CSV Export
    ok, msg = gp_export.save_csv_report(final_rows, FILES["out_csv"])
    if ok: 
        log(f"CSV: {FILES['out_csv']}", "ГОТОВО", "32")

    log(f"Успішно: {_c(str(len(final_rows)), '32')}", "РЕЗУЛЬТАТ", "32")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(0)