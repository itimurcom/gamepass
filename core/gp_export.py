# core/gp_export.py
# Export helpers (HTML/CSV) extracted from gp_collector to keep responsibilities clean.

import os
import json
import csv

def save_html_report(rows, template_path, out_path):
    """
    Render a single self-contained HTML file using core/template.html.

    The template is expected to contain the placeholder:
        __DATASET_JSON__
    which will be replaced by a JSON array of rows.
    """
    if not os.path.exists(template_path):
        return False, "No template"

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            tmpl = f.read()

        dataset_json = json.dumps(rows, ensure_ascii=False)
        out = tmpl
        # Support both placeholders (template versions differ)
        out = out.replace("__DATASET_JSON__", dataset_json)
        out = out.replace("__DATA_JSON__", dataset_json)
        out = out.replace("__TITLE__", "Game Pass Catalog")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out)

        return True, "OK"
    except Exception as e:
        return False, str(e)

def save_csv_report(rows, out_path):
    """
    Export a lightweight CSV snapshot for debugging/analysis.
    """
    try:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "id", "name_uk", "name_en", "genres", "rating", "ratingSource",
                    "year", "hours", "publisher", "developer", "isAAA", "isIndie"
                ],
                extrasaction="ignore"
            )
            w.writeheader()

            for r in rows:
                i18n = r.get("i18n", {})
                uk = i18n.get("uk", {})
                en = i18n.get("en", {})

                genres = r.get("genres") or []
                if isinstance(genres, list):
                    genres_csv = ", ".join([str(x) for x in genres if x])
                else:
                    genres_csv = str(genres)

                w.writerow({
                    "id": r.get("id", ""),
                    "name_uk": uk.get("name", ""),
                    "name_en": en.get("name", ""),
                    "genres": genres_csv,
                    "rating": r.get("rating", ""),
                    "ratingSource": r.get("ratingSource", ""),
                    "year": r.get("year", ""),
                    "hours": r.get("hours", ""),
                    "publisher": r.get("publisher", ""),
                    "developer": r.get("developer", ""),
                    "isAAA": r.get("isAAA", False),
                    "isIndie": r.get("isIndie", False),
                })

        return True, "OK"
    except Exception as e:
        return False, str(e)