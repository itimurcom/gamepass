# core/gp_logic.py
# Версія: 12.3 (Fix: Wikipedia EN Fallback)

import os
import json
import re
import html
from datetime import datetime

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
    
    # 1. Магазин
    if store_txt and "Опис відсутній" not in store_txt:
        safe_txt = html.escape(store_txt).replace("\n", "<br>")
        url = links.get("store", "#")
        html_out += f'<div class="desc-block"><a href="{url}" target="_blank" class="desc-header">🎮 Microsoft Store</a><div class="desc-body">{safe_txt}</div></div>'
    
    # 2. Wikipedia (з позначкою мови, якщо це фолбек)
    if wiki_txt:
        # Визначаємо, чи це англійський текст (проста евристика)
        is_en_fallback = lang == "uk" and not any(c in wiki_txt.lower() for c in "іїєґабвгджзклмнопрстуфхцчшщюя")
        
        safe_txt = html.escape(wiki_txt).replace("\n", "<br>")
        url = links.get("wiki", "#")
        
        label = "Wikipedia"
        if lang == "uk":
            label = "Wikipedia (EN)" if is_en_fallback else "Wikipedia (UK)"
            
        html_out += f'<div class="desc-block"><a href="{url}" target="_blank" class="desc-header">📖 {label}</a><div class="desc-body">{safe_txt}</div></div>'
    
    if not html_out:
        html_out = "<div style='color:#888; font-style:italic;'>Опис недоступний / No description.</div>"
        
    return html_out

# --- EXTRACTION HELPERS ---

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
    if isinstance(lp_main, dict):
        imgs = lp_main.get("Images") or []
    if (not imgs) and p.get("DisplaySkuAvailabilities"):
        try:
            skus = p["DisplaySkuAvailabilities"][0].get("Sku", {}).get("LocalizedProperties", [])
            if skus:
                imgs = skus[0].get("Images") or []
        except Exception: pass
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
        if not uri:
            for img in imgs:
                if isinstance(img, dict) and img.get("Uri"):
                    uri = img["Uri"]
                    break
    if uri and uri.startswith("//"):
        uri = "https:" + uri
    return uri

def _is_valid_year_str(d_str):
    if not d_str or len(d_str) < 4: return False
    try:
        y = int(d_str[:4])
        return 1970 <= y <= 2035
    except:
        return False

def extract_release_year(p_raw, wd_data):
    if wd_data.get("Year_WD"):
        return wd_data["Year_WD"]
    for mp in p_raw.get("MarketProperties", []):
        d = mp.get("OriginalReleaseDate")
        if _is_valid_year_str(d):
            return d[:4]
    props = p_raw.get("Properties", {})
    d = props.get("OriginalReleaseDate")
    if _is_valid_year_str(d):
        return d[:4]
    return ""

def analyze_metrics(product_raw, wikidata_data, genres_str):
    props = product_raw.get("Properties", {})
    market_props = product_raw.get("MarketProperties", [])
    
    lps = product_raw.get("LocalizedProperties", [])
    lp_en = next((x for x in lps if x.get("Language","").lower() in ("en-us", "en")), lps[0] if lps else {})
    
    publisher = (lp_en.get("PublisherName") or props.get("PublisherName") or "").lower()
    
    max_size_gb = 0
    if product_raw.get("DisplaySkuAvailabilities"):
        for sku_avail in product_raw["DisplaySkuAvailabilities"]:
            pkg = sku_avail.get("Sku", {}).get("Properties", {}).get("Packages", [])
            if pkg:
                size_bytes = pkg[0].get("MaxDownloadFileSizeInBytes", 0)
                max_size_gb = max(max_size_gb, size_bytes / (1024**3))

    is_aaa_publisher = any(p in publisher for p in AAA_PUBLISHERS)
    is_huge_game = max_size_gb > 45
    is_indie_genre = any(m in genres_str.lower() for m in INDIE_MARKERS)
    
    tier = "Indie/AA"
    if (is_aaa_publisher or is_huge_game) and not is_indie_genre:
        tier = "AAA"
    
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
    path = os.path.join(dirs["products"], f"{safe_name(bid)}.json")
    
    if log_func: log_func(bid, "load product json")
    store_data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            full_json = json.load(f)
            if "product" in full_json:
                store_data = full_json["product"]
    except: return None

    if log_func: log_func(bid, "parse properties")
    props = store_data.get("Properties", {})
    lps = store_data.get("LocalizedProperties", [])
    
    lp_uk = next((x for x in lps if x.get("Language","").lower() in ("uk-ua", "uk")), {})
    lp_en = next((x for x in lps if x.get("Language","").lower() in ("en-us", "en")), {})
    
    if not lp_uk: lp_uk = lp_en
    if not lp_en: lp_en = lp_uk
    if not lp_uk and lps: lp_uk = lps[0]
    if not lp_en and lps: lp_en = lps[0]

    name = lp_uk.get("ProductTitle") or lp_en.get("ProductTitle") or props.get("ProductTitle") or f"UnknownID_{bid}"
    clean_name = name.replace("(PC)", "").replace("(Windows)", "").strip()
    clean_id = safe_name(clean_name)

    desc_store_uk = clean_text(lp_uk.get("ProductDescription") or lp_uk.get("ShortDescription") or "")
    desc_store_en = clean_text(lp_en.get("ProductDescription") or lp_en.get("ShortDescription") or desc_store_uk)

    if log_func: log_func(bid, "wiki check/cache")
    wiki_desc = "" # General result
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
                        wiki_url = wd_data.get('WikiUrl', '')
                        
                        # --- LOGIC FIX: Prefer UK, fallback to EN ---
                        wiki_desc = clean_text(wd_data.get('Description_UK', ''))
                        if not wiki_desc:
                            wiki_desc = clean_text(wd_data.get('Description', '')) # Зазвичай тут EN опис з Wikidata
    except: pass

    if log_func: log_func(bid, "hltb check/cache")
    hours = ""
    try:
        h_f = os.path.join(dirs["hltb"], f"{clean_id}.json")
        if os.path.exists(h_f):
            with open(h_f) as f: 
                h_val = json.load(f).get("hours", "0")
                if h_val != "0": hours = h_val
    except: pass

    if log_func: log_func(bid, "metrics")
    
    genres_list = extract_genres_from_product(props)
    genre_str = ", ".join(genres_list)
    
    tier, rating, rating_src = analyze_metrics(store_data, wd_data, genre_str)
    image_url = pick_best_image_uri(store_data, lp_uk)
    
    links = { "store": f"https://www.xbox.com/en-us/games/store/{bid}", "wiki": wiki_url }

    # Pass the unified wiki description
    html_uk = make_html_desc(desc_store_uk, wiki_desc, links, "uk")
    html_en = make_html_desc(desc_store_en, "", links, "en") # EN version

    display_genre = props.get("Category", "Unknown")
    if genres_list: display_genre = genres_list[0]

    year = extract_release_year(store_data, wd_data)

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