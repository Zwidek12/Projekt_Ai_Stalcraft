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


def test_exbo_client_retries_on_rate_limit_with_retry_after() -> None:
    client = ExboAuctionClient(
        config=ExboApiConfig(
            client_id="1",
            client_secret="secret",
            rate_limit_max_retries=2,
            rate_limit_backoff_s=1.0,
            min_request_interval_s=0.0,
        )
    )

    rate_limited = Mock()
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "0"}
    rate_limited.raise_for_status.side_effect = None

    ok_response = Mock()
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"total": 0, "prices": []}

    with patch.object(client._session, "get", side_effect=[rate_limited, ok_response]) as mocked_get:
        with patch("stalcraft_market_analyzer.ingestion.exbo_api.time.sleep") as mocked_sleep:
            payload = client._get_json(path="/EU/auction/wg3p/history", params={"additional": "true"})

    assert payload == {"total": 0, "prices": []}
    assert mocked_get.call_count == 2
    mocked_sleep.assert_called_once()
