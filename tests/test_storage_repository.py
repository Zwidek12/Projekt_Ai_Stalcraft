from __future__ import annotations

from datetime import datetime, timezone

from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import IngestionBatch, RepositoryPriceRecord


def _batch(*, snapshot_id: str) -> IngestionBatch:
    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    record: RepositoryPriceRecord = {
        "item_id": "7lrz3",
        "item_name": "AK-103",
        "price": 123.0,
        "volume": 1,
        "observed_at": datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        "source": "stalcraftdb_auction",
    }
    return IngestionBatch(snapshot_id=snapshot_id, collected_at=now, records=[record])


def test_save_ingestion_batch_dedupes_by_unique_key() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    batch = _batch(snapshot_id="snap1")
    inserted_1 = repo.save_ingestion_batch(batch)
    inserted_2 = repo.save_ingestion_batch(batch)

    assert inserted_1 == 1
    assert inserted_2 == 0


def test_get_average_price_7d_returns_value() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    batch = _batch(snapshot_id="snap2")
    repo.save_ingestion_batch(batch)

    avg = repo.get_average_price_7d(item_id="7lrz3", now=datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc))
    assert avg == 123.0

