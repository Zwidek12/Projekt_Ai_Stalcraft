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

from stalcraft_market_analyzer.core.pipeline import run_market_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end pipeline: ingest → anomaly scan (+ optional Discord) → optional patch LLM.")

    parser.add_argument("--items", required=True, help="Comma-separated item ids for ingestion.")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--region", default="")

    parser.add_argument("--recent-hours", type=int, default=48)
    parser.add_argument("--baseline-days", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=6)
    parser.add_argument("--deal-pct", type=float, default=-35.0)
    parser.add_argument("--spike-pct", type=float, default=60.0)
    parser.add_argument("--send-discord", action="store_true")
    parser.add_argument(
        "--force-discord-notify",
        action="store_true",
        help="Send Discord even when anomaly fingerprint already exists (deduped).",
    )

    parser.add_argument("--patch-version", default="")
    parser.add_argument("--patch-notes-file", default="")
    parser.add_argument("--patch-notes", default="")
    parser.add_argument("--send-patch-discord", action="store_true")

    parser.add_argument("--discord-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    return run_market_pipeline(project_root=PROJECT_ROOT, args=parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
