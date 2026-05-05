from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .parsers import (
    MarketPriceRecord,
    parse_api_history,
    parse_html_market_table,
    parse_stalcraftdb_auction_history,
    parse_stalcraftdb_item_name,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScraperConfig:
    base_url: str
    region: str = "eu"
    timeout_seconds: int = 15
    max_retries: int = 3
    backoff_factor: float = 0.5


class StalcraftPriceScraper:
    """API-first scraper with HTML fallback and JS-only extension point."""

    def __init__(self, config: ScraperConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._region = config.region
        self._timeout_seconds = config.timeout_seconds
        self._session = self._build_session(config=config)
        self._api_origin = self._derive_api_origin(self._base_url)

    def fetch_prices(self, item_ids: list[str]) -> list[MarketPriceRecord]:
        output: list[MarketPriceRecord] = []
        for item_id in item_ids:
            resolved_id = self._resolve_item_id(item_id)
            if resolved_id != item_id:
                logger.info("Resolved item token '%s' -> '%s'", item_id, resolved_id)

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

            # StalcraftDB supports auction-history endpoint; use it as a fallback if base_url points to stalcraftdb.net.
            if self._api_origin and resolved_id:
                auction_records = self._try_fetch_stalcraftdb_auction(item_id=resolved_id)
                if auction_records:
                    output.extend(auction_records)
                    continue

            output.extend(self._js_only_fallback(item_id=resolved_id))
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

    def _try_fetch_stalcraftdb_auction(self, *, item_id: str) -> list[MarketPriceRecord]:
        if not self._api_origin:
            return []

        try:
            item_resp = self._session.get(
                f"{self._api_origin}/api/items/{item_id}?region={self._region}",
                timeout=self._timeout_seconds,
            )
            item_resp.raise_for_status()
            item_payload = item_resp.json()
            if not isinstance(item_payload, dict):
                return []
            item_name = parse_stalcraftdb_item_name(item_payload, item_id=item_id)

            hist_resp = self._session.get(
                f"{self._api_origin}/api/items/{item_id}/auction-history?region={self._region}&page=0",
                timeout=self._timeout_seconds,
            )
            hist_resp.raise_for_status()
            hist_payload = hist_resp.json()
            if not isinstance(hist_payload, dict):
                return []

            return parse_stalcraftdb_auction_history(
                item_id=item_id,
                item_name=item_name,
                history_payload=hist_payload,
            )
        except requests.RequestException as error:
            logger.warning("StalcraftDB auction fetch failed for %s: %s", item_id, error)
            return []
        except ValueError as error:
            logger.warning("StalcraftDB JSON decode failed for %s: %s", item_id, error)
            return []

    def _resolve_item_id(self, token: str) -> str:
        """
        Resolve human input into StalcraftDB item id when possible.

        - If token already looks like an item id (4-6 lowercase alnum), keep it.
        - Else try lookup via listing endpoint by English name matching.
        """
        normalized = token.strip()
        if re.fullmatch(r"[a-z0-9]{4,6}", normalized):
            return normalized
        if not self._api_origin:
            return normalized

        try:
            listing = self._session.get(
                f"{self._api_origin}/api/listing/{self._region}/grouped?",
                timeout=self._timeout_seconds,
            ).json()
        except (requests.RequestException, ValueError):
            return normalized

        if not isinstance(listing, dict):
            return normalized

        query = normalized.lower().replace("-", " ").strip()
        best_id: str | None = None
        for _, items in listing.items():
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                item_id = it.get("id")
                if not isinstance(item_id, str):
                    continue
                name = it.get("name")
                en = ""
                if isinstance(name, dict):
                    lines = name.get("lines")
                    if isinstance(lines, dict) and isinstance(lines.get("en"), str):
                        en = lines["en"].lower()
                if en and (en == query or query in en):
                    best_id = item_id
                    if en == query:
                        return item_id
        return best_id or normalized

    @staticmethod
    def _derive_api_origin(base_url: str) -> str | None:
        parsed = urlparse(base_url)
        if not parsed.netloc:
            return None
        if "stalcraftdb.net" in parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
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
