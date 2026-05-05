from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.ingestion.scraper import ScraperConfig, StalcraftPriceScraper
from stalcraft_market_analyzer.ingestion.exporter import build_quality_report, write_raw_snapshot
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stalcraft market ingestion.")
    parser.add_argument(
        "--items",
        required=True,
        help="Comma-separated item ids, example: ak-103,veteran-armor",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=15,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Base URL of StalcraftDB (overrides STALCRAFTDB_BASE_URL)",
    )
    parser.add_argument(
        "--region",
        default="",
        help="Region code (overrides STALCRAFT_REGION), example: eu",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    item_ids = [value.strip() for value in args.items.split(",") if value.strip()]
    if not item_ids:
        logging.error("No valid item ids were provided.")
        return 1

    app_cfg = load_config(project_root=PROJECT_ROOT)
    base_url = args.base_url.strip() or app_cfg.base_url
    region = args.region.strip() or "eu"

    scraper = StalcraftPriceScraper(
        config=ScraperConfig(
            base_url=base_url,
            region=region,
            timeout_seconds=args.timeout_seconds,
        )
    )
    records = scraper.fetch_prices(item_ids=item_ids)
    snapshot_result = write_raw_snapshot(records=records, output_dir=app_cfg.raw_output_dir)
    quality_report = build_quality_report(records=records)
    batch = build_ingestion_batch(snapshot_id=snapshot_result.snapshot_id, records=records)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    inserted = repo.save_ingestion_batch(batch)

    for record in records:
        print(record)
    logging.info("Ingestion finished. Records fetched: %s", len(records))
    logging.info("Raw snapshot saved to: %s", snapshot_result.output_path)
    logging.info(
        "Data quality report => total=%s api=%s html=%s mock=%s",
        quality_report.total_records,
        quality_report.json_api_records,
        quality_report.html_table_records,
        quality_report.mock_js_fallback_records,
    )
    logging.info("Repository batch contract ready with %s records.", len(batch.records))
    logging.info("Inserted into DB: %s", inserted)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
