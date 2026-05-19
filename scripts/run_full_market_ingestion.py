from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.core.pipeline import ingest_items
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape market data for ids from item_catalog in safe batches.")
    parser.add_argument("--batch-size", type=int, default=25, help="Items per ingestion batch.")
    parser.add_argument("--sleep-seconds", type=float, default=1.5, help="Delay between batches.")
    parser.add_argument("--limit", type=int, default=0, help="Optional item limit for test runs. 0 = no limit.")
    parser.add_argument("--artifact-only", action="store_true", help="Only scrape item_catalog rows marked as artifacts.")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--base-url", default="", help="Defaults to STALCRAFTDB_BASE_URL.")
    parser.add_argument("--region", default="", help="Defaults to eu.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    app_cfg = load_config(project_root=PROJECT_ROOT)

    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    catalog = repo.get_catalog_items(artifact_only=bool(args.artifact_only), limit=50_000)
    item_ids = [str(row["item_id"]) for row in catalog if str(row.get("item_id", "")).strip()]
    if args.limit and int(args.limit) > 0:
        item_ids = item_ids[: int(args.limit)]

    if not item_ids:
        logging.error("item_catalog is empty. Run scripts/refresh_item_catalog.py first.")
        return 1

    batch_size = max(1, int(args.batch_size))
    total_batches = (len(item_ids) + batch_size - 1) // batch_size
    logging.info("Full market ingestion: items=%s batch_size=%s batches=%s", len(item_ids), batch_size, total_batches)

    failures = 0
    for idx in range(0, len(item_ids), batch_size):
        batch_no = (idx // batch_size) + 1
        batch = item_ids[idx : idx + batch_size]
        logging.info("Ingesting batch %s/%s (items=%s)", batch_no, total_batches, len(batch))
        rc = ingest_items(
            project_root=PROJECT_ROOT,
            items_csv=",".join(batch),
            timeout_seconds=max(3, int(args.timeout_seconds)),
            base_url=args.base_url.strip() or app_cfg.base_url,
            region=args.region.strip() or "eu",
            print_records=False,
        )
        if rc != 0:
            failures += 1
            logging.error("Batch %s/%s failed with rc=%s", batch_no, total_batches, rc)
        if batch_no < total_batches:
            time.sleep(max(0.0, float(args.sleep_seconds)))

    logging.info("Full market ingestion finished: batches=%s failures=%s", total_batches, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
