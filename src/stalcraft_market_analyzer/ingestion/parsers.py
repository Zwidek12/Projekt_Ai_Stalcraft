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
    rarity: str = "unknown"


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


def parse_stalcraftdb_item_name(item_payload: dict[str, Any], *, item_id: str) -> str:
    name = item_payload.get("name")
    if isinstance(name, dict):
        lines = name.get("lines")
        if isinstance(lines, dict):
            en_value = lines.get("en")
            if isinstance(en_value, str) and en_value.strip():
                return en_value.strip()
    return f"item_{item_id}"


def parse_stalcraftdb_auction_history(
    *,
    item_id: str,
    item_name: str,
    history_payload: dict[str, Any],
) -> list[MarketPriceRecord]:
    prices = history_payload.get("prices")
    if not isinstance(prices, list):
        logger.warning("Missing or invalid auction prices list for %s", item_id)
        return []

    records: list[MarketPriceRecord] = []
    for row in prices:
        if not isinstance(row, dict):
            continue
        price = _safe_float(row.get("price"))
        amount = _safe_int(row.get("amount"))
        time_value = row.get("time")
        rarity = _rarity_from_additional(row.get("additional"))
        if price is None or amount is None:
            continue
        observed_at = parse_datetime(time_value)
        records.append(
            MarketPriceRecord(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=amount,
                observed_at=observed_at,
                source="stalcraftdb_auction",
                rarity=rarity,
            )
        )
    return records


def parse_exbo_auction_history(
    *,
    item_id: str,
    item_name: str,
    history_payload: dict[str, Any],
) -> list[MarketPriceRecord]:
    prices = history_payload.get("prices")
    if not isinstance(prices, list):
        logger.warning("Missing or invalid EXBO auction prices list for %s", item_id)
        return []

    records: list[MarketPriceRecord] = []
    for row in prices:
        if not isinstance(row, dict):
            continue
        price = _safe_float(row.get("price"))
        amount = _safe_int(row.get("amount"))
        if price is None or amount is None:
            continue
        records.append(
            MarketPriceRecord(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=amount,
                observed_at=parse_datetime(row.get("time")),
                source="exbo_auction_history",
                rarity=_rarity_from_additional(row.get("additional")),
            )
        )
    return records


def parse_exbo_active_lots(
    *,
    item_id: str,
    item_name: str,
    lots_payload: dict[str, Any],
    observed_at: datetime,
) -> list[MarketPriceRecord]:
    lots = lots_payload.get("lots")
    if not isinstance(lots, list):
        logger.warning("Missing or invalid EXBO auction lots list for %s", item_id)
        return []

    records: list[MarketPriceRecord] = []
    for row in lots:
        if not isinstance(row, dict):
            continue
        price = _lot_market_price(row)
        amount = _safe_int(row.get("amount"))
        if price is None or amount is None:
            continue
        records.append(
            MarketPriceRecord(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=amount,
                observed_at=observed_at,
                source="exbo_auction_lot",
                rarity=_rarity_from_additional(row.get("additional")),
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


def _lot_market_price(row: dict[str, Any]) -> float | None:
    for key in ("buyoutPrice", "currentPrice", "startPrice"):
        price = _safe_float(row.get(key))
        if price is not None and price > 0:
            return price
    return None


def _rarity_from_additional(value: Any) -> str:
    if not isinstance(value, dict):
        return "unknown"
    qlt = value.get("qlt")
    if qlt is None:
        return "unknown"
    try:
        qlt_int = int(qlt)
    except (TypeError, ValueError):
        return "unknown"
    return {
        0: "common",
        1: "uncommon",
        2: "special",
        3: "rare",
        4: "exclusive",
        5: "legendary",
        6: "unique",
    }.get(qlt_int, "unknown")
