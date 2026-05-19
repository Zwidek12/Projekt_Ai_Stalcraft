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
