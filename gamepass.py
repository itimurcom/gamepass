#!/usr/bin/env python3
"""
PC Game Pass catalog dumper (EN/US only) - stdlib only

Output:
  .cache/            one raw Microsoft Store product JSON per game (ProductId.json)
  .cache/_meta/      meta files (SIGL dump etc.)
"""

from __future__ import annotations

import time
from pathlib import Path

from core.gp_config import Config, PC_GAMEPASS_SIGL
from core.gp_sigl import fetch_sigl_big_ids
from core.gp_terminal import (
    log_error,
    log_info,
    log_process,
    log_warn,
    progress_done,
    progress_update,
)
from core.core import chunked, ensure_dirs, fetch_products, write_json, write_product


def run(cfg: Config) -> None:
    meta_dir = ensure_dirs(cfg.out_dir)

    log_process(f"Start. Output directory: {cfg.out_dir.resolve()}")
    log_info(f"Market={cfg.market} Language={cfg.language} SIGL={cfg.sigl_id}")
    log_info(f"Meta directory: {meta_dir.resolve()}")

    # Phase: SIGL
    log_process("Phase: SIGL -> fetch list of bigIds for PC Game Pass")
    try:
        ids, sigl_meta = fetch_sigl_big_ids(cfg)
    except Exception as e:
        log_error(f"SIGL fetch failed: {e}")
        raise

    write_json(meta_dir / "sigl_US_en-us.json", sigl_meta)
    log_info(f"SIGL fetched. Unique bigIds: {len(ids)}. Saved: {meta_dir / 'sigl_US_en-us.json'}")

    if not ids:
        log_warn("No bigIds received. Nothing to do.")
        return

    ids_sorted = sorted(ids)
    batches = list(chunked(ids_sorted, cfg.batch_size))
    log_process(f"Phase: PRODUCTS -> fetch and dump products in {len(batches)} batches (batch_size={cfg.batch_size})")

    total_products = 0
    written_files = 0

    for idx, batch in enumerate(batches, start=1):
        log_process(f"Batch {idx}/{len(batches)}: fetching products for {len(batch)} bigIds")
        try:
            products = fetch_products(cfg, batch)
        except Exception as e:
            log_error(f"DisplayCatalog fetch failed on batch {idx}/{len(batches)}: {e}")
            raise

        total_products += len(products)

        batch_written = 0
        # Progress bar: writing files inside this batch
        for p_i, p in enumerate(products, start=1):
            progress_update(p_i, len(products), prefix=f"Writing batch {idx}/{len(batches)} ")
            if isinstance(p, dict):
                ok = write_product(cfg.out_dir, p)
                if ok:
                    batch_written += 1
                    written_files += 1
        progress_done(suffix="")

        log_info(f"Batch {idx}/{len(batches)}: fetched={len(products)} written={batch_written}")
        time.sleep(cfg.sleep_s)

    log_process("Phase: DONE")
    log_info(f"Summary: bigIds={len(ids_sorted)} products_fetched={total_products} files_written={written_files}")
    log_info("Finished successfully.")


def main() -> None:
    cfg = Config(
        market="US",
        language="en-us",
        out_dir=Path(".cache"),
        sigl_id=PC_GAMEPASS_SIGL,
        batch_size=100,
        sleep_s=0.2,
        timeout_s=30.0,
        retries=3,
    )
    run(cfg)


if __name__ == "__main__":
    main()
