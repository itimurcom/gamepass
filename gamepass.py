#!/usr/bin/env python3
"""
PC Game Pass catalog dumper (stdlib only)

Output layout (multi-language):
  .cache/UA/         uk-UA market UA
  .cache/EN/         en-US market US
Each language directory contains:
  <ProductId>.json
  _meta/            meta files
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from core.gp_config import Config, LANGUAGES, PC_GAMEPASS_SIGL
from core.gp_sigl import fetch_sigl_big_ids
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
from core.core import chunked, ensure_dirs, fetch_products, write_json, write_product

PROJECT_TITLE_WITH_VERSION = "Gamepass Parser v15.4"


def run_one_language(cfg: Config, *, lang_code: str) -> None:
    """
    Runs the staged pipeline for a single language directory (cfg.out_dir).
    """
    meta_dir = ensure_dirs(cfg.out_dir)

    # ----------------
    # Stage 1: SIGL
    # ----------------
    stage_no = 1
    print_stage(stage_no, f"[{lang_code}] Fetch PC Game Pass catalog ids (SIGL)")

    progress_update(0, 1, text=f"[{lang_code}] Requesting SIGL list...")
    try:
        ids, sigl_meta = fetch_sigl_big_ids(cfg)
    except Exception as e:
        progress_done(final_text=f"[{lang_code}] SIGL request failed")
        log_error(f"[{lang_code}] SIGL fetch failed: {e}")
        raise
    progress_update(1, 1, text=f"[{lang_code}] SIGL list received")
    progress_done()

    sigl_name = f"sigl_{cfg.market}_{cfg.language}.json"
    sigl_path = meta_dir / sigl_name
    write_json(sigl_path, sigl_meta)

    if not ids:
        print_stage_result(stage_no, f"[{lang_code}] 0 ids received (nothing to do)")
        log_warn(f"[{lang_code}] No bigIds received. Nothing to do.")
        return

    print_stage_result(stage_no, f"[{lang_code}] {len(ids)} ids saved to {sigl_path}")

    # ----------------
    # Stage 2: Fetch+Write products (batched)
    # ----------------
    stage_no = 2
    print_stage(stage_no, f"[{lang_code}] Fetch product details and write JSON files")

    ids_sorted = sorted(ids)
    batches = list(chunked(ids_sorted, cfg.batch_size))
    total_steps = len(batches) * 2  # fetch + write per batch
    step = 0

    products_fetched = 0
    files_written = 0

    for idx, batch in enumerate(batches, start=1):
        # Step: fetch
        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] Fetching batch {idx}/{len(batches)} ({len(batch)} ids)")
        try:
            products = fetch_products(cfg, batch)
        except Exception as e:
            progress_done(final_text=f"[{lang_code}] Batch {idx} fetch failed")
            log_error(f"[{lang_code}] DisplayCatalog fetch failed on batch {idx}/{len(batches)}: {e}")
            raise

        products_fetched += len(products)

        # Step: write
        step += 1
        progress_update(step, total_steps, text=f"[{lang_code}] Writing batch {idx}/{len(batches)} ({len(products)} products)")
        for p in products:
            if isinstance(p, dict):
                ok = write_product(cfg.out_dir, p)
                if ok:
                    files_written += 1

        time.sleep(cfg.sleep_s)

    progress_done(final_text=f"[{lang_code}] Batches processed")

    print_stage_result(stage_no, f"[{lang_code}] products_fetched={products_fetched}, files_written={files_written}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dump PC Game Pass catalog into .cache/<LANG>/ (stdlib only).")
    p.add_argument("--reset-cache", action="store_true", help="Delete .cache directory before parsing.")
    p.add_argument("--cache-dir", default=".cache", help="Cache root directory (default: .cache)")
    p.add_argument("--batch", type=int, default=100, help="Batch size for bigIds (default: 100)")
    p.add_argument("--sleep", type=float, default=0.2, help="Sleep between requests in seconds (default: 0.2)")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30)")
    p.add_argument("--retries", type=int, default=3, help="Retries for transient errors (default: 3)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    cache_root = Path(args.cache_dir)

    print_project(PROJECT_TITLE_WITH_VERSION)
    log_info(f"Cache root: {cache_root}")
    log_info("Languages: " + ", ".join([f"{lp.code}({lp.language}/{lp.market})" for lp in LANGUAGES]))

    # Stage 0: reset-cache (optional)
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

    # Run for each language profile
    for i, lp in enumerate(LANGUAGES, start=1):
        out_dir = cache_root / lp.code
        cfg = Config(
            market=lp.market,
            language=lp.language,
            out_dir=out_dir,
            sigl_id=PC_GAMEPASS_SIGL,
            batch_size=args.batch,
            sleep_s=args.sleep,
            timeout_s=args.timeout,
            retries=args.retries,
        )

        log_info(f"Language {lp.code}: output -> {out_dir}")
        run_one_language(cfg, lang_code=lp.code)

    print_overall_result(f"Done. Cache root: {cache_root}")


if __name__ == "__main__":
    main()
