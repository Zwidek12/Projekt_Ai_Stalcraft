from src.stalcraft_market_analyzer.analysis.price_anomaly import check_for_anomaly

def test_check_for_anomaly_is_deal():
    # Średnia 100, aktualna cena 60, wolumen 10 (okazja)
    is_deal, ratio = check_for_anomaly(60.0, 100.0, 10)
    assert is_deal is True
    assert ratio == 0.6

def test_check_for_anomaly_no_deal():
    # Średnia 100, aktualna cena 80, wolumen 10 (brak okazji)
    is_deal, ratio = check_for_anomaly(80.0, 100.0, 10)
    assert is_deal is False
    assert ratio == 0.8

def test_check_for_anomaly_exact_threshold():
    # Równo na granicy progu 70%, wolumen 10
    is_deal, ratio = check_for_anomaly(70.0, 100.0, 10)
    assert is_deal is True
    assert ratio == 0.7

def test_check_for_anomaly_no_data():
    # Zabezpieczenie przed dzieleniem przez zero
    is_deal, ratio = check_for_anomaly(50.0, 0.0, 10)
    assert is_deal is False
    assert ratio == 0.0

def test_check_for_anomaly_zero_volume():
    # NOWY TEST: Cena to 50% średniej (super tanio!), ale wolumen to 0.
    # System powinien to zignorować i uznać, że nie ma okazji.
    is_deal, ratio = check_for_anomaly(50.0, 100.0, 0)
    assert is_deal is False
    assert ratio == 0.5