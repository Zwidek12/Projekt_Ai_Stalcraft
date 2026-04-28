from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from stalcraft_market_analyzer.ingestion.exporter import build_quality_report, write_raw_snapshot
from stalcraft_market_analyzer.ingestion.parsers import MarketPriceRecord


def _sample_records() -> list[MarketPriceRecord]:
    now = datetime(2026, 4, 28, 18, 0, tzinfo=timezone.utc)
    return [
        MarketPriceRecord("ak-103", "AK-103", 12000.0, 5, now, "json_api"),
        MarketPriceRecord("armor", "Armor", 10000.0, 3, now, "html_table"),
        MarketPriceRecord("scope", "Scope", 0.0, 0, now, "mock_js_fallback"),
    ]


def test_build_quality_report_counts_by_source() -> None:
    report = build_quality_report(_sample_records())
    assert report.total_records == 3
    assert report.json_api_records == 1
    assert report.html_table_records == 1
    assert report.mock_js_fallback_records == 1


def test_write_raw_snapshot_creates_json_file(tmp_path: Path) -> None:
    result = write_raw_snapshot(records=_sample_records(), output_dir=tmp_path)
    assert result.output_path.exists()
    content = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert content["snapshot_id"] == result.snapshot_id
    assert len(content["records"]) == 3
