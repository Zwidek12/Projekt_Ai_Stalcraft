from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .exbo_rate_limit import retry_after_seconds, throttle_before_request
from .parsers import MarketPriceRecord, parse_exbo_active_lots, parse_exbo_auction_history

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExboApiConfig:
    api_base_url: str = "https://eapi.stalcraft.net"
    region: str = "EU"
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    timeout_seconds: int = 15
    max_retries: int = 3
    backoff_factor: float = 0.5
    rate_limit_max_retries: int = 6
    rate_limit_backoff_s: float = 2.0
    min_request_interval_s: float = 0.0
    history_limit: int = 20
    lots_limit: int = 20

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token.strip() or (self.client_id.strip() and self.client_secret.strip()))


class ExboAuctionClient:
    def __init__(self, config: ExboApiConfig) -> None:
        self._config = config
        self._api_base_url = config.api_base_url.rstrip("/")
        self._region = config.region.strip().upper() or "EU"
        self._session = self._build_session(config=config)
        self._last_request_monotonic: float | None = None

    def fetch_market_records(self, *, item_id: str, item_name: str) -> list[MarketPriceRecord]:
        if not self._config.is_configured:
            return []

        records: list[MarketPriceRecord] = []
        history_payload = self._get_json(
            path=f"/{self._region}/auction/{item_id}/history",
            params={
                "additional": "true",
                "limit": str(max(1, min(self._config.history_limit, 200))),
            },
        )
        if history_payload is not None:
            records.extend(
                parse_exbo_auction_history(
                    item_id=item_id,
                    item_name=item_name,
                    history_payload=history_payload,
                )
            )

        lots_payload = self._get_json(
            path=f"/{self._region}/auction/{item_id}/lots",
            params={
                "additional": "true",
                "limit": str(max(1, min(self._config.lots_limit, 200))),
                "sort": "buyout_price",
                "order": "asc",
            },
        )
        if lots_payload is not None:
            records.extend(
                parse_exbo_active_lots(
                    item_id=item_id,
                    item_name=item_name,
                    lots_payload=lots_payload,
                    observed_at=datetime.now(timezone.utc),
                )
            )

        return records

    def _get_json(self, *, path: str, params: dict[str, str]) -> dict[str, Any] | None:
        url = f"{self._api_base_url}{path}"
        max_attempts = max(1, self._config.rate_limit_max_retries + 1)

        for attempt_idx in range(max_attempts):
            self._last_request_monotonic = throttle_before_request(
                last_request_monotonic=self._last_request_monotonic,
                min_interval_s=self._config.min_request_interval_s,
            )
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self._config.timeout_seconds,
                )
            except requests.RequestException as error:
                logger.warning("EXBO auction fetch failed for %s: %s", path, error)
                return None

            if response.status_code == 429:
                fallback = self._config.rate_limit_backoff_s * (2**attempt_idx)
                wait_s = retry_after_seconds(response, fallback_s=fallback)
                logger.warning(
                    "EXBO rate limited for %s: attempt=%s/%s wait_s=%.2f",
                    path,
                    attempt_idx + 1,
                    max_attempts,
                    wait_s,
                )
                if attempt_idx + 1 >= max_attempts:
                    return None
                time.sleep(wait_s)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                logger.warning("EXBO auction fetch failed for %s: %s", path, error)
                return None

            try:
                payload = response.json()
            except ValueError as error:
                logger.warning("EXBO JSON decode failed for %s: %s", path, error)
                return None

            if not isinstance(payload, dict):
                logger.warning("EXBO response is not a JSON object for %s", path)
                return None
            return payload

        return None

    def _build_session(self, *, config: ExboApiConfig) -> requests.Session:
        retry = Retry(
            total=config.max_retries,
            connect=config.max_retries,
            read=config.max_retries,
            status=config.max_retries,
            backoff_factor=config.backoff_factor,
            # 429 is handled explicitly in _get_json (Retry-After + longer backoff).
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self._auth_headers(config=config))
        return session

    @staticmethod
    def _auth_headers(*, config: ExboApiConfig) -> dict[str, str]:
        token = config.access_token.strip()
        if token:
            return {"Authorization": f"Bearer {token}"}

        client_id = config.client_id.strip()
        client_secret = config.client_secret.strip()
        if client_id and client_secret:
            return {"Client-Id": client_id, "Client-Secret": client_secret}

        return {}
