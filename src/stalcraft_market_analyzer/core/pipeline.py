from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from api.analysis_jobs import run_price_anomaly_scan_job
from api.health import record_anomaly_scan, record_ingestion
from api.patch_jobs import run_patch_impact_job
from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_price_opportunity_embed
from stalcraft_market_analyzer.analysis.analyzer import AnomalyScanConfig
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.ingestion.exporter import build_quality_report, write_raw_snapshot
from stalcraft_market_analyzer.ingestion.scraper import ScraperConfig, StalcraftPriceScraper
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import CatalogItemInput
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch

logger = logging.getLogger(__name__)


def ingest_items(
    *,
    project_root: Path,
    items_csv: str,
    timeout_seconds: int,
    base_url: str,
    region: str,
    print_records: bool = True,
) -> int:
    item_ids = [value.strip() for value in items_csv.split(",") if value.strip()]
    if not item_ids:
        logger.error("No valid item ids were provided.")
        return 1

    app_cfg = load_config(project_root=project_root)
    resolved_base = base_url.strip() or app_cfg.base_url
    resolved_region = region.strip() or "eu"

    scraper = StalcraftPriceScraper(
        config=ScraperConfig(
            base_url=resolved_base,
            region=resolved_region,
            timeout_seconds=timeout_seconds,
            exbo_api_base_url=app_cfg.exbo_api_base_url,
            exbo_region=app_cfg.exbo_region,
            exbo_access_token=app_cfg.exbo_access_token,
            exbo_client_id=app_cfg.exbo_client_id,
            exbo_client_secret=app_cfg.exbo_client_secret,
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

    if print_records:
        for record in records:
            print(record)
    logging.info("Ingestion finished. Records fetched: %s", len(records))
    logging.info("Raw snapshot saved to: %s", snapshot_result.output_path)
    logging.info(
        "Data quality report => total=%s api=%s html=%s exbo=%s mock=%s",
        quality_report.total_records,
        quality_report.json_api_records,
        quality_report.html_table_records,
        quality_report.exbo_auction_records,
        quality_report.mock_js_fallback_records,
    )
    logging.info("Repository batch contract ready with %s records.", len(batch.records))
    logging.info("Inserted into DB: %s", inserted)
    return 0


def _catalog_updates_from_records(
    *,
    records: list[object],
    base_url: str,
    region: str,
) -> list[CatalogItemInput]:
    updates: dict[str, CatalogItemInput] = {}
    for record in records:
        item_id = str(getattr(record, "item_id", "")).strip()
        if not item_id:
            continue
        rarity = str(getattr(record, "rarity", "unknown") or "unknown").strip().lower()
        if rarity == "unknown":
            continue
        updates[item_id] = CatalogItemInput(
            item_id=item_id,
            item_name=str(getattr(record, "item_name", f"item_{item_id}")),
            rarity=rarity,
            category="unknown",
            external_url=_external_item_url(base_url=base_url, region=region, item_id=item_id),
            is_artifact=True,
        )
    return list(updates.values())


def _external_item_url(*, base_url: str, region: str, item_id: str) -> str:
    base = base_url.rstrip("/")
    if "stalcraftdb.net" in base:
        origin = base.split("/eu")[0].split("/na")[0].split("/sea")[0].split("/ru")[0]
        return f"{origin}/{region}/items/{item_id}"
    return f"{base}/items/{item_id}" if base else ""


def anomaly_scan(
    *,
    project_root: Path,
    items_csv: str,
    recent_hours: int,
    baseline_days: int,
    min_samples: int,
    deal_pct: float,
    spike_pct: float,
    send_discord: bool,
    force_discord_notify: bool,
    discord_test: bool,
) -> int:
    app_cfg = load_config(project_root=project_root)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime.now(timezone.utc)
    items_arg = items_csv.strip()
    item_ids = [token.strip() for token in items_arg.split(",") if token.strip()] if items_arg else None

    config = AnomalyScanConfig(
        baseline_days=max(1, int(baseline_days)),
        min_samples=max(3, int(min_samples)),
        deal_deviation_pct=float(deal_pct),
        spike_deviation_pct=float(spike_pct),
    )

    result = run_price_anomaly_scan_job(
        repo=repo,
        now=now,
        recent_hours=max(1, int(recent_hours)),
        item_ids=item_ids,
        send_discord=bool(send_discord),
        force_discord_notify=bool(force_discord_notify),
        anomaly_config=config,
    )
    logging.info("Anomaly scan complete: %s", result)

    if discord_test:
        try:
            notifier = DiscordNotifier.from_env()
            embed = build_price_opportunity_embed(
                {
                    "severity": "low",
                    "item_name": "CLI webhook test (pipeline)",
                    "price": 1,
                    "deviation_pct": 0.0,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "source": "run_pipeline.py",
                    "notes": "Diagnostics message (--discord-test).",
                }
            )
            resp = notifier.send_price_alert({"source": "run_pipeline.py", "mode": "discord_test"}, embeds=[embed])
            logging.info("Discord test send: status=%s http=%s err=%s", resp.status, resp.http_status, resp.error)
        except Exception as error:
            logging.error("Discord test send failed: %s", error)
            return 2

    return 0


def patch_stage(
    *,
    project_root: Path,
    patch_version: str,
    patch_text: str,
    send_discord: bool,
) -> None:
    app_cfg = load_config(project_root=project_root)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    logging.info(
        "Patch stage: %s",
        run_patch_impact_job(repo=repo, patch_version=patch_version, patch_text=patch_text, send_discord=send_discord),
    )


def run_market_pipeline(
    *,
    project_root: Path,
    args: argparse.Namespace,
) -> int:
    rc = ingest_items(
        project_root=project_root,
        items_csv=args.items,
        timeout_seconds=args.timeout_seconds,
        base_url=args.base_url,
        region=args.region,
    )
    if rc != 0:
        return rc
    record_ingestion()

    rc = anomaly_scan(
        project_root=project_root,
        items_csv=args.items,
        recent_hours=args.recent_hours,
        baseline_days=args.baseline_days,
        min_samples=args.min_samples,
        deal_pct=args.deal_pct,
        spike_pct=args.spike_pct,
        send_discord=bool(args.send_discord),
        force_discord_notify=bool(getattr(args, "force_discord_notify", False)),
        discord_test=bool(args.discord_test),
    )
    if rc != 0:
        return rc
    record_anomaly_scan()

    patch_version = args.patch_version.strip()
    patch_file = args.patch_notes_file.strip()
    patch_inline = args.patch_notes.strip()
    if patch_version:
        if patch_file:
            candidate = Path(patch_file)
            notes_path = candidate if candidate.is_file() else (project_root / patch_file)
            if not notes_path.is_file():
                logger.error("Patch notes file not found: %s (cwd=%s)", patch_file, Path.cwd())
                return 1
            patch_text = notes_path.read_text(encoding="utf-8")
        else:
            patch_text = patch_inline
        if not patch_text.strip():
            logger.error("--patch-version set but patch notes missing (pass --patch-notes-file or --patch-notes).")
            return 1
        patch_stage(
            project_root=project_root,
            patch_version=patch_version,
            patch_text=patch_text.strip(),
            send_discord=bool(args.send_patch_discord),
        )

    return 0
