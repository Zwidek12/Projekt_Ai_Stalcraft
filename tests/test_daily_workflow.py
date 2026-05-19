from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from stalcraft_market_analyzer.analysis.daily_review import DailyReviewResult
from stalcraft_market_analyzer.core import daily_workflow
from stalcraft_market_analyzer.core.daily_workflow import DailyWorkflowConfig, run_daily_workflow


def test_daily_workflow_runs_catalog_ingestion_and_review(monkeypatch, tmp_path: Path) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'market.db').as_posix()}"
    monkeypatch.setattr(
        daily_workflow,
        "load_config",
        lambda project_root: SimpleNamespace(
            base_url="https://stalcraftdb.net/eu",
            database_url=db_url,
        ),
    )
    monkeypatch.setattr(
        daily_workflow,
        "fetch_stalcraftdb_catalog",
        lambda config: [
            {
                "item_id": "art1",
                "item_name": "Gold Artifact",
                "rarity": "gold",
                "category": "artifact",
                "external_url": "https://stalcraftdb.net/eu/items/art1",
                "is_artifact": True,
            }
        ],
    )

    ingested: list[str] = []

    def _fake_ingest_items(**kwargs: object) -> int:
        ingested.append(str(kwargs["items_csv"]))
        return 0

    monkeypatch.setattr(daily_workflow, "ingest_items", _fake_ingest_items)
    monkeypatch.setattr(
        daily_workflow,
        "run_daily_market_review",
        lambda **kwargs: DailyReviewResult(
            review_id="daily-test",
            scanned_items=1,
            deals_found=1,
            deals_saved=1,
        ),
    )

    result = run_daily_workflow(
        project_root=tmp_path,
        config=DailyWorkflowConfig(batch_size=1, sleep_seconds=0, artifact_only=True),
    )

    assert result.catalog_items == 1
    assert result.catalog_changed == 1
    assert result.ingestion_items == 1
    assert result.ingestion_batches == 1
    assert result.ingestion_failures == 0
    assert result.review is not None
    assert result.review.deals_saved == 1
    assert ingested == ["art1"]


def test_daily_workflow_resumes_from_checkpoint(monkeypatch, tmp_path: Path) -> None:
    from stalcraft_market_analyzer.core.workflow_checkpoint import build_run_key, checkpoint_path, save_checkpoint
    from stalcraft_market_analyzer.storage.db import create_database, init_schema
    from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

    db_url = f"sqlite+pysqlite:///{(tmp_path / 'resume.db').as_posix()}"
    monkeypatch.setattr(
        daily_workflow,
        "load_config",
        lambda project_root: SimpleNamespace(
            base_url="https://stalcraftdb.net/eu",
            database_url=db_url,
        ),
    )
    monkeypatch.setattr(daily_workflow, "fetch_stalcraftdb_catalog", lambda config: [])
    monkeypatch.setattr(daily_workflow, "run_daily_market_review", lambda **kwargs: None)

    calls: list[str] = []

    def _fake_ingest(**kwargs: object) -> int:
        calls.append(str(kwargs["items_csv"]))
        return 0

    monkeypatch.setattr(daily_workflow, "ingest_items", _fake_ingest)

    db = create_database(db_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    repo.upsert_item_catalog(
        items=[
            {
                "item_id": "a1",
                "item_name": "A",
                "rarity": "common",
                "category": "x",
                "external_url": "",
                "is_artifact": False,
            },
            {
                "item_id": "a2",
                "item_name": "B",
                "rarity": "common",
                "category": "x",
                "external_url": "",
                "is_artifact": False,
            },
        ]
    )

    run_key = build_run_key(region="eu", artifact_only=False, limit=0)
    save_checkpoint(checkpoint_path(tmp_path), run_key=run_key, next_batch_index=1, failed_batches=[])

    run_daily_workflow(
        project_root=tmp_path,
        config=DailyWorkflowConfig(
            region="eu",
            refresh_catalog=False,
            batch_size=1,
            sleep_seconds=0,
            artifact_only=False,
            fresh_run=False,
            resume_from_checkpoint=True,
            run_review=False,
        ),
    )
    assert calls == ["a2"]
