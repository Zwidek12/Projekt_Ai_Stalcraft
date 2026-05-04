from src.stalcraft_market_analyzer.storage.repository import get_average_price_7d, save_price_record
from src.stalcraft_market_analyzer.analysis.price_anomaly import check_for_anomaly

def run_scan():
    # 1. Symulujemy, że mamy w bazie jakieś dane (dodajmy AK-74U o różnych cenach)
    print("Przygotowuję dane do testu...")
    item_id = "wpn_ak74u"
    
    # Dodajemy kilka rekordów z przeszłości (wysokie ceny)
    save_price_record(item_id, "AK-74U", 200000.0, 10, "test_history")
    save_price_record(item_id, "AK-74U", 210000.0, 5, "test_history")
    
    # 2. Pobieramy średnią
    avg = get_average_price_7d(item_id)
    print(f"Średnia cena dla {item_id} z 7 dni: {avg:.2f} rubli")
    
    # 3. Symulujemy nową, niską cenę (np. 130 000)
    current_price = 130000.0
    print(f"Aktualna cena rynkowa: {current_price} rubli")
    
    # 4. Sprawdzamy anomalię
    is_deal, ratio = check_for_anomaly(current_price, avg)
    
    if is_deal:
        print(f"🔥 ALARM: Znaleziono okazję! Cena stanowi {ratio*100:.1f}% średniej.")
    else:
        print(f"ℹ️ Cena stabilna ({ratio*100:.1f}% średniej). Brak okazji.")

if __name__ == "__main__":
    run_scan()