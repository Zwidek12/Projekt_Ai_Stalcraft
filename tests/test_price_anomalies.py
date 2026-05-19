from __future__ import annotations

from datetime import datetime, timezone

from stalcraft_market_analyzer.analysis.analyzer import AnomalyScanConfig, scan_price_anomalies
from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch


def _dt(day: int, hour: int) -> datetime:
    return datetime(2026, 5, day, hour, 0, 0, tzinfo=timezone.utc)


def test_detects_price_deal_against_baseline_median() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    records = [
        MarketPriceRecord(item_id="i1", item_name="Item", price=1_000_000.0, volume=1, observed_at=_dt(1, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i1", item_name="Item", price=1_050_000.0, volume=1, observed_at=_dt(1, 11), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i1", item_name="Item", price=980_000.0, volume=1, observed_at=_dt(1, 12), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i1", item_name="Item", price=1_020_000.0, volume=1, observed_at=_dt(2, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i1", item_name="Item", price=1_000_000.0, volume=1, observed_at=_dt(3, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i1", item_name="Item", price=500_000.0, volume=1, observed_at=_dt(5, 10), source="stalcraftdb_auction"),
    ]
    repo.save_ingestion_batch(build_ingestion_batch(snapshot_id="snap-test", records=records))

    signals = scan_price_anomalies(
        repo=repo,
        item_ids=["i1"],
        now=_dt(5, 12),
        config=AnomalyScanConfig(min_samples=6, deal_deviation_pct=-35.0, spike_deviation_pct=60.0),
    )

    assert len(signals) == 1
    assert signals[0].kind == "price_deal"
    assert signals[0].item_id == "i1"


def test_no_signal_when_threshold_not_met() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    records = [
        MarketPriceRecord(item_id="i2", item_name="Item", price=1_000_000.0, volume=1, observed_at=_dt(1, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i2", item_name="Item", price=1_050_000.0, volume=1, observed_at=_dt(1, 11), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i2", item_name="Item", price=980_000.0, volume=1, observed_at=_dt(1, 12), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i2", item_name="Item", price=1_020_000.0, volume=1, observed_at=_dt(2, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i2", item_name="Item", price=1_000_000.0, volume=1, observed_at=_dt(3, 10), source="stalcraftdb_auction"),
        MarketPriceRecord(item_id="i2", item_name="Item", price=980_000.0, volume=1, observed_at=_dt(5, 10), source="stalcraftdb_auction"),
    ]
    repo.save_ingestion_batch(build_ingestion_batch(snapshot_id="snap-test-2", records=records))

    signals = scan_price_anomalies(
        repo=repo,
        item_ids=["i2"],
        now=_dt(5, 12),
        config=AnomalyScanConfig(min_samples=6, deal_deviation_pct=-35.0, spike_deviation_pct=60.0),
    )

    assert signals == []
