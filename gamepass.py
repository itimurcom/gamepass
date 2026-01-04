#!/usr/bin/env python3
# gamepass.py — v10.6 (Image Protocol Fix)

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

SCRIPT_VERSION = "v10.6"

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

# --- PROGRESS STAGE TRACKING ---
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

def get_best_image(images_list):
    """Шукає постер, додає протокол https."""
    if not images_list: return ""
    
    target_url = ""
    # 1. Пріоритет: Poster
    for img in images_list:
        if img.get("ImagePurpose") == "Poster":
            target_url = img.get("Uri", "")
            break
    
    # 2. Якщо немає постера, беремо першу картинку
    if not target_url and images_list:
        target_url = images_list[0].get("Uri", "")
        
    # 3. FIX: Додаємо https, якщо посилання починається з //
    if target_url.startswith("//"):
        target_url = "https:" + target_url
        
    return target_url

def parse_product_local(bid, dirs):
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
    set_stage(bid, "parse localized properties")
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
    # Wiki
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
    # HLTB
    hours = ""
    try:
        h_f = os.path.join(dirs["hltb"], f"{clean_id}.json")
        if os.path.exists(h_f):
            with open(h_f) as f: 
                h_val = json.load(f).get("hours", "0")
                if h_val != "0": hours = h_val
    except: pass

    set_stage(bid, "rating")
    # Rating (float fix)
    rating = 0.0
    rating_src = ""
    ms_score = store_data.get("MarketProperties", [{}])[0].get("UsageData", [{}])[0].get("AverageRating", 0)
    if ms_score:
        rating = round(ms_score * 20, 1)
        rating_src = "Microsoft"

    set_stage(bid, "images")
    # Image processing
    raw_images = store_data.get("Images", [])
    image_url = get_best_image(raw_images)

    links = { "store": f"https://www.xbox.com/en-us/games/store/{bid}", "wiki": wiki_url }

    set_stage(bid, "assemble html")
    html_uk = make_html_desc(desc_store_uk, wiki_desc_uk, links, "uk")
    html_en = make_html_desc(desc_store_en, "", links, "en")

    set_stage(bid, "done")
    return {
        "id": bid,
        "name": clean_name,
        "genre": genre,
        "tier": "Standard",
        "rating": rating,
        "ratingSource": rating_src,
        "year": year,
        "hours": hours,
        "publisher": props.get("PublisherName", ""),
        "developer": props.get("DeveloperName", ""),
        "image": image_url, # Now strictly HTTPS
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
    p.add_argument("--reset-cache", action="store_true")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    
    CACHE_DIR = os.path.join(os.getcwd(), ".cache")
    DIRS, FILES = gp_collector.setup_paths(CACHE_DIR)
    
    if args.reset_cache:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        DIRS, FILES = gp_collector.setup_paths(CACHE_DIR)
        log("Кеш очищено.", "КЕШ", "33")

    ids = []
    if os.path.exists(FILES["sigl"]) and not args.reset_cache:
        try: ids = json.load(open(FILES["sigl"]))["ids"]
        except: pass
    
    if not ids:
        ids = gp_collector.get_all_ids(MARKET, DATA_LANG, log)
        gp_collector.atomic_save(FILES["sigl"], {"ids": ids})
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

    log("Обробка файлів (v10 Parser)...", "ОБРОБКА", "36")
    final_rows = []
    
    files_on_disk = set(os.listdir(DIRS["products"]))
    valid_ids = [bid for bid in ids if f"{gp_collector.safe_name(bid)}.json" in files_on_disk]
    total = len(valid_ids)

    for i, bid in enumerate(valid_ids, 1):
        set_stage(bid, "parse")
        set_stage(bid, "parse")
        row = parse_product_local(bid, DIRS)
        
        if row:
            if not args.quick and not row["name"].startswith("UnknownID"):
                set_stage(bid, "wiki download")
                gp_collector.download_wiki_data(row["i18n"]["en"]["name"], gp_collector.safe_name(row["i18n"]["en"]["name"]), DIRS)
                set_stage(bid, "hltb download")
                gp_collector.download_hltb_data(row["i18n"]["en"]["name"], gp_collector.safe_name(row["i18n"]["en"]["name"]), DIRS)
                set_stage(bid, "re-parse")
                row = parse_product_local(bid, DIRS)

            final_rows.append(row)
        
        if i % 5 == 0 or i == total: print_progress(i, total, "Аналіз")

    sys.stdout.write("\n")

    log("Збереження...", "ЕКСПОРТ", "32")
    ok, msg = gp_collector.save_html_report(final_rows, FILES["template"], FILES["out_html"])
    if ok: log(f"HTML: {FILES['out_html']}", "ГОТОВО", "32")
    
    ok, msg = gp_collector.save_csv_report(final_rows, FILES["out_csv"])
    if ok: log(f"CSV: {FILES['out_csv']}", "ГОТОВО", "32")

    log(f"Успішно: {_c(str(len(final_rows)), '32')}", "РЕЗУЛЬТАТ", "32")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(0)
