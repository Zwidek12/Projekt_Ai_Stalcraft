from __future__ import annotations

from unittest.mock import Mock, patch

from stalcraft_market_analyzer.ingestion.exbo_api import ExboApiConfig, ExboAuctionClient


def test_exbo_client_uses_secret_headers_and_fetches_history_and_lots() -> None:
    client = ExboAuctionClient(
        config=ExboApiConfig(
            api_base_url="https://dapi.stalcraft.net",
            region="EU",
            client_id="1",
            client_secret="secret",
        )
    )

    history_response = Mock()
    history_response.raise_for_status.return_value = None
    history_response.json.return_value = {
        "total": 1,
        "prices": [{"amount": 1, "price": 1000, "time": "2026-05-09T10:00:00Z", "additional": {"qlt": 4}}],
    }
    lots_response = Mock()
    lots_response.raise_for_status.return_value = None
    lots_response.json.return_value = {
        "total": 1,
        "lots": [
            {
                "itemId": "wg3p",
                "amount": 1,
                "startPrice": 100,
                "buyoutPrice": 900,
                "startTime": "2026-05-09T10:00:00Z",
                "endTime": "2026-05-10T10:00:00Z",
                "additional": {"qlt": 5},
            }
        ],
    }

    with patch.object(client._session, "get", side_effect=[history_response, lots_response]) as mocked_get:
        records = client.fetch_market_records(item_id="wg3p", item_name="Disintegrator")

    assert client._session.headers["Client-Id"] == "1"
    assert client._session.headers["Client-Secret"] == "secret"
    assert [record.source for record in records] == ["exbo_auction_history", "exbo_auction_lot"]
    assert [record.rarity for record in records] == ["exclusive", "legendary"]
    assert mocked_get.call_count == 2
