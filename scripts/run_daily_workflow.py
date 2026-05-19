from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.daily_workflow import DailyWorkflowConfig, run_daily_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily workflow: catalog refresh -> market ingestion -> daily review.")
    parser.add_argument("--base-url", default="", help="Defaults to STALCRAFTDB_BASE_URL.")
    parser.add_argument("--region", default="eu")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    parser.add_argument("--limit", type=int, default=0, help="Optional item limit for test runs. 0 = no limit.")
    parser.add_argument("--artifact-only", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    parser.add_argument("--skip-ingestion", action="store_true")
    parser.add_argument("--skip-review", action="store_true")
    parser.add_argument("--review-deal-pct", type=float, default=-25.0)
    parser.add_argument("--review-limit", type=int, default=250)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore saved ingestion checkpoint and start batches from the beginning.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not resume from checkpoint (still writes progress for crash recovery).",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    result = run_daily_workflow(
        project_root=PROJECT_ROOT,
        base_url=args.base_url,
        config=DailyWorkflowConfig(
            region=args.region,
            timeout_seconds=max(3, int(args.timeout_seconds)),
            batch_size=max(1, int(args.batch_size)),
            sleep_seconds=max(0.0, float(args.sleep_seconds)),
            limit=max(0, int(args.limit)),
            artifact_only=bool(args.artifact_only),
            refresh_catalog=not bool(args.skip_catalog),
            run_ingestion=not bool(args.skip_ingestion),
            run_review=not bool(args.skip_review),
            review_deal_pct=float(args.review_deal_pct),
            review_limit=max(1, int(args.review_limit)),
            resume_from_checkpoint=not bool(args.no_resume),
            fresh_run=bool(args.fresh),
        ),
    )
    review_summary = (
        "none"
        if result.review is None
        else (
            f"id={result.review.review_id} scanned={result.review.scanned_items} "
            f"found={result.review.deals_found} saved={result.review.deals_saved}"
        )
    )
    logging.info(
        "Daily workflow complete: catalog_items=%s catalog_changed=%s ingestion_items=%s "
        "batches=%s failures=%s review=%s",
        result.catalog_items,
        result.catalog_changed,
        result.ingestion_items,
        result.ingestion_batches,
        result.ingestion_failures,
        review_summary,
    )
    return 1 if result.ingestion_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
