from typing import Tuple

def check_for_anomaly(current_price: float, average_price: float, threshold: float = 0.7) -> Tuple[bool, float]:
    """Sprawdza czy aktualna cena jest anomalią (okazją). Zwraca status i stosunek ceny."""
    if average_price <= 0:
        return False, 0.0
    
    ratio = current_price / average_price
    is_anomaly = ratio <= threshold
    return is_anomaly, ratio