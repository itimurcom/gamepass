#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Set

from core.gp_config import Config, LANGUAGES, SIGL_LISTS
from core.gp_sigl import fetch_sigl_ids
from core.gp_terminal import (
    log_error,
    log_info,
    log_warn,
    print_overall_result,
    print_project,
    print_stage,
    print_stage_result,
    progress_done,
    progress_update,
)
from core.core import chunked, ensure_dirs, export_catalog_data_js, fetch_products, write_json, write_product

PROJECT_TITLE_WITH_VERSION = "Gamepass Parser v16.2"


def _load_cached_list_items(list_path: Path) -> list[str] | None:
    if not list_path.exists() or not list_path.is_file():
        return None
    try:
        obj = json.loads(list_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        return [x for x in obj["items"] if isinstance(x, str) and x]
    return None


def _get_cached_product_ids(language_out_dir: Path) -> Set[str]:
    """Cached products are stored as: .cache/<LANG>/<ProductId>.json"""
    ids: Set[str] = set()
    if not language_out_dir.exists():
        return ids

    for p in language_out_dir.glob("*.json"):
        if not p.is_file():
            continue
        stem = p.stem
        if stem:
            ids.add(stem)
    return ids


def run_one_language(cfg: Config, *, lang_code: str) -> None:
    out_dir = Path(cfg.out_dir)
    ensure_dirs(out_dir)
    lists_dir = out_dir / "_lists"
    lists_dir.mkdir(parents=True, exist_ok=True)

    stage_no = 1
    print_stage(stage_no, f"[{lang_code}] SIGL v2 lists (use cache; fetch only missing)")

    all_ids: Set[str] = set()
    total_steps = max(1, len(SIGL_LISTS)) * 2
    step = 0
    list_fetched = 0
    list_cached = 0

    for idx, lst in enumerate(SIGL_LISTS, start=1):
        list_path = lists_dir / f"{lst.key}.json"

        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] SIGL {idx}/{len(SIGL_LISTS)}: {lst.key} (load cache)")
        cached_items = _load_cached_list_items(list_path)
        if cached_items is not None:
            for x in cached_items:
                all_ids.add(x)
            step += 1
            progress_update(step, total_steps, text=f"[{lang_code}] SIGL {idx}/{len(SIGL_LISTS)}: {lst.key} (cached)")
            list_cached += 1
            continue

        # Cache miss -> fetch from network
        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] SIGL {idx}/{len(SIGL_LISTS)}: {lst.key} (fetch ids)")
        try:
            ids, meta = fetch_sigl_ids(cfg, sigl_id=lst.sigl_id)
        except Exception as e:
            progress_done(final_text=f"[{lang_code}] SIGL fetch failed")
            log_error(f"[{lang_code}] SIGL list '{lst.key}' failed: {e}")
            raise

        ids_clean = sorted({x for x in ids if isinstance(x, str) and x})
        for x in ids_clean:
            all_ids.add(x)

        write_json(
            list_path,
            {
                "key": lst.key,
                "title": lst.title,
                "group": lst.group,
                "sigl_id": lst.sigl_id,
                "market": cfg.market,
                "language": cfg.language,
                "items": ids_clean,
                "_meta": meta,
            },
        )
        list_fetched += 1
        time.sleep(cfg.sleep_s)

    progress_done(final_text=f"[{lang_code}] Lists ready")
    print_stage_result(
        stage_no,
        f"[{lang_code}] lists_cached={list_cached}, lists_fetched={list_fetched}, unique_product_ids={len(all_ids)}",
    )

    stage_no = 2
    print_stage(stage_no, f"[{lang_code}] Products (use cache; fetch only missing)")

    ids_sorted = sorted(all_ids)
    if not ids_sorted:
        print_stage_result(stage_no, f"[{lang_code}] 0 ids after lists (nothing to fetch)")
        log_warn(f"[{lang_code}] No ids found across lists. Nothing to fetch.")
        return

    cached_ids = _get_cached_product_ids(out_dir)
    missing_ids = sorted([x for x in ids_sorted if x not in cached_ids])

    if not missing_ids:
        print_stage_result(stage_no, f"[{lang_code}] All products already cached ({len(cached_ids)}) - skipped network")
        return

    batches = list(chunked(missing_ids, cfg.batch_size))
    total_steps = len(batches) * 2
    step = 0
    products_fetched = 0
    files_written = 0

    for bidx, batch in enumerate(batches, start=1):
        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] Fetch batch {bidx}/{len(batches)} ({len(batch)} missing ids)")
        try:
            products = fetch_products(cfg, batch)
        except Exception as e:
            progress_done(final_text=f"[{lang_code}] Batch {bidx} fetch failed")
            log_error(f"[{lang_code}] DisplayCatalog fetch failed on batch {bidx}/{len(batches)}: {e}")
            raise

        products_fetched += len(products)

        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] Write batch {bidx}/{len(batches)} ({len(products)} products)")
        for p in products:
            if isinstance(p, dict) and write_product(out_dir, p):
                files_written += 1

        time.sleep(cfg.sleep_s)

    progress_done(final_text=f"[{lang_code}] Products cached")
    print_stage_result(
        stage_no,
        f"[{lang_code}] cached_before={len(cached_ids)}, missing_before={len(missing_ids)}, products_fetched={products_fetched}, product_files_written={files_written}",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dump PC Game Pass catalog into .cache/<LANG>/ using SIGL v2 lists (stdlib only).")
    p.add_argument("--reset-cache", action="store_true", help="Delete .cache directory before parsing.")
    p.add_argument("--cache-dir", default=".cache", help="Cache root directory (default: .cache)")
    p.add_argument("--export-js", default="catalog/data.js", help="Export JS file path (default: catalog/data.js)")
    p.add_argument("--batch", type=int, default=100, help="Batch size for bigIds (default: 100)")
    p.add_argument("--sleep", type=float, default=0.2, help="Sleep between requests in seconds (default: 0.2)")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30)")
    p.add_argument("--retries", type=int, default=3, help="Retries for transient errors (default: 3)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    cache_root = Path(args.cache_dir)
    export_path = Path(args.export_js)

    print_project(PROJECT_TITLE_WITH_VERSION)
    log_info(f"Cache root: {cache_root}")
    log_info("Languages: " + ", ".join([f"{lp.code}({lp.language}/{lp.market})" for lp in LANGUAGES]))
    log_info(f"SIGL lists: {len(SIGL_LISTS)}")
    log_info(f"Export: {export_path}")

    if args.reset_cache:
        print_stage(0, "Reset cache")
        if cache_root.exists():
            progress_update(0, 1, text=f"Deleting {cache_root} ...")
            try:
                shutil.rmtree(cache_root)
            except Exception as e:
                progress_done(final_text="Cache delete failed")
                log_error(f"Failed to delete cache directory '{cache_root}': {e}")
                raise
            progress_update(1, 1, text="Deleted")
            progress_done()
            print_stage_result(0, f"Deleted {cache_root}")
        else:
            progress_update(1, 1, text="Nothing to delete")
            progress_done()
            print_stage_result(0, f"{cache_root} does not exist")

    for lp in LANGUAGES:
        out_dir = cache_root / lp.code
        cfg = Config(
            market=lp.market,
            language=lp.language,
            out_dir=out_dir,
            batch_size=args.batch,
            sleep_s=args.sleep,
            timeout_s=args.timeout,
            retries=args.retries,
        )
        log_info(f"Language {lp.code}: output -> {out_dir}")
        run_one_language(cfg, lang_code=lp.code)

    print_stage(3, "Export catalog/data.js for SPA")
    progress_update(0, 1, text="Building JS export...")
    counts = export_catalog_data_js(cache_root=cache_root, out_path=export_path)
    progress_update(1, 1, text="Export complete")
    progress_done()

    print_stage_result(3, f"Exported {export_path} (EN={counts.get('EN',0)}, UA={counts.get('UA',0)})")
    print_overall_result(f"Done. Cache root: {cache_root}. Export: {export_path}")


if __name__ == "__main__":
    main()
