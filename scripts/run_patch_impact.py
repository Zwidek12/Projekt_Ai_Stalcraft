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

from api.health import record_anomaly_scan
from api.patch_jobs import run_patch_impact_job
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze patch notes (LLM optional) + optional Discord broadcast.")
    parser.add_argument("--patch-version", required=True, help="Patch version tag, example: 1.9.14")
    parser.add_argument("--notes-file", default="", help="Path to UTF-8 text file containing patch notes.")
    parser.add_argument(
        "--notes",
        "--patch-notes",
        dest="notes",
        default="",
        help="Inline patch notes (quote in PowerShell if text starts with '-' or contains spaces).",
    )
    parser.add_argument("--send-discord", action="store_true", help="Send Discord embed if thresholds are met.")
    return parser.parse_args()


def _resolve_notes_file_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_file():
        return candidate
    fallback = PROJECT_ROOT / raw
    if fallback.is_file():
        return fallback
    return candidate


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    if args.notes_file.strip():
        notes_path = _resolve_notes_file_path(args.notes_file.strip())
        if not notes_path.is_file():
            logging.error(
                "Patch notes file not found: %s (tried absolute path and %s)",
                args.notes_file.strip(),
                PROJECT_ROOT / args.notes_file.strip(),
            )
            return 2
        patch_text = notes_path.read_text(encoding="utf-8")
    else:
        patch_text = args.notes

    patch_text_stripped = patch_text.strip()
    if not patch_text_stripped:
        logging.error("No patch notes provided (use --notes or --notes-file).")
        return 1

    app_cfg = load_config(project_root=PROJECT_ROOT)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    result = run_patch_impact_job(
        repo=repo,
        patch_version=args.patch_version.strip(),
        patch_text=patch_text_stripped,
        send_discord=bool(args.send_discord),
    )
    logging.info("Patch impact job complete: %s", result)
    record_anomaly_scan()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
