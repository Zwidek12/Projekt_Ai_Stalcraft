from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.ingestion.catalog import (
    CatalogRefreshConfig,
    apply_artifact_rarity_enrichment,
    apply_artifact_rarity_overrides,
    build_catalog_refresh_summary,
    fetch_stalcraftdb_catalog,
    load_artifact_rarity_overrides,
)
from stalcraft_market_analyzer.ingestion.exbo_item_database import (
    ExboItemDatabaseConfig,
    fetch_exbo_artifact_rarity_index,
)
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local item_catalog from StalcraftDB listing.")
    parser.add_argument("--base-url", default="", help="Defaults to STALCRAFTDB_BASE_URL from .env.")
    parser.add_argument("--region", default="", help="Defaults to eu.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--artifact-rarity-overrides",
        default="",
        help="JSON file: {item_id: rarity} or list of {item_id, rarity}. Defaults to ARTIFACT_RARITY_OVERRIDES_FILE.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing to SQLite.")
    parser.add_argument("--skip-exbo-item-db", action="store_true", help="Skip public EXBO item database rarity enrichment.")
    parser.add_argument("--refresh-exbo-item-db-cache", action="store_true", help="Refresh cached EXBO item rarity data.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    app_cfg = load_config(project_root=PROJECT_ROOT)
    base_url = args.base_url.strip() or app_cfg.base_url
    region = args.region.strip() or "eu"

    items = fetch_stalcraftdb_catalog(
        CatalogRefreshConfig(
            base_url=base_url,
            region=region,
            timeout_seconds=max(3, int(args.timeout_seconds)),
        )
    )
    if app_cfg.exbo_item_db_enabled and not bool(args.skip_exbo_item_db):
        artifact_ids = {
            str(item.get("item_id") or "").strip()
            for item in items
            if bool(item.get("is_artifact", False)) and str(item.get("item_id") or "").strip()
        }
        rarity_index = fetch_exbo_artifact_rarity_index(
            config=ExboItemDatabaseConfig(
                realm=app_cfg.exbo_item_db_realm,
                timeout_seconds=max(3, int(args.timeout_seconds)),
                cache_path=app_cfg.exbo_item_db_cache_file,
                refresh_cache=bool(args.refresh_exbo_item_db_cache),
            ),
            item_ids=artifact_ids,
        )
        items = apply_artifact_rarity_enrichment(items=items, rarity_by_item_id=rarity_index)
        logging.info(
            "Applied EXBO item database rarity enrichment: realm=%s entries=%s cache=%s",
            app_cfg.exbo_item_db_realm,
            len(rarity_index),
            app_cfg.exbo_item_db_cache_file,
        )
    overrides_path = _resolve_overrides_path(args.artifact_rarity_overrides, project_root=PROJECT_ROOT)
    if overrides_path is not None:
        overrides = load_artifact_rarity_overrides(overrides_path)
        items = apply_artifact_rarity_overrides(items=items, overrides=overrides)
        logging.info("Applied artifact rarity overrides: file=%s entries=%s", overrides_path, len(overrides))
    summary = build_catalog_refresh_summary(items)
    logging.info("Catalog fetch summary: %s", json.dumps(summary, ensure_ascii=False, sort_keys=True))

    if args.dry_run:
        return 0

    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    changed = repo.upsert_item_catalog(items=items)
    logging.info("Catalog persisted: changed=%s", changed)
    return 0


def _resolve_overrides_path(raw: str, *, project_root: Path) -> Path | None:
    value = raw.strip()
    if not value:
        import os

        value = os.environ.get("ARTIFACT_RARITY_OVERRIDES_FILE", "").strip()
    if not value:
        default_path = project_root / "data" / "artifact_rarity_overrides.json"
        return default_path if default_path.is_file() else None
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    fallback = project_root / value
    return fallback if fallback.is_file() else candidate


if __name__ == "__main__":
    raise SystemExit(main())
