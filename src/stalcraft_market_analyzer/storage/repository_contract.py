from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, TypedDict

from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord


class RepositoryPriceRecord(TypedDict):
    item_id: str
    item_name: str
    price: float
    volume: int
    observed_at: datetime
    source: str


@dataclass(frozen=True)
class IngestionBatch:
    snapshot_id: str
    collected_at: datetime
    records: list[RepositoryPriceRecord]


class PriceHistoryRepository(Protocol):
    def save_ingestion_batch(self, batch: IngestionBatch) -> int:
        """Persist the batch and return number of inserted rows."""


def build_ingestion_batch(snapshot_id: str, records: list[MarketPriceRecord]) -> IngestionBatch:
    payload: list[RepositoryPriceRecord] = []
    for record in records:
        payload.append(
            RepositoryPriceRecord(
                item_id=record.item_id,
                item_name=record.item_name,
                price=record.price,
                volume=record.volume,
                observed_at=record.observed_at,
                source=record.source,
            )
        )

    return IngestionBatch(
        snapshot_id=snapshot_id,
        collected_at=datetime.now(timezone.utc),
        records=payload,
    )
