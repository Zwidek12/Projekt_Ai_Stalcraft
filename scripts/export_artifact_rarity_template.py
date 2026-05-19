from __future__ import annotations

import argparse
import json
import sys
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
    parser = argparse.ArgumentParser(description="Export artifact rarity override template from item_catalog.")
    parser.add_argument("--output", default="data/artifact_rarity_overrides.template.json")
    parser.add_argument("--only-unknown", action="store_true", help="Only export artifacts with rarity=unknown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_cfg = load_config(project_root=PROJECT_ROOT)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    rows = repo.search_artifacts(artifact_only=True, limit=50_000)
    if args.only_unknown:
        rows = [row for row in rows if str(row.get("rarity", "unknown")) == "unknown"]

    template = [
        {
            "item_id": str(row["item_id"]),
            "item_name": str(row["item_name"]),
            "rarity": str(row.get("rarity") or "unknown"),
            "allowed": ["pink", "red", "gold"],
        }
        for row in rows
    ]
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(template)} artifact rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
