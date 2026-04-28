from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketPriceRecord:
    item_id: str
    item_name: str
    price: float
    volume: int
    observed_at: datetime
    source: str


def parse_api_history(item_id: str, payload: dict[str, Any]) -> list[MarketPriceRecord]:
    item_name_value = payload.get("item_name")
    item_name = str(item_name_value) if item_name_value else f"item_{item_id}"
    history = payload.get("history")
    if not isinstance(history, list):
        logger.warning("Missing or invalid API history for %s", item_id)
        return []

    records: list[MarketPriceRecord] = []
    for row in history:
        if not isinstance(row, dict):
            logger.warning("Skipping invalid API row type for %s", item_id)
            continue

        price = _safe_float(row.get("price"))
        volume = _safe_int(row.get("volume"))
        if price is None or volume is None:
            logger.warning("Skipping row with invalid price/volume for %s", item_id)
            continue

        observed_at = parse_datetime(value=row.get("timestamp"))
        records.append(
            MarketPriceRecord(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=volume,
                observed_at=observed_at,
                source="json_api",
            )
        )
    return records


def parse_html_market_table(item_id: str, html: str) -> list[MarketPriceRecord]:
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one("h1.item-title")
    item_name = title_node.get_text(strip=True) if title_node else f"item_{item_id}"

    table = soup.select_one("table.market-history")
    if table is None:
        logger.warning("No market table found for %s", item_id)
        return []

    rows: list[MarketPriceRecord] = []
    for row in table.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 3:
            logger.warning("Skipping malformed row for %s", item_id)
            continue

        observed_at = parse_datetime(cols[0].get_text(strip=True))
        price = _safe_float(_normalize_number_text(cols[1].get_text(strip=True)))
        volume = _safe_int(_normalize_number_text(cols[2].get_text(strip=True)))
        if price is None or volume is None:
            logger.warning("Skipping row with invalid values for %s", item_id)
            continue

        rows.append(
            MarketPriceRecord(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=volume,
                observed_at=observed_at,
                source="html_table",
            )
        )
    return rows


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Invalid datetime value: %s", value)
    return datetime.now(timezone.utc)


def _normalize_number_text(value: str) -> str:
    return value.replace(",", "").replace(" ", "")


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
