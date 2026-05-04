from typing import Tuple

def check_for_anomaly(current_price: float, average_price: float, current_volume: int, threshold: float = 0.7) -> Tuple[bool, float]:
    """
    Sprawdza, czy aktualna cena jest anomalią (okazją).
    Wymaga podania wolumenu, aby odfiltrować fałszywe okazje (np. błędy API gdzie volume = 0).
    Zwraca status (True/False) i stosunek ceny do średniej.
    """
    if average_price <= 0:
        return False, 0.0
    
    # Zabezpieczenie przed "pustymi" ofertami
    if current_volume <= 0:
        return False, current_price / average_price if average_price > 0 else 0.0
    
    ratio = current_price / average_price
    is_anomaly = ratio <= threshold
    
    return is_anomaly, ratio