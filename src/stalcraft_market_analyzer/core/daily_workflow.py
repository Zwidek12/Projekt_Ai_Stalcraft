from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from stalcraft_market_analyzer.analysis.daily_review import DailyReviewConfig, DailyReviewResult, run_daily_market_review
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.core.pipeline import ingest_items
from stalcraft_market_analyzer.core.workflow_checkpoint import (
    build_run_key,
    checkpoint_path,
    clear_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from stalcraft_market_analyzer.ingestion.catalog import (
    CatalogRefreshConfig,
    build_catalog_refresh_summary,
    fetch_stalcraftdb_catalog,
)
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DailyWorkflowConfig:
    region: str = "eu"
    timeout_seconds: int = 15
    batch_size: int = 25
    sleep_seconds: float = 1.5
    limit: int = 0
    artifact_only: bool = False
    refresh_catalog: bool = True
    run_ingestion: bool = True
    run_review: bool = True
    review_deal_pct: float = -25.0
    review_limit: int = 250
    resume_from_checkpoint: bool = True
    fresh_run: bool = False


@dataclass(frozen=True, slots=True)
class DailyWorkflowResult:
    catalog_items: int
    catalog_changed: int
    ingestion_items: int
    ingestion_batches: int
    ingestion_failures: int
    review: DailyReviewResult | None


def run_daily_workflow(
    *,
    project_root: Path,
    config: DailyWorkflowConfig | None = None,
    base_url: str = "",
) -> DailyWorkflowResult:
    cfg = config or DailyWorkflowConfig()
    app_cfg = load_config(project_root=project_root)
    resolved_base_url = base_url.strip() or app_cfg.base_url
    resolved_region = cfg.region.strip() or "eu"

    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    catalog_items = 0
    catalog_changed = 0
    if cfg.refresh_catalog:
        fetched = fetch_stalcraftdb_catalog(
            CatalogRefreshConfig(
                base_url=resolved_base_url,
                region=resolved_region,
                timeout_seconds=max(3, int(cfg.timeout_seconds)),
            )
        )
        catalog_items = len(fetched)
        catalog_changed = repo.upsert_item_catalog(items=fetched)
        logger.info("Daily workflow catalog summary: %s", build_catalog_refresh_summary(fetched))

    ingestion_items = 0
    ingestion_batches = 0
    ingestion_failures = 0
    if cfg.run_ingestion:
        ingestion_items, ingestion_batches, ingestion_failures = _ingest_catalog_batches(
            project_root=project_root,
            repo=repo,
            base_url=resolved_base_url,
            region=resolved_region,
            cfg=cfg,
        )
        if ingestion_failures == 0:
            clear_checkpoint(checkpoint_path(project_root))

    review: DailyReviewResult | None = None
    if cfg.run_review:
        review = run_daily_market_review(
            repo=repo,
            config=DailyReviewConfig(
                deal_deviation_pct=float(cfg.review_deal_pct),
                limit=max(1, int(cfg.review_limit)),
                artifact_only=bool(cfg.artifact_only),
            ),
            base_url=resolved_base_url,
        )

    return DailyWorkflowResult(
        catalog_items=catalog_items,
        catalog_changed=catalog_changed,
        ingestion_items=ingestion_items,
        ingestion_batches=ingestion_batches,
        ingestion_failures=ingestion_failures,
        review=review,
    )


def _ingest_catalog_batches(
    *,
    project_root: Path,
    repo: SqlAlchemyRepository,
    base_url: str,
    region: str,
    cfg: DailyWorkflowConfig,
) -> tuple[int, int, int]:
    catalog = repo.get_catalog_items(artifact_only=bool(cfg.artifact_only), limit=50_000)
    item_ids = [str(row["item_id"]) for row in catalog if str(row.get("item_id", "")).strip()]
    if cfg.limit and int(cfg.limit) > 0:
        item_ids = item_ids[: int(cfg.limit)]
    if not item_ids:
        logger.warning("Daily workflow ingestion skipped: item_catalog is empty.")
        return 0, 0, 0

    batch_size = max(1, int(cfg.batch_size))
    total_batches = (len(item_ids) + batch_size - 1) // batch_size
    failures = 0
    failed_batch_numbers: list[int] = []

    ckpt_file = checkpoint_path(project_root)
    run_key = build_run_key(region=region, artifact_only=bool(cfg.artifact_only), limit=int(cfg.limit))
    if cfg.fresh_run:
        clear_checkpoint(ckpt_file)

    start_batch_index = 0
    if cfg.resume_from_checkpoint:
        existing = load_checkpoint(ckpt_file)
        if existing is not None and existing.run_key == run_key:
            start_batch_index = min(existing.next_batch_index, total_batches)
            failed_batch_numbers = list(existing.failed_batches)
            if start_batch_index:
                logger.info(
                    "Resuming daily workflow ingestion from batch %s/%s (failed_batches=%s)",
                    start_batch_index + 1,
                    total_batches,
                    failed_batch_numbers or "none",
                )

    for batch_index in range(start_batch_index, total_batches):
        idx = batch_index * batch_size
        batch_no = batch_index + 1
        batch = item_ids[idx : idx + batch_size]
        logger.info("Daily workflow ingestion batch %s/%s (items=%s)", batch_no, total_batches, len(batch))
        try:
            rc = ingest_items(
                project_root=project_root,
                items_csv=",".join(batch),
                timeout_seconds=max(3, int(cfg.timeout_seconds)),
                base_url=base_url,
                region=region,
                print_records=False,
            )
        except Exception as error:
            logger.warning(
                "Daily workflow batch %s/%s crashed; skipping corrupted batch: %s",
                batch_no,
                total_batches,
                error,
            )
            rc = 1

        if rc != 0:
            failures += 1
            if batch_no not in failed_batch_numbers:
                failed_batch_numbers.append(batch_no)

        save_checkpoint(
            ckpt_file,
            run_key=run_key,
            next_batch_index=batch_index + 1,
            failed_batches=failed_batch_numbers,
        )

        if batch_no < total_batches:
            time.sleep(max(0.0, float(cfg.sleep_seconds)))
    return len(item_ids), total_batches, failures
