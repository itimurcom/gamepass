# core/gp_logic.py
# Версія: 12.0 (Refactored: All Logic Here)

import os
import json
import re
import html

# --- КОНСТАНТИ ---
AAA_PUBLISHERS = [
    "xbox game studios", "bethesda", "electronic arts", "ea", "ubisoft", 
    "activision", "blizzard", "rockstar", "2k", "capcom", "square enix", 
    "bandai namco", "sega", "wb games", "sony", "cd projekt", "take-two",
    "konami", "riot games", "bungie", "epic games"
]

INDIE_MARKERS = ["indie", "independent", "аркади", "arcade", "platformer", "puzzle"]

# --- УТИЛІТИ ---
def safe_name(s):
    return "".join(c for c in (s or "").lower() if c.isalnum() or c in "-_")[:180] or "x"

def clean_text(text):
    """Очищує текст від HTML тегів та зайвих пробілів."""
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\xa0', ' ').replace('\r', '')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'(\n\s*){3,}', '\n\n', text)
    return text.strip()

def make_html_desc(store_txt, wiki_txt, links, lang="uk"):
    """Формує HTML блок опису для модального вікна."""
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

# --- ДОПОМІЖНІ ФУНКЦІЇ ПАРСИНГУ ---

def _is_str(x):
    return isinstance(x, str)

def _clean_str(s: str) -> str:
    return (s or "").strip()

def extract_genres_from_product(props: dict) -> list:
    out = []
    candidates = []
    for key in ("Categories", "Category", "Subcategory", "Genres", "Genre"):
        v = props.get(key)
        if isinstance(v, list):
            candidates.extend(v)
        elif _is_str(v) and v:
            candidates.append(v)
    for g in candidates:
        if not _is_str(g): continue
        g = _clean_str(g)
        if not g: continue
        if g.startswith("{") or g.startswith("['") or g.lower() in ("game", "gaming", "application"):
            continue
        if g not in out:
            out.append(g)
    return out

def pick_best_image_uri(p: dict, lp_main: dict) -> str:
    priority = [
        "Poster", "BoxArt", "BrandedKeyArt", "KeyArt", "SuperHeroArt", "Hero",
        "TitledHeroArt", "FeaturePromotionalSquareArt", "Tile", "Logo", "Screenshot"
    ]
    imgs = []
    # 1) Main Localized Props
    if isinstance(lp_main, dict):
        imgs = lp_main.get("Images") or []
    # 2) SKU Localized Props
    if (not imgs) and p.get("DisplaySkuAvailabilities"):
        try:
            skus = p["DisplaySkuAvailabilities"][0].get("Sku", {}).get("LocalizedProperties", [])
            if skus:
                imgs = skus[0].get("Images") or []
        except Exception: pass
    # 3) MarketProperties
    if (not imgs) and p.get("MarketProperties"):
        try:
            imgs = p["MarketProperties"][0].get("Images") or []
        except Exception: pass

    def _purpose(img: dict) -> str:
        return (img.get("ImagePurpose") or img.get("Purpose") or img.get("ImageType") or "").strip()

    uri = ""
    if isinstance(imgs, list) and imgs:
        for pur in priority:
            for img in imgs:
                if not isinstance(img, dict): continue
                if _purpose(img) == pur and img.get("Uri"):
                    uri = img["Uri"]
                    break
            if uri: break
        if not uri: # Fallback to any URI
            for img in imgs:
                if isinstance(img, dict) and img.get("Uri"):
                    uri = img["Uri"]
                    break
    if uri and uri.startswith("//"):
        uri = "https:" + uri
    return uri

def analyze_metrics(product_raw, wikidata_data, genres_str):
    props = product_raw.get("Properties", {})
    market_props = product_raw.get("MarketProperties", [])
    
    # Видавець (шукаємо EN або EN-US)
    lps = product_raw.get("LocalizedProperties", [])
    lp_en = next((x for x in lps if x.get("Language","").lower() in ("en-us", "en")), lps[0] if lps else {})
    
    publisher = (lp_en.get("PublisherName") or props.get("PublisherName") or "").lower()
    
    # Розмір гри
    max_size_gb = 0
    if product_raw.get("DisplaySkuAvailabilities"):
        for sku_avail in product_raw["DisplaySkuAvailabilities"]:
            pkg = sku_avail.get("Sku", {}).get("Properties", {}).get("Packages", [])
            if pkg:
                size_bytes = pkg[0].get("MaxDownloadFileSizeInBytes", 0)
                max_size_gb = max(max_size_gb, size_bytes / (1024**3))

    # Tier Logic
    is_aaa_publisher = any(p in publisher for p in AAA_PUBLISHERS)
    is_huge_game = max_size_gb > 45
    is_indie_genre = any(m in genres_str.lower() for m in INDIE_MARKERS)
    
    tier = "Indie/AA"
    if (is_aaa_publisher or is_huge_game) and not is_indie_genre:
        tier = "AAA"
    
    # Rating Logic
    ms_score = 0
    ms_count = 0
    for mp in market_props:
        usage = mp.get("UsageData", [])
        for u in usage:
            if u.get("AggregateTimeSpan") == "AllTime":
                ms_score = u.get("AverageRating", 0)
                ms_count = u.get("RatingCount", 0)
                break
        if ms_count > 0: break
    
    wd_score_raw = wikidata_data.get("Rating", 0)
    wd_score = 0
    try:
        wd_val = float(str(wd_score_raw).split("/")[0])
        if wd_val <= 5: wd_score = wd_val * 20
        elif wd_val <= 10: wd_score = wd_val * 10
        else: wd_score = wd_val
    except: pass

    final_score = 0
    if ms_count > 0:
        R = ms_score * 20
        v = ms_count
        m = 50 
        C = 75 
        final_score = (v / (v + m)) * R + (m / (v + m)) * C
    elif wd_score > 0:
        final_score = wd_score
    
    score_src = f"{ms_count} (Xbox)" if ms_count else ("Wiki" if wd_score > 0 else "")
    
    return tier, round(final_score, 1), score_src

