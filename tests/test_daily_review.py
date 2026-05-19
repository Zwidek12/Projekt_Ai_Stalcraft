from __future__ import annotations

from datetime import datetime, timedelta, timezone

from stalcraft_market_analyzer.analysis.daily_review import DailyReviewConfig, run_daily_market_review
from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch


def test_daily_review_saves_discounted_market_deal() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        MarketPriceRecord(
            item_id="art1",
            item_name="Gold Artifact",
            price=1000.0,
            volume=1,
            observed_at=now - timedelta(days=6),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art1",
            item_name="Gold Artifact",
            price=950.0,
            volume=1,
            observed_at=now - timedelta(days=3),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art1",
            item_name="Gold Artifact",
            price=500.0,
            volume=1,
            observed_at=now,
            source="stalcraftdb_auction",
            rarity="exclusive",
        ),
    ]
    repo.save_ingestion_batch(build_ingestion_batch(snapshot_id="snap-review", records=records))

    result = run_daily_market_review(
        repo=repo,
        now=now,
        config=DailyReviewConfig(min_samples_7d=3, deal_deviation_pct=-25.0),
        base_url="https://stalcraftdb.net/eu",
    )

    assert result.scanned_items == 1
    assert result.deals_found == 1
    assert result.deals_saved == 1

    deals = repo.get_hot_deals(artifact_only=False, limit=10)
    assert len(deals) == 1
    assert deals[0]["item_id"] == "art1"
    assert deals[0]["rarity"] == "exclusive"
    assert float(deals[0]["deviation_pct"]) < -25.0


def test_daily_review_ignores_outlier_when_computing_average() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        MarketPriceRecord(
            item_id="art2",
            item_name="Artifact",
            price=1_000.0,
            volume=1,
            observed_at=now - timedelta(days=6),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art2",
            item_name="Artifact",
            price=1_020.0,
            volume=1,
            observed_at=now - timedelta(days=5),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art2",
            item_name="Artifact",
            price=990.0,
            volume=1,
            observed_at=now - timedelta(days=4),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art2",
            item_name="Artifact",
            price=50_000_000.0,
            volume=1,
            observed_at=now - timedelta(days=2),
            source="stalcraftdb_auction",
        ),
        MarketPriceRecord(
            item_id="art2",
            item_name="Artifact",
            price=500.0,
            volume=1,
            observed_at=now,
            source="stalcraftdb_auction",
        ),
    ]
    repo.save_ingestion_batch(build_ingestion_batch(snapshot_id="snap-outlier", records=records))

    result = run_daily_market_review(
        repo=repo,
        now=now,
        config=DailyReviewConfig(min_samples_7d=4, deal_deviation_pct=-25.0),
    )

    assert result.deals_found == 1
    deals = repo.get_hot_deals(artifact_only=False, limit=10)
    assert deals[0]["item_id"] == "art2"
