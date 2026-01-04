# core/gp_export.py
# Версія: 11.13 (Clean Data Export)

import os
import json
import csv

def export_data_js(rows, output_dir):
    """
    Генерує чистий файл даних data.js.
    Картинки-заглушки тепер обробляються на стороні HTML/CSS.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # Підготовка даних: просто ставимо прапорець, якщо картинки немає
    for r in rows:
        if not r.get("image"):
            r["image"] = ""     # Порожній рядок, щоб зекономити місце
            r["no_avatar"] = True
        else:
            r["no_avatar"] = False

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