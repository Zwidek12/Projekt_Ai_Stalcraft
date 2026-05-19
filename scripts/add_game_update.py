from __future__ import annotations

import argparse
import json
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

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add update/balance note for read-only User Web.")
    parser.add_argument("--type", default="update", choices=["update", "balance", "patch"], help="Update category.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--summary-file", default="", help="UTF-8 file used when --summary is empty.")
    parser.add_argument("--link", default="")
    parser.add_argument(
        "--new-item",
        action="append",
        default=[],
        help="Repeatable. Format: item_id:name:url(optional), e.g. 9nd0:Spectral Crystal:https://...",
    )
    parser.add_argument("--published-at", default="", help="ISO datetime. Defaults to now UTC.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    app_cfg = load_config(project_root=PROJECT_ROOT)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    summary = args.summary.strip()
    if not summary and args.summary_file.strip():
        path = Path(args.summary_file)
        if not path.is_file():
            path = PROJECT_ROOT / args.summary_file
        summary = path.read_text(encoding="utf-8").strip()

    update_id = repo.save_game_update(
        update={
            "update_type": args.type,
            "title": args.title,
            "summary": summary,
            "link_url": args.link,
            "new_items": [_parse_new_item(raw) for raw in args.new_item],
            "published_at": _parse_datetime(args.published_at) or datetime.now(timezone.utc),
        }
    )
    logging.info("Game update saved: id=%s", update_id)
    return 0


def _parse_new_item(raw: str) -> dict[str, str]:
    parts = raw.split(":", 2)
    item_id = parts[0].strip() if len(parts) >= 1 else ""
    name = parts[1].strip() if len(parts) >= 2 else item_id
    url = parts[2].strip() if len(parts) >= 3 else ""
    return {"item_id": item_id, "name": name, "url": url}


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = json.loads(f'"{value}"')
        dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