# --- ГОЛОВНА ФУНКЦІЯ ПАРСИНГУ ---

def parse_product(bid, dirs, tags=None, log_func=None):
    """
    Зчитує JSON файли з дисків, об'єднує дані та повертає фінальний об'єкт для data.js.
    """
    path = os.path.join(dirs["products"], f"{safe_name(bid)}.json")
    
    # 1. Завантаження JSON продукту
    if log_func: log_func(bid, "load product json")
    store_data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            full_json = json.load(f)
            if "product" in full_json:
                store_data = full_json["product"]
    except: return None # Файл битий або відсутній

    if log_func: log_func(bid, "parse properties")
    props = store_data.get("Properties", {})
    lps = store_data.get("LocalizedProperties", [])
    
    # 2. Вибір локалізації (FIX: Loose language matching)
    lp_uk = next((x for x in lps if x.get("Language","").lower() in ("uk-ua", "uk")), {})
    lp_en = next((x for x in lps if x.get("Language","").lower() in ("en-us", "en")), {})
    
    # Fallbacks
    if not lp_uk: lp_uk = lp_en
    if not lp_en: lp_en = lp_uk
    if not lp_uk and lps: lp_uk = lps[0] # First available
    if not lp_en and lps: lp_en = lps[0]

    # 3. Назви
    name = lp_uk.get("ProductTitle") or lp_en.get("ProductTitle") or props.get("ProductTitle") or f"UnknownID_{bid}"
    clean_name = name.replace("(PC)", "").replace("(Windows)", "").strip()
    clean_id = safe_name(clean_name)

    # 4. Описи
    desc_store_uk = clean_text(lp_uk.get("ProductDescription") or lp_uk.get("ShortDescription") or "")
    desc_store_en = clean_text(lp_en.get("ProductDescription") or lp_en.get("ShortDescription") or desc_store_uk)

    # 5. Wikidata Check
    if log_func: log_func(bid, "wiki check/cache")
    wiki_desc_uk = ""
    wiki_url = ""
    wd_data = {}
    try:
        wd_f = os.path.join(dirs['wikidata'], f'{clean_id}.json')
        if os.path.exists(wd_f):
            with open(wd_f) as f: qid = json.load(f).get('qid')
            if qid:
                sp_f = os.path.join(dirs["wd_sparql"], f"{safe_name(qid)}.json")
                if os.path.exists(sp_f):
                    with open(sp_f) as f:
                        wd_data = json.load(f).get('data', {})
                        wiki_desc_uk = clean_text(wd_data.get('Description_UK', ''))
                        wiki_url = wd_data.get('WikiUrl', '')
    except: pass

    # 6. HLTB Check
    if log_func: log_func(bid, "hltb check/cache")
    hours = ""
    try:
        h_f = os.path.join(dirs["hltb"], f"{clean_id}.json")
        if os.path.exists(h_f):
            with open(h_f) as f: 
                h_val = json.load(f).get("hours", "0")
                if h_val != "0": hours = h_val
    except: pass

    # 7. Аналіз та Метрики
    if log_func: log_func(bid, "metrics")
    
    # Жанри (з пропсів або вікі)
    genres_list = extract_genres_from_product(props)
    genre_str = ", ".join(genres_list)
    
    # Tier / Rating
    tier, rating, rating_src = analyze_metrics(store_data, wd_data, genre_str)
    
    # Картинка
    image_url = pick_best_image_uri(store_data, lp_uk) # lp_uk is best approximation of main

    # Посилання
    links = { "store": f"https://www.xbox.com/en-us/games/store/{bid}", "wiki": wiki_url }

    # 8. HTML Генерація
    html_uk = make_html_desc(desc_store_uk, wiki_desc_uk, links, "uk")
    html_en = make_html_desc(desc_store_en, "", links, "en")

    # Жанр для відображення (беремо перший або category)
    display_genre = props.get("Category", "Unknown")
    if genres_list: display_genre = genres_list[0]

    year = wd_data.get("Year_WD") or (props.get("OriginalReleaseDate") or "")[:4]

    return {
        "id": bid,
        "name": clean_name,
        "clean_id": clean_id,
        "genre": display_genre,
        "tier": tier,
        "rating": rating,
        "ratingSource": rating_src,
        "year": year,
        "hours": hours,
        "tags": tags or [],
        "publisher": props.get("PublisherName", ""),
        "developer": props.get("DeveloperName", ""),
        "image": image_url,
        "i18n": {
            "uk": { "name": clean_name, "genre": display_genre, "desc": html_uk },
            "en": { "name": clean_name, "genre": display_genre, "desc": html_en }
        },
        "links": links
    }