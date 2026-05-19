from __future__ import annotations

from stalcraft_market_analyzer.analysis.price_stats import filter_price_outliers


def test_filter_price_outliers_removes_extreme_spike() -> None:
    prices = [1_000.0, 1_020.0, 980.0, 1_010.0, 50_000_000.0, 990.0]
    filtered = filter_price_outliers(prices)
    assert 50_000_000.0 not in filtered
    assert len(filtered) >= 4


def test_filter_price_outliers_keeps_short_series() -> None:
    prices = [100.0, 200.0, 999_999.0]
    assert filter_price_outliers(prices) == prices
