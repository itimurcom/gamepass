# gp_logic.py
# Логіка: Dual-Language Extraction + Smart Metrics

import os
import json
import re

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

def rw_json(path, data=None):
    if data is None: # Read
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if not content: return None 
                    return content
            except (json.JSONDecodeError, OSError):
                return None
        return None
    else: # Write
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f: 
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            print(f"[ERROR] Не вдалося записати {path}: {e}")

def clean_html(txt):
    if not txt: return ""
    return re.sub(r'<[^>]+>', '', txt).strip()

# --- БІЗНЕС-ЛОГІКА ---

def analyze_metrics(product_raw, wikidata_data, genres_str):
    """Визначає Tier та Рейтинг."""
    props = product_raw.get("Properties", {})
    market_props = product_raw.get("MarketProperties", [])
    
    # Видавець (беремо англійську назву як універсальну)
    lps = product_raw.get("LocalizedProperties", [])
    lp_en = next((x for x in lps if x.get("Language","").lower() == "en-us"), lps[0] if lps else {})
    publisher = (lp_en.get("PublisherName") or props.get("PublisherName") or "").lower()
    
    # Розмір
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

def get_product_data(bid, dirs, lang_pref="uk-ua"):
    path = os.path.join(dirs["products"], f"{safe_name(bid)}.json")
    cache = rw_json(path)
    if not cache or "product" not in cache: return None 
        
    p = cache["product"]
    props = p.get("Properties", {})
    lps = p.get("LocalizedProperties", [])
    
    # --- DUAL LANGUAGE EXTRACTION (patched) ---
    name_uk, name_en, lp_uk, lp_en, lp_main = pick_best_titles(lps, props, bid)

    
    # Назви
    name_uk = lp_uk.get("ProductTitle") or lp_en.get("ProductTitle") or p.get("ProductTitle") or ""
    name_en = lp_en.get("ProductTitle") or name_uk
    
    # Описи (Store)
    desc_uk = clean_html(lp_uk.get("ShortDescription") or lp_uk.get("ProductDescription") or "")
    desc_en = clean_html(lp_en.get("ShortDescription") or lp_en.get("ProductDescription") or "")
    
    if not name_uk: return None
    # Картинка (patched)
    img_url = pick_best_image_uri(p, lp_main)


    # Пошук в кешах (Wiki/HLTB) робимо за очищеною назвою
    search_name = name_en.replace("(Game Preview)", "").replace("(PC)", "").strip()

    # Wikidata
    wd_cache_name = rw_json(os.path.join(dirs["wikidata"], f"{safe_name(search_name)}.json"))
    qid = wd_cache_name.get("qid") if wd_cache_name else None
    wd_data = {}
    if qid:
        wd_raw = rw_json(os.path.join(dirs["wd_sparql"], f"{safe_name(qid)}.json"))
        if wd_raw and "data" in wd_raw: wd_data = wd_raw["data"]

    # HLTB
    hltb_raw = rw_json(os.path.join(dirs["hltb"], f"{safe_name(search_name)}.json"))
    hours = hltb_raw.get("hours","") if hltb_raw else ""
    # Жанри (patched)
    genres = extract_genres_from_product(props)
    genre_uk = wd_data.get("Genres_UK") or (genres[0] if genres else "")

            
    # Аналіз
    tier, score, score_src = analyze_metrics(p, wd_data, genre_uk or "")

    # Описи для модального вікна
    # Формуємо об'єкт для фронтенду
    
    return {
        "id": bid,
        "tier": tier,
        "rating": score,
        "ratingSource": score_src,
        "year": wd_data.get("Year_WD") or (props.get("OriginalReleaseDate") or "")[:4],
        "hours": hours,
        "publisher": lp_en.get("PublisherName") or props.get("PublisherName") or "",
        "developer": lp_en.get("DeveloperName") or lp_uk.get("DeveloperName") or "",
        "image": img_url,
        
        # I18N Data Blocks
        "i18n": {
            "uk": {
                "name": name_uk,
                "genre": genre_uk or "Невідомо",
                "desc": wd_data.get("Description_UK") or desc_uk or "Опис відсутній."
            },
            "en": {
                "name": name_en,
                "genre": props.get("Category", "Unknown"), # Тут можна покращити, якщо парсити WD англійською
                "desc": desc_en or "Description not available."
            }
        },
        
        # Посилання
        "links": {
            "wiki": wd_data.get("WikipediaUrl") or wd_data.get("WikidataUrl"),
            "store": f"https://www.xbox.com/uk-ua/games/store/-/{bid}"
        }
    }

