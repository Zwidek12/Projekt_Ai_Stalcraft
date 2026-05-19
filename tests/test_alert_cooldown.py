from __future__ import annotations

import os
from datetime import datetime, timezone

from api.analysis_jobs import run_price_anomaly_scan_job
from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord
from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch


def _dt(day: int, hour: int) -> datetime:
    return datetime(2026, 5, day, hour, 0, 0, tzinfo=timezone.utc)


def test_price_alert_cooldown_skips_second_signal(monkeypatch) -> None:
    monkeypatch.setenv("PRICE_ALERT_COOLDOWN_MINUTES", "60")

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

    assert repo.save_alert(
        alert_type="price_anomaly",
        fingerprint="manual",
        payload={"reason": "seed"},
        item_id="i1",
    )

    result = run_price_anomaly_scan_job(repo=repo, item_ids=["i1"], now=_dt(5, 12), send_discord=False)
    assert int(result.get("cooldown_skipped", 0)) == 1
