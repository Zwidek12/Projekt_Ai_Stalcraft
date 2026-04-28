# Repository Input Contract (handover for Luxber)

## Purpose
This contract defines the payload that ingestion provides to `repository.py`.

## Python contract location
- `src/stalcraft_market_analyzer/storage/repository_contract.py`

## Main types
1. `RepositoryPriceRecord`
   - `item_id: str`
   - `item_name: str`
   - `price: float`
   - `volume: int`
   - `observed_at: datetime`
   - `source: str`
2. `IngestionBatch`
   - `snapshot_id: str`
   - `collected_at: datetime`
   - `records: list[RepositoryPriceRecord]`

## Builder helper
Use:
- `build_ingestion_batch(snapshot_id: str, records: list[MarketPriceRecord]) -> IngestionBatch`

## Repository protocol
Expected implementation in future `repository.py`:
- `save_ingestion_batch(batch: IngestionBatch) -> int`
