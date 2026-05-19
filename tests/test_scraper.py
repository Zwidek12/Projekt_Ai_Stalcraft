from __future__ import annotations

from unittest.mock import Mock, patch

import requests

from stalcraft_market_analyzer.ingestion.scraper import ScraperConfig, StalcraftPriceScraper


def test_scraper_uses_api_first() -> None:
    scraper = StalcraftPriceScraper(config=ScraperConfig(base_url="https://example.com"))
    api_response = Mock()
    api_response.raise_for_status.return_value = None
    api_response.json.return_value = {
        "item_name": "AK-103",
        "history": [{"price": 11000, "volume": 6, "timestamp": "2026-04-28T18:00:00Z"}],
    }

    with patch.object(scraper._session, "get", return_value=api_response):
        records = scraper.fetch_prices(["ak-103"])

    assert len(records) == 1
    assert records[0].source == "json_api"


def test_scraper_falls_back_to_html_when_api_fails() -> None:
    scraper = StalcraftPriceScraper(config=ScraperConfig(base_url="https://example.com"))

    def _mocked_get(url: str, timeout: int) -> Mock:
        if "/api/" in url:
            error_response = Mock()
            error_response.raise_for_status.side_effect = requests.RequestException("api fail")
            return error_response
        html_response = Mock()
        html_response.raise_for_status.return_value = None
        html_response.text = """
        <html><body>
            <h1 class="item-title">AK-103</h1>
            <table class="market-history"><tbody>
                <tr><td>2026-04-28T18:00:00Z</td><td>10,000</td><td>4</td></tr>
            </tbody></table>
        </body></html>
        """
        return html_response

    with patch.object(scraper._session, "get", side_effect=_mocked_get):
        records = scraper.fetch_prices(["ak-103"])

    assert len(records) == 1
    assert records[0].source == "html_table"


def test_scraper_uses_mock_fallback_when_no_sources() -> None:
    scraper = StalcraftPriceScraper(config=ScraperConfig(base_url="https://example.com"))

    def _always_fail(url: str, timeout: int) -> Mock:
        response = Mock()
        response.raise_for_status.side_effect = requests.RequestException("fail")
        return response

    with patch.object(scraper._session, "get", side_effect=_always_fail):
        records = scraper.fetch_prices(["ak-103"])

    assert len(records) == 1
    assert records[0].source == "mock_js_fallback"


def test_scraper_stalcraftdb_skips_generic_api_and_html_probes() -> None:
    scraper = StalcraftPriceScraper(config=ScraperConfig(base_url="https://stalcraftdb.net/eu", region="eu"))

    item_response = Mock()
    item_response.raise_for_status.return_value = None
    item_response.json.return_value = {
        "name": {"lines": {"en": "AK-103"}},
    }

    hist_response = Mock()
    hist_response.raise_for_status.return_value = None
    hist_response.json.return_value = {
        "prices": [
            {
                "price": 11000,
                "amount": 6,
                "time": "2026-04-28T18:00:00Z",
            }
        ]
    }

    calls: list[str] = []

    def _mocked_get(url: str, *args: object, **kwargs: object) -> Mock:
        calls.append(url)
        if "/auction-history" in url:
            return hist_response
        if "/api/items/v7ar" in url and "region=eu" in url:
            return item_response
        raise AssertionError(f"Unexpected URL in test: {url}")

    with patch.object(scraper._session, "get", side_effect=_mocked_get):
        records = scraper.fetch_prices(["v7ar"])

    assert len(records) == 1
    assert records[0].source == "stalcraftdb_auction"

    assert not any("/api/market/" in u for u in calls)
    assert not any("/market/items/" in u for u in calls)
