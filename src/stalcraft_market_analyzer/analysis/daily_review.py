from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from stalcraft_market_analyzer.analysis.price_stats import filter_price_outliers
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import CatalogItemInput, MarketDealInput, PriceObservation


@dataclass(frozen=True, slots=True)
class DailyReviewConfig:
    recent_days: int = 30
    min_samples_7d: int = 3
    deal_deviation_pct: float = -25.0
    limit: int = 250
    artifact_only: bool = False
    hot_rarities: frozenset[str] = frozenset({"pink", "red", "gold"})
    outlier_iqr_multiplier: float = 1.5


@dataclass(frozen=True, slots=True)
class DailyReviewResult:
    review_id: str
    scanned_items: int
    deals_found: int
    deals_saved: int


def run_daily_market_review(
    *,
    repo: SqlAlchemyRepository,
    now: datetime | None = None,
    config: DailyReviewConfig | None = None,
    base_url: str = "",
) -> DailyReviewResult:
    cfg = config or DailyReviewConfig()
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    review_id = now_utc.strftime("daily-%Y%m%dT%H%M%SZ")

    item_ids = _review_targets(repo=repo, now=now_utc, config=cfg)
    deals: list[MarketDealInput] = []
    catalog_updates: list[CatalogItemInput] = []

    for item_id in item_ids:
        observations_7d = _clean_observations(
            repo.get_price_observations_since(item_id=item_id, since=now_utc - timedelta(days=7))
        )
        if len(observations_7d) < cfg.min_samples_7d:
            continue

        latest = observations_7d[-1]
        latest_price = float(latest["price"])
        prices_7d = _average_prices(
            observations_7d,
            iqr_multiplier=cfg.outlier_iqr_multiplier,
        )
        if len(prices_7d) < cfg.min_samples_7d:
            continue

        avg_7d = _average(prices_7d)
        if avg_7d <= 0:
            continue

        observations_1d = [
            row for row in observations_7d if _as_utc(row["observed_at"]) >= now_utc - timedelta(days=1)
        ]
        prices_1d = _average_prices(
            observations_1d,
            iqr_multiplier=cfg.outlier_iqr_multiplier,
        )
        avg_1d = _average(prices_1d) or latest_price
        deviation_pct = ((latest_price - avg_7d) / avg_7d) * 100.0
        if deviation_pct > cfg.deal_deviation_pct:
            continue

        history_rows = repo.get_price_history_since(item_id=item_id, since=now_utc - timedelta(days=7))
        latest_row = _latest_valid_history_row(history_rows)
        item_name = latest_row.item_name if latest_row is not None else item_id
        catalog_item = repo.get_catalog_item(item_id=item_id) or _catalog_for_item(
            item_id=item_id,
            item_name=item_name,
            base_url=base_url,
        )
        catalog_updates.append(catalog_item)
        deal_rarity = _deal_rarity(latest=latest, catalog_item=catalog_item, latest_row=latest_row)

        deals.append(
            MarketDealInput(
                item_id=item_id,
                item_name=item_name,
                rarity=deal_rarity,
                category=str(catalog_item.get("category", "unknown")),
                external_url=str(catalog_item.get("external_url", "")),
                is_artifact=bool(catalog_item.get("is_artifact", False)),
                current_price=latest_price,
                avg_price_1d=avg_1d,
                avg_price_7d=avg_7d,
                deviation_pct=deviation_pct,
                deal_score=_deal_score(deviation_pct=deviation_pct, current_price=latest_price, avg_price_7d=avg_7d),
                observed_at=_as_utc(latest["observed_at"]),
                source=str(latest["source"]),
            )
        )

    if catalog_updates:
        repo.upsert_item_catalog(items=catalog_updates, updated_at=now_utc)

    deals_sorted = sorted(deals, key=lambda row: float(row["deal_score"]), reverse=True)
    if cfg.artifact_only:
        deals_sorted = [
            deal
            for deal in deals_sorted
            if bool(deal["is_artifact"]) and str(deal["rarity"]).lower() in cfg.hot_rarities
        ]
    deals_limited = deals_sorted[: max(1, cfg.limit)]
    saved = repo.save_market_deals(review_id=review_id, deals=deals_limited, created_at=now_utc)

    return DailyReviewResult(
        review_id=review_id,
        scanned_items=len(item_ids),
        deals_found=len(deals_sorted),
        deals_saved=saved,
    )


def _review_targets(*, repo: SqlAlchemyRepository, now: datetime, config: DailyReviewConfig) -> list[str]:
    catalog_items = repo.get_catalog_items(artifact_only=config.artifact_only)
    if catalog_items:
        return [str(item["item_id"]) for item in catalog_items if str(item.get("item_id", "")).strip()]
    return repo.get_distinct_item_ids(since=now - timedelta(days=max(1, config.recent_days)))


def _clean_observations(rows: list[PriceObservation]) -> list[PriceObservation]:
    out: list[PriceObservation] = []
    for row in rows:
        price = float(row["price"])
        source = str(row["source"])
        if price <= 0:
            continue
        if source == "mock_js_fallback":
            continue
        out.append(row)
    return out


def _latest_valid_history_row(rows: list[object]) -> object | None:
    for row in reversed(rows):
        price = float(getattr(row, "price", 0.0))
        source = str(getattr(row, "source", ""))
        if price > 0 and source != "mock_js_fallback":
            return row
    return None


def _latest_record_rarity(row: object | None) -> str:
    if row is None:
        return "unknown"
    return str(getattr(row, "rarity", "unknown") or "unknown").lower()


def _deal_rarity(
    *,
    latest: PriceObservation,
    catalog_item: dict[str, object],
    latest_row: object | None,
) -> str:
    for candidate in (latest.get("rarity"), _latest_record_rarity(latest_row), catalog_item.get("rarity")):
        rarity = str(candidate or "unknown").strip().lower()
        if rarity != "unknown":
            return rarity
    return "unknown"


def _catalog_for_item(*, item_id: str, item_name: str, base_url: str) -> CatalogItemInput:
    url_base = base_url.rstrip("/")
    external_url = f"{url_base}/items/{item_id}" if url_base else ""
    return CatalogItemInput(
        item_id=item_id,
        item_name=item_name,
        rarity="unknown",
        category="unknown",
        external_url=external_url,
        is_artifact=False,
    )


def _average_prices(
    observations: list[PriceObservation],
    *,
    iqr_multiplier: float,
) -> list[float]:
    if not observations:
        return []

    prices = [float(row["price"]) for row in observations]
    if len(prices) == 1:
        return prices

    baseline_prices = filter_price_outliers(prices[:-1], iqr_multiplier=iqr_multiplier)
    return baseline_prices + [prices[-1]]


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _deal_score(*, deviation_pct: float, current_price: float, avg_price_7d: float) -> float:
    absolute_discount = max(0.0, avg_price_7d - current_price)
    return abs(float(deviation_pct)) + (absolute_discount / max(1.0, avg_price_7d)) * 100.0
