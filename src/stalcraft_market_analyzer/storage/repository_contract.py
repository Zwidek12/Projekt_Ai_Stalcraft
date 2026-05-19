from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, TypedDict

from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord
from stalcraft_market_analyzer.storage.models import PriceHistory


class RepositoryPriceRecord(TypedDict):
    item_id: str
    item_name: str
    price: float
    volume: int
    observed_at: datetime
    source: str
    rarity: str


class PriceObservation(TypedDict):
    price: float
    observed_at: datetime
    source: str
    rarity: str


class CatalogItemInput(TypedDict, total=False):
    item_id: str
    item_name: str
    rarity: str
    category: str
    external_url: str
    is_artifact: bool


class MarketDealInput(TypedDict):
    item_id: str
    item_name: str
    rarity: str
    category: str
    external_url: str
    is_artifact: bool
    current_price: float
    avg_price_1d: float
    avg_price_7d: float
    deviation_pct: float
    deal_score: float
    observed_at: datetime
    source: str


class GameUpdateInput(TypedDict, total=False):
    update_type: str
    title: str
    summary: str
    link_url: str
    new_items: list[dict[str, str]]
    published_at: datetime


@dataclass(frozen=True)
class IngestionBatch:
    snapshot_id: str
    collected_at: datetime
    records: list[RepositoryPriceRecord]


class PriceHistoryRepository(Protocol):
    def save_ingestion_batch(self, batch: IngestionBatch) -> int:
        """Persist the batch and return number of inserted rows."""

    def get_average_price_7d(self, *, item_id: str, now: datetime | None = None) -> float | None:
        """Return average price over last 7 days or None if no data."""

    def get_price_history_since(self, *, item_id: str, since: datetime) -> list[PriceHistory]:
        """Return price rows for item since timestamp (UTC-aware), ascending by observed_at."""

    def get_distinct_item_ids(self, *, since: datetime) -> list[str]:
        """Return distinct item ids seen since the given timestamp (UTC-aware)."""

    def get_observed_prices_since(self, *, item_id: str, since: datetime) -> list[float]:
        """Return observed prices for an item since the given timestamp (ascending by time)."""

    def get_price_observations_since(self, *, item_id: str, since: datetime) -> list[PriceObservation]:
        """Return price observations (price, observed_at, source) since timestamp (ascending by time)."""


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
                rarity=record.rarity,
            )
        )

    return IngestionBatch(
        snapshot_id=snapshot_id,
        collected_at=datetime.now(timezone.utc),
        records=payload,
    )
