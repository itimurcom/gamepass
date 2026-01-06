# gp_logic.py
# Логіка обробки даних, аналіз рейтингів та робота з файлами.

import os
import json
import re

# --- КОНСТАНТИ ---
AAA_PUBLISHERS = [
    "xbox game studios", "bethesda", "electronic arts", "ea", "ubisoft", 
    "activision", "blizzard", "rockstar", "2k", "capcom", "square enix", 
    "bandai namco", "sega", "wb games", "sony", "cd projekt", "take-two"
]

# --- УТИЛІТИ ---
def safe_name(s):
    """Очищує рядок для використання в імені файлу."""
    return "".join(c for c in (s or "").lower() if c.isalnum() or c in "-_")[:180] or "x"

def rw_json(path, data=None):
    """
    Читає або пише JSON. 
    Повертає вміст файлу при читанні.
    Повертає None, якщо файл не існує або пошкоджений.
    """
    if data is None: # Read
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if not content: return None 
                    return content
            except (json.JSONDecodeError, OSError):
                return None # Файл пошкоджено
        return None
    else: # Write
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f: 
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            print(f"[ERROR] Не вдалося записати {path}: {e}")

# --- БІЗНЕС-ЛОГІКА ---

def analyze_metrics(product_raw, wikidata_data):
    """
    Визначає Tier гри (AAA/Indie) та розраховує 'Розумний рейтинг' (0-100).
    Використовує байєсівське наближення для балансу між кількістю голосів та оцінкою.
    """
    props = product_raw.get("Properties", {})
    market_props = product_raw.get("MarketProperties", [])
    
    # 1. ВИЗНАЧЕННЯ TIER (AAA vs AA/Indie)
    lps = product_raw.get("LocalizedProperties", [])
    # Шукаємо хоч якусь назву видавця, бажано англійською або українською
    lp = next((x for x in lps if x.get("Language","").lower() in ["en-us", "uk-ua"]), lps[0] if lps else {})
    publisher = (lp.get("PublisherName") or props.get("PublisherName") or "").lower()
    
    # Перевірка розміру (якщо > 40 ГБ - ймовірно, велика гра)
    max_size_gb = 0
    if product_raw.get("DisplaySkuAvailabilities"):
        for sku_avail in product_raw["DisplaySkuAvailabilities"]:
            pkg = sku_avail.get("Sku", {}).get("Properties", {}).get("Packages", [])
            if pkg:
                size_bytes = pkg[0].get("MaxDownloadFileSizeInBytes", 0)
                max_size_gb = max(max_size_gb, size_bytes / (1024**3))

    is_aaa_publisher = any(p in publisher for p in AAA_PUBLISHERS)
    is_huge_game = max_size_gb > 40
    
    tier = "AAA" if (is_aaa_publisher or is_huge_game) else "Indie/AA"
    
    # 2. РОЗРАХУНОК РЕЙТИНГУ (Smart Score)
    ms_score = 0
    ms_count = 0
    
    # Рейтинг з Microsoft Store
    for mp in market_props:
        usage = mp.get("UsageData", [])
        for u in usage:
            if u.get("AggregateTimeSpan") == "AllTime":
                ms_score = u.get("AverageRating", 0) # 0..5
                ms_count = u.get("RatingCount", 0)
                break
        if ms_count > 0: break
    
    # Рейтинг з Wikidata
    wd_score_raw = wikidata_data.get("Rating", 0)
    wd_score = 0
    try:
        wd_val = float(str(wd_score_raw).split("/")[0])
        # Нормалізація до 100
        if wd_val <= 5: wd_score = wd_val * 20
        elif wd_val <= 10: wd_score = wd_val * 10
        else: wd_score = wd_val
    except: pass

    final_score = 0
    
    if ms_count > 0:
        # Формула: (v / (v+m)) * R + (m / (v+m)) * C
        # Де C=75 (середнє), m=50 (поріг довіри)
        R = ms_score * 20
        v = ms_count
        m = 50 
        C = 75 
        final_score = (v / (v + m)) * R + (m / (v + m)) * C
    elif wd_score > 0:
        final_score = wd_score
    
    score_src = f"{ms_count} (Xbox)" if ms_count else ("Wiki" if wd_score > 0 else "")
    
    return tier, round(final_score, 1), score_src

def get_product_data(bid, dirs, lang):
    """
    Збирає повну інформацію про гру з кешованих файлів.
    :param bid: BigID гри
    :param dirs: словник шляхів до папок (dirs['products'], dirs['wikidata']...)
    :param lang: мова даних (uk-ua)
    """
    path = os.path.join(dirs["products"], f"{safe_name(bid)}.json")
    cache = rw_json(path)
    
    if not cache or "product" not in cache: 
        return None 
        
    p = cache["product"]
    lps = p.get("LocalizedProperties", [])
    lp = next((x for x in lps if x.get("Language","").lower() == lang), lps[0] if lps else {})
    props = p.get("Properties", {})
    
    # Зображення
    imgs = lp.get("Images", [])
    if not imgs and p.get("DisplaySkuAvailabilities"):
        skus = p.get("DisplaySkuAvailabilities")[0].get("Sku", {}).get("LocalizedProperties", [])
        if skus: imgs = skus[0].get("Images", [])
        
    img_url = next((i.get("Uri") for i in imgs if i.get("ImagePurpose") in ["Poster", "BoxArt"]), imgs[0].get("Uri") if imgs else "")
    if img_url and img_url.startswith("//"): img_url = "https:" + img_url

    name = lp.get("ProductTitle") or p.get("ProductTitle") or ""
    if not name: return None

    # Очистка назви для пошуку додаткових даних
    search_name = name.replace("(Game Preview)", "").replace("(PC)", "").strip()

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

    # Жанри (Пріоритет: Wikidata -> Store Category -> Пусто)
    genre_final = wd_data.get("Genres_UK")
    if not genre_final:
        store_cat = props.get("Category", "")
        if store_cat and str(store_cat).lower() not in ["game", "gaming", "application"]:
            genre_final = store_cat

    # Аналіз метрик (Tier + Rating)
    tier, score, score_src = analyze_metrics(p, wd_data)

    return {
        "id": bid,
        "name": name,
        "genre": genre_final or "",
        "description": wd_data.get("Description_UK") or lp.get("ShortDescription",""),
        "tier": tier,
        "rating": score,
        "ratingSource": score_src,
        "year": wd_data.get("Year_WD") or (props.get("OriginalReleaseDate") or "")[:4],
        "hours": hours,
        "publisher": lp.get("PublisherName",""),
        "developer": lp.get("DeveloperName",""),
        "wikipedia": wd_data.get("WikipediaUrl",""),
        "wikidata": wd_data.get("WikidataUrl",""),
        "image": img_url
    }