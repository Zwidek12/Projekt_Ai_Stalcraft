from __future__ import annotations

from pathlib import Path

from stalcraft_market_analyzer.ingestion.parsers import (
    parse_api_history,
    parse_exbo_active_lots,
    parse_exbo_auction_history,
    parse_html_market_table,
    parse_stalcraftdb_auction_history,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_api_history_valid_rows() -> None:
    payload = {
        "item_name": "AK-103",
        "history": [
            {"price": 12000, "volume": 5, "timestamp": "2026-04-28T18:00:00Z"},
            {"price": "13000", "volume": "9", "timestamp": "2026-04-28T19:00:00Z"},
        ],
    }

    records = parse_api_history(item_id="ak-103", payload=payload)
    assert len(records) == 2
    assert records[0].item_name == "AK-103"
    assert records[0].source == "json_api"
    assert records[1].price == 13000.0
    assert records[1].volume == 9


def test_parse_api_history_skips_invalid_rows() -> None:
    payload = {
        "item_name": "AK-103",
        "history": [{"price": "bad", "volume": 2, "timestamp": "2026-04-28T18:00:00Z"}],
    }

    records = parse_api_history(item_id="ak-103", payload=payload)
    assert records == []


def test_parse_html_market_table_valid() -> None:
    html = (FIXTURES_DIR / "market_history_valid.html").read_text(encoding="utf-8")
    records = parse_html_market_table(item_id="veteran-armor", html=html)
    assert len(records) == 2
    assert records[0].item_name == "Veteran Armor"
    assert records[0].price == 12500.0
    assert records[0].volume == 8
    assert records[0].source == "html_table"


def test_parse_html_market_table_handles_missing_table() -> None:
    html = "<html><body><h1 class='item-title'>X</h1></body></html>"
    records = parse_html_market_table(item_id="x", html=html)
    assert records == []


def test_parse_html_market_table_skips_row_with_missing_cells() -> None:
    html = (FIXTURES_DIR / "market_history_missing_cells.html").read_text(encoding="utf-8")
    records = parse_html_market_table(item_id="broken", html=html)
    assert len(records) == 1
    assert records[0].volume == 10


def test_parse_stalcraftdb_auction_history_extracts_quality() -> None:
    records = parse_stalcraftdb_auction_history(
        item_id="wg3p",
        item_name="Disintegrator",
        history_payload={
            "prices": [
                {
                    "price": 600000,
                    "amount": 1,
                    "time": "2026-05-09T10:00:00Z",
                    "additional": {"qlt": 4},
                }
            ]
        },
    )
    assert len(records) == 1
    assert records[0].rarity == "exclusive"


def test_parse_exbo_auction_history_extracts_quality() -> None:
    records = parse_exbo_auction_history(
        item_id="wg3p",
        item_name="Disintegrator",
        history_payload={
            "prices": [
                {
                    "price": 600000,
                    "amount": 1,
                    "time": "2026-05-09T10:00:00Z",
                    "additional": {"qlt": 5},
                }
            ]
        },
    )

    assert len(records) == 1
    assert records[0].source == "exbo_auction_history"
    assert records[0].rarity == "legendary"


def test_parse_exbo_active_lots_uses_buyout_price_and_quality() -> None:
    records = parse_exbo_active_lots(
        item_id="wg3p",
        item_name="Disintegrator",
        lots_payload={
            "lots": [
                {
                    "itemId": "wg3p",
                    "amount": 1,
                    "startPrice": 100,
                    "currentPrice": 200,
                    "buyoutPrice": 700000,
                    "startTime": "2026-05-09T10:00:00Z",
                    "endTime": "2026-05-10T10:00:00Z",
                    "additional": {"qlt": 6},
                }
            ]
        },
        observed_at=parse_exbo_auction_history(
            item_id="dummy",
            item_name="dummy",
            history_payload={"prices": [{"price": 1, "amount": 1, "time": "2026-05-09T10:00:00Z"}]},
        )[0].observed_at,
    )

    assert len(records) == 1
    assert records[0].source == "exbo_auction_lot"
    assert records[0].price == 700000.0
    assert records[0].rarity == "unique"
