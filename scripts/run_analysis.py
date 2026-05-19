from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.analysis_jobs import run_price_anomaly_scan_job
from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_price_opportunity_embed
from stalcraft_market_analyzer.analysis.analyzer import AnomalyScanConfig
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run basic price anomaly detection using DB history.")
    parser.add_argument(
        "--items",
        default="",
        help="Comma-separated item ids to scan. If empty, scans recent distinct ids from DB.",
    )
    parser.add_argument("--recent-hours", type=int, default=48, help="How far back to look for recent items if --items omitted.")
    parser.add_argument("--baseline-days", type=int, default=7, help="Baseline window in days.")
    parser.add_argument("--min-samples", type=int, default=6, help="Minimum baseline+latest samples required.")
    parser.add_argument("--deal-pct", type=float, default=-35.0, help="Deviation threshold for a deal (negative percent).")
    parser.add_argument("--spike-pct", type=float, default=60.0, help="Deviation threshold for a spike (positive percent).")
    parser.add_argument(
        "--send-discord",
        action="store_true",
        help="If set, sends Discord alerts for newly inserted anomaly rows.",
    )
    parser.add_argument(
        "--force-discord-notify",
        action="store_true",
        help="Dev/test: send Discord embed even when alert fingerprint already exists (deduped).",
    )
    parser.add_argument(
        "--discord-test",
        action="store_true",
        help="Send a deterministic Discord embed after the scan (for webhook diagnostics).",
    )
    return parser.parse_args()


def run_analysis_job(*, args: argparse.Namespace | None = None) -> int:
    effective_args = args or parse_args()

    app_cfg = load_config(project_root=PROJECT_ROOT)
    logging.info("Starting anomaly scan job (send_discord=%s)...", bool(effective_args.send_discord))
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime.now(timezone.utc)
    items_arg = effective_args.items.strip()
    item_ids = [token.strip() for token in items_arg.split(",") if token.strip()] if items_arg else None

    config = AnomalyScanConfig(
        baseline_days=max(1, int(effective_args.baseline_days)),
        min_samples=max(3, int(effective_args.min_samples)),
        deal_deviation_pct=float(effective_args.deal_pct),
        spike_deviation_pct=float(effective_args.spike_pct),
    )

    result = run_price_anomaly_scan_job(
        repo=repo,
        now=now,
        recent_hours=max(1, int(effective_args.recent_hours)),
        item_ids=item_ids,
        send_discord=bool(effective_args.send_discord),
        force_discord_notify=bool(effective_args.force_discord_notify),
        anomaly_config=config,
    )

    logging.info("Anomaly scan complete: %s", result)

    if effective_args.discord_test:
        try:
            notifier = DiscordNotifier.from_env()
            embed = build_price_opportunity_embed(
                {
                    "severity": "low",
                    "item_name": "CLI webhook test (run_analysis)",
                    "price": 1,
                    "deviation_pct": 0.0,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "source": "run_analysis.py",
                    "notes": "This is a diagnostics message sent by --discord-test (independent of anomalies).",
                }
            )
            resp = notifier.send_price_alert({"source": "run_analysis.py", "mode": "discord_test"}, embeds=[embed])
            logging.info("Discord test send: status=%s http=%s err=%s", resp.status, resp.http_status, resp.error)
        except Exception as error:
            logging.error("Discord test send failed: %s", error)
            return 2

    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return run_analysis_job(args=parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
