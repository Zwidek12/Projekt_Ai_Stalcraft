from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from .parsers import MarketPriceRecord


class RawMarketRecord(TypedDict):
    item_id: str
    item_name: str
    price: float
    volume: int
    observed_at: str
    source: str


@dataclass(frozen=True)
class DataQualityReport:
    total_records: int
    json_api_records: int
    html_table_records: int
    mock_js_fallback_records: int


@dataclass(frozen=True)
class SnapshotWriteResult:
    snapshot_id: str
    output_path: Path


def to_raw_market_record(record: MarketPriceRecord) -> RawMarketRecord:
    return RawMarketRecord(
        item_id=record.item_id,
        item_name=record.item_name,
        price=record.price,
        volume=record.volume,
        observed_at=record.observed_at.isoformat(),
        source=record.source,
    )


def build_quality_report(records: list[MarketPriceRecord]) -> DataQualityReport:
    source_counts: dict[str, int] = {
        "json_api": 0,
        "html_table": 0,
        "mock_js_fallback": 0,
    }
    for record in records:
        if record.source in source_counts:
            source_counts[record.source] += 1

    return DataQualityReport(
        total_records=len(records),
        json_api_records=source_counts["json_api"],
        html_table_records=source_counts["html_table"],
        mock_js_fallback_records=source_counts["mock_js_fallback"],
    )


def write_raw_snapshot(records: list[MarketPriceRecord], output_dir: Path) -> SnapshotWriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc)
    snapshot_id = f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    output_path = output_dir / f"market_snapshot_{snapshot_id}.json"

    payload = {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at.isoformat(),
        "records": [to_raw_market_record(record) for record in records],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SnapshotWriteResult(snapshot_id=snapshot_id, output_path=output_path)
