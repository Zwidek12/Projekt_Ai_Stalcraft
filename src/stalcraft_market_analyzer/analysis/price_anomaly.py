def check_for_anomaly(current_price: float, average_price: float, threshold: float = 0.7):
    """Sprawdza, czy aktualna cena jest okazją (domyślnie o 30% taniej niż średnia)."""
    if average_price <= 0:
        return False, 0
    
    ratio = current_price / average_price
    is_anomaly = ratio <= threshold
    
    return is_anomaly, ratio