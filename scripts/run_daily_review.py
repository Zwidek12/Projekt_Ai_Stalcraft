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

from stalcraft_market_analyzer.analysis.daily_review import DailyReviewConfig, run_daily_market_review
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily market review and persist hot deal candidates.")
    parser.add_argument("--recent-days", type=int, default=30, help="Fallback DB lookback when item_catalog is empty.")
    parser.add_argument("--min-samples-7d", type=int, default=3, help="Minimum valid samples required in 7d window.")
    parser.add_argument("--deal-pct", type=float, default=-25.0, help="Current price must be <= this deviation vs 7d avg.")
    parser.add_argument("--limit", type=int, default=250, help="Maximum deals saved for this review.")
    parser.add_argument(
        "--artifact-only",
        action="store_true",
        help="Only review catalog rows marked as artifacts and save configured hot rarities.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="External item link base URL. Defaults to STALCRAFTDB_BASE_URL from .env.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    app_cfg = load_config(project_root=PROJECT_ROOT)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    config = DailyReviewConfig(
        recent_days=max(1, int(args.recent_days)),
        min_samples_7d=max(2, int(args.min_samples_7d)),
        deal_deviation_pct=float(args.deal_pct),
        limit=max(1, int(args.limit)),
        artifact_only=bool(args.artifact_only),
    )
    result = run_daily_market_review(
        repo=repo,
        config=config,
        base_url=args.base_url.strip() or app_cfg.base_url,
    )
    logging.info(
        "Daily review complete: review_id=%s scanned_items=%s deals_found=%s deals_saved=%s",
        result.review_id,
        result.scanned_items,
        result.deals_found,
        result.deals_saved,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
