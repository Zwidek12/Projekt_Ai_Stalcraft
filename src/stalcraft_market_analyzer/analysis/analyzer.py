from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from stalcraft_market_analyzer.storage.repository_contract import PriceHistoryRepository

AnomalyKind = Literal["price_deal", "price_spike"]


@dataclass(frozen=True, slots=True)
class AnomalyScanConfig:
    baseline_days: int = 7
    min_samples: int = 6
    deal_deviation_pct: float = -35.0
    spike_deviation_pct: float = 60.0


@dataclass(frozen=True, slots=True)
class PriceAnomalySignal:
    kind: AnomalyKind
    item_id: str
    item_name: str
    latest_price: float
    baseline_median: float
    deviation_pct: float
    severity: Literal["critical", "high", "medium", "low"]
    observed_at: datetime
    source: str


def scan_price_anomalies(
    *,
    repo: PriceHistoryRepository,
    item_ids: list[str],
    now: datetime | None = None,
    config: AnomalyScanConfig | None = None,
) -> list[PriceAnomalySignal]:
    cfg = config or AnomalyScanConfig()
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    signals: list[PriceAnomalySignal] = []
    for item_id in item_ids:
        signal = _detect_for_item(repo=repo, item_id=item_id, now=now_utc, config=cfg)
        if signal is None:
            continue
        signals.append(signal)
    return signals


def build_price_anomaly_fingerprint(*, signal: PriceAnomalySignal, now: datetime) -> str:
    """
    Dedupe key for alert spam control.

    Bucketed by UTC day + coarse median bucket so repeats across a day collapse,
    but meaningfully different regimes get a new fingerprint.
    """
    day = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    median_bucket = int(round(signal.baseline_median / 250_000.0))
    return f"{signal.kind}|{signal.item_id}|d={day}|mb={median_bucket}"


def _detect_for_item(
    *,
    repo: PriceHistoryRepository,
    item_id: str,
    now: datetime,
    config: AnomalyScanConfig,
) -> PriceAnomalySignal | None:
    baseline_since = now - timedelta(days=config.baseline_days)
    observations = repo.get_price_observations_since(item_id=item_id, since=baseline_since)
    filtered: list[tuple[float, datetime, str]] = []
    for observation in observations:
        price = float(observation["price"])
        source = str(observation["source"])
        if price <= 0:
            continue
        if source == "mock_js_fallback":
            continue
        filtered.append((price, observation["observed_at"], source))

    prices_chronological = [row[0] for row in filtered]

    if len(prices_chronological) < config.min_samples:
        return None

    latest_price, latest_observed_at, latest_source = filtered[-1]
    baseline_rows = filtered[:-1]
    baseline_prices = [row[0] for row in baseline_rows]
    if not baseline_prices:
        return None

    baseline_median = _median(baseline_prices)
    if baseline_median <= 0:
        return None

    deviation_pct = ((latest_price - baseline_median) / baseline_median) * 100.0

    kind: AnomalyKind | None = None
    if deviation_pct <= config.deal_deviation_pct:
        kind = "price_deal"
    elif deviation_pct >= config.spike_deviation_pct:
        kind = "price_spike"

    if kind is None:
        return None

    severity = _severity_for(kind=kind, deviation_pct=deviation_pct)

    rows = repo.get_price_history_since(item_id=item_id, since=baseline_since)
    last_row = None
    for row in reversed(rows):
        if float(row.price) <= 0:
            continue
        if row.source == "mock_js_fallback":
            continue
        last_row = row
        break

    return PriceAnomalySignal(
        kind=kind,
        item_id=item_id,
        item_name=last_row.item_name if last_row is not None else item_id,
        latest_price=float(latest_price),
        baseline_median=float(baseline_median),
        deviation_pct=float(deviation_pct),
        severity=severity,
        observed_at=latest_observed_at,
        source=latest_source,
    )


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return float(sorted_values[mid])
    return float((sorted_values[mid - 1] + sorted_values[mid]) / 2.0)


def _severity_for(*, kind: AnomalyKind, deviation_pct: float) -> Literal["critical", "high", "medium", "low"]:
    magnitude = abs(float(deviation_pct))
    if kind == "price_deal":
        if magnitude >= 55:
            return "high"
        if magnitude >= 45:
            return "medium"
        return "low"

    if magnitude >= 120:
        return "high"
    if magnitude >= 90:
        return "medium"
    return "low"