# --- PATCH: robust genre/image/name extraction (2026-01-04) ---

def _is_str(x):
    return isinstance(x, str)

def _clean_str(s: str) -> str:
    return (s or "").strip()

def extract_genres_from_product(props: dict) -> list:
    """Return list of genre/category strings only (exclude capability dicts)."""
    out = []
    # Common fields in DisplayCatalog
    candidates = []
    for key in ("Categories", "Category", "Subcategory", "Genres", "Genre"):
        v = props.get(key)
        if isinstance(v, list):
            candidates.extend(v)
        elif _is_str(v) and v:
            candidates.append(v)
    # Filter
    for g in candidates:
        if not _is_str(g):
            continue
        g = _clean_str(g)
        if not g:
            continue
        # exclude serialized dicts or technical markers
        if g.startswith("{") or g.startswith("['") or g.lower() in ("game", "gaming", "application"):
            continue
        if g not in out:
            out.append(g)
    return out

def pick_best_image_uri(p: dict, lp_main: dict) -> str:
    """Pick best image url from product/sku localized props."""
    priority = [
        "Poster", "BoxArt", "BrandedKeyArt", "KeyArt", "SuperHeroArt", "Hero",
        "TitledHeroArt", "FeaturePromotionalSquareArt", "Tile", "Logo", "Screenshot"
    ]
    imgs = []
    # 1) LocalizedProperties[*].Images
    if isinstance(lp_main, dict):
        imgs = lp_main.get("Images") or []
    # 2) SKU localized props images
    if (not imgs) and p.get("DisplaySkuAvailabilities"):
        try:
            skus = p["DisplaySkuAvailabilities"][0].get("Sku", {}).get("LocalizedProperties", [])
            if skus:
                imgs = skus[0].get("Images") or []
        except Exception:
            pass
    # 3) MarketProperties images (sometimes)
    if (not imgs) and p.get("MarketProperties"):
        try:
            imgs = p["MarketProperties"][0].get("Images") or []
        except Exception:
            pass

    def _purpose(img: dict) -> str:
        return (img.get("ImagePurpose") or img.get("Purpose") or img.get("ImageType") or "").strip()

    uri = ""
    if isinstance(imgs, list) and imgs:
        # Try by purpose priority
        for pur in priority:
            for img in imgs:
                if not isinstance(img, dict):
                    continue
                if _purpose(img) == pur and img.get("Uri"):
                    uri = img["Uri"]
                    break
            if uri:
                break
        # Fallback first valid Uri
        if not uri:
            for img in imgs:
                if isinstance(img, dict) and img.get("Uri"):
                    uri = img["Uri"]
                    break
    if uri and uri.startswith("//"):
        uri = "https:" + uri
    return uri

def pick_best_titles(lps: list, props: dict, bid: str) -> tuple:
    """Return (uk_title, en_title, lp_main) with safe fallbacks."""
    lp_uk = next((x for x in lps if (x.get("Language","").lower() == "uk-ua")), {}) if isinstance(lps, list) else {}
    lp_en = next((x for x in lps if (x.get("Language","").lower() == "en-us")), {}) if isinstance(lps, list) else {}
    lp_main = lp_uk or lp_en or (lps[0] if isinstance(lps, list) and lps else {})
    def _title(lp):
        if not isinstance(lp, dict): return ""
        return lp.get("ProductTitle") or lp.get("Title") or ""
    name_uk = _clean_str(_title(lp_uk))
    name_en = _clean_str(_title(lp_en))
    # extra fallbacks
    if not name_en:
        name_en = _clean_str(_title(lp_main))
    if not name_uk:
        name_uk = name_en
    if not name_en:
        # sometimes in Properties
        name_en = _clean_str(props.get("ProductTitle") or props.get("Title") or "")
    if not name_uk:
        name_uk = name_en
    if not name_uk:
        name_uk = f"UnknownID_{bid}"
    if not name_en:
        name_en = name_uk
    return name_uk, name_en, lp_uk, lp_en, lp_main
