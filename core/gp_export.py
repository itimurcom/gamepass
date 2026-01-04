# core/gp_export.py
# Версія: 11.8 (Data Only Mode)

import os
import json
import csv

# --- ASSETS ---
NO_COVER_IMAGE = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMzAwIiB2aWV3Qm94PSIwIDAgMjAwIDMwMCI+PHJlY3Qgd2lkdGg9IjIwMCIgaGVpZ2h0PSIzMDAiIGZpbGw9IiMyYzJjMmUiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZm9udC1mYW1pbHk9InNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjAiIGZpbGw9IiM4NjhlOGIiPk5PIElNQUdFPC90ZXh0Pjwvc3ZnPg=="

def export_data_js(rows, output_dir):
    """
    Генерує ТІЛЬКИ файл даних data.js у вказаній папці.
    Не чіпає HTML файли.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 1. Підготовка даних (Image Fallback)
    # Ми модифікуємо rows in-place або копіюємо, тут це безпечно
    for r in rows:
        if not r.get("image"):
            r["image"] = NO_COVER_IMAGE
            r["no_avatar"] = True
        else:
            r["no_avatar"] = False

    # 2. Запис даних у JS файл
    data_js_path = os.path.join(output_dir, "data.js")
    try:
        json_str = json.dumps(rows, ensure_ascii=False)
        with open(data_js_path, "w", encoding="utf-8") as f:
            f.write(f"window.GP_DATA = {json_str};")
        return True, "Updated data.js"
    except Exception as e:
        return False, f"Error writing data.js: {e}"

def save_csv_report(rows, out_path):
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        def _clean(t):
            if not t: return ""
            return str(t).replace("\n", " ").replace("\r", "")

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id","name","rating","hours","year","desc_preview"], extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({
                    "id": r["id"],
                    "name": r["i18n"]["uk"]["name"],
                    "rating": r["rating"],
                    "hours": r["hours"],
                    "year": r["year"],
                    "desc_preview": _clean(r["i18n"]["uk"]["desc"])[:200]
                })
        return True, "OK"
    except Exception as e: return False, str(e)