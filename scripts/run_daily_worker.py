from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import schedule

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.daily_workflow import DailyWorkflowConfig, run_daily_workflow
from stalcraft_market_analyzer.core.scheduler import run_forever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blocking daily worker for market workflow.")
    parser.add_argument("--at", default="06:00", help="Local time HH:MM for daily workflow.")
    parser.add_argument("--run-on-start", action="store_true")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--region", default="eu")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--artifact-only", action="store_true")
    parser.add_argument("--review-deal-pct", type=float, default=-25.0)
    parser.add_argument("--review-limit", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    cfg = DailyWorkflowConfig(
        region=args.region,
        timeout_seconds=max(3, int(args.timeout_seconds)),
        batch_size=max(1, int(args.batch_size)),
        sleep_seconds=max(0.0, float(args.sleep_seconds)),
        limit=max(0, int(args.limit)),
        artifact_only=bool(args.artifact_only),
        review_deal_pct=float(args.review_deal_pct),
        review_limit=max(1, int(args.review_limit)),
    )

    def _job() -> None:
        result = run_daily_workflow(project_root=PROJECT_ROOT, config=cfg, base_url=args.base_url)
        logging.info("Daily worker run complete: %s", result)

    schedule.every().day.at(args.at).do(_job)
    logging.info("Daily worker scheduled at %s (local time).", args.at)
    if args.run_on_start:
        _job()
    run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
