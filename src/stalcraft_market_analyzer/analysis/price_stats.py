from __future__ import annotations


def filter_price_outliers(
    prices: list[float],
    *,
    iqr_multiplier: float = 1.5,
    min_samples: int = 4,
) -> list[float]:
    """
    Drop extreme prices that skew averages (obvious bad listings).

    Uses Tukey fences on the inter-quartile range. With fewer than ``min_samples``
    values, returns the input unchanged so short histories are not over-filtered.
    """
    if len(prices) < min_samples:
        return prices

    low_fence, high_fence = iqr_fences(prices, multiplier=iqr_multiplier)
    if low_fence is None or high_fence is None:
        return prices

    filtered = [price for price in prices if low_fence <= price <= high_fence]
    return filtered if filtered else prices


def iqr_fences(values: list[float], *, multiplier: float = 1.5) -> tuple[float | None, float | None]:
    if len(values) < 4:
        return None, None

    sorted_values = sorted(float(v) for v in values)
    q1 = _percentile(sorted_values, 0.25)
    q3 = _percentile(sorted_values, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return None, None

    return q1 - multiplier * iqr, q3 + multiplier * iqr


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)
