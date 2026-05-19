from __future__ import annotations

from datetime import datetime, timezone

from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord
from stalcraft_market_analyzer.storage.repository_contract import build_ingestion_batch


def test_build_ingestion_batch_maps_records() -> None:
    input_records = [
        MarketPriceRecord(
            item_id="ak-103",
            item_name="AK-103",
            price=15000.0,
            volume=7,
            observed_at=datetime(2026, 4, 28, 18, 0, tzinfo=timezone.utc),
            source="json_api",
        )
    ]
    batch = build_ingestion_batch(snapshot_id="snapshot-1", records=input_records)
    assert batch.snapshot_id == "snapshot-1"
    assert len(batch.records) == 1
    assert batch.records[0]["item_id"] == "ak-103"
    assert batch.records[0]["source"] == "json_api"
