from src.stalcraft_market_analyzer.analysis.price_anomaly import check_for_anomaly

def test_check_for_anomaly_is_deal():
    is_deal, ratio = check_for_anomaly(60.0, 100.0)
    assert is_deal is True
    assert ratio == 0.6

def test_check_for_anomaly_no_deal():
    is_deal, ratio = check_for_anomaly(80.0, 100.0)
    assert is_deal is False
    assert ratio == 0.8

def test_check_for_anomaly_no_data():
    is_deal, ratio = check_for_anomaly(50.0, 0.0)
    assert is_deal is False
    assert ratio == 0.0