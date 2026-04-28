from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .parsers import MarketPriceRecord, parse_api_history, parse_html_market_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScraperConfig:
    base_url: str
    timeout_seconds: int = 15
    max_retries: int = 3
    backoff_factor: float = 0.5


class StalcraftPriceScraper:
    """API-first scraper with HTML fallback and JS-only extension point."""

    def __init__(self, config: ScraperConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._timeout_seconds = config.timeout_seconds
        self._session = self._build_session(config=config)

    def fetch_prices(self, item_ids: list[str]) -> list[MarketPriceRecord]:
        output: list[MarketPriceRecord] = []
        for item_id in item_ids:
            api_payload = self._try_fetch_api(item_id=item_id)
            if api_payload is not None:
                api_records = parse_api_history(item_id=item_id, payload=api_payload)
                if api_records:
                    output.extend(api_records)
                    continue

            html_page = self._try_fetch_html(item_id=item_id)
            if html_page is not None:
                html_records = parse_html_market_table(item_id=item_id, html=html_page)
                if html_records:
                    output.extend(html_records)
                    continue

            output.extend(self._js_only_fallback(item_id=item_id))
        return output

    def _try_fetch_api(self, item_id: str) -> dict[str, Any] | None:
        endpoint = f"{self._base_url}/api/market/items/{item_id}/prices"
        try:
            response = self._session.get(endpoint, timeout=self._timeout_seconds)
            response.raise_for_status()
            parsed = response.json()
            if not isinstance(parsed, dict):
                logger.warning("API response is not a JSON object for %s", item_id)
                return None
            return parsed
        except requests.RequestException as error:
            logger.warning("API fetch failed for %s: %s", item_id, error)
            return None
        except ValueError as error:
            logger.warning("API JSON decode failed for %s: %s", item_id, error)
            return None

    def _try_fetch_html(self, item_id: str) -> str | None:
        page_url = f"{self._base_url}/market/items/{item_id}"
        try:
            response = self._session.get(page_url, timeout=self._timeout_seconds)
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            logger.warning("HTML fetch failed for %s: %s", item_id, error)
            return None

    def _build_session(self, config: ScraperConfig) -> requests.Session:
        retry = Retry(
            total=config.max_retries,
            connect=config.max_retries,
            read=config.max_retries,
            status=config.max_retries,
            backoff_factor=config.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _js_only_fallback(self, item_id: str) -> list[MarketPriceRecord]:
        # Extension point for future Playwright implementation.
        logger.info("Using JS-only mock fallback for %s", item_id)
        return [
            MarketPriceRecord(
                item_id=item_id,
                item_name=f"item_{item_id}",
                price=0.0,
                volume=0,
                observed_at=datetime.now(timezone.utc),
                source="mock_js_fallback",
            )
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = StalcraftPriceScraper(config=ScraperConfig(base_url="https://stalcraftdb.example.com"))
    result = scraper.fetch_prices(item_ids=["ak-103", "veteran-armor"])
    for row in result:
        print(row)
