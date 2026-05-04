import time
import schedule
from datetime import datetime

# Importy z Twojej działki (Osoba B)
from src.stalcraft_market_analyzer.storage.repository import save_price_record, get_average_price_7d, can_send_alert, log_alert_sent
from src.stalcraft_market_analyzer.analysis.price_anomaly import check_for_anomaly

def market_cycle_job():
    """Główny cykl pracy aplikacji: Pobierz -> Zapisz -> Analizuj -> Wyślij (z cooldownem)"""
    print(f"\n--- [ {datetime.now().strftime('%H:%M:%S')} ] Rozpoczynam cykl rynkowy ---")
    
    # TYMCZASOWY MOCK: Sztuczne dane (zastąpione później przez kod Zwidka)
    mock_scraped_data = [
        {"item_id": "wpn_ak74u", "item_name": "AK-74U", "price": 125000.0, "volume": 12},
        # Zwróć uwagę na wolumen 0 poniżej - system to teraz zignoruje:
        {"item_id": "med_medkit", "item_name": "Apteczka", "price": 4500.0, "volume": 0},
        {"item_id": "art_sun", "item_name": "Słońce", "price": 800000.0, "volume": 2}
    ]
    
    for item in mock_scraped_data:
        # A) Zapisujemy świeżą cenę do bazy
        save_price_record(
            item_id=item["item_id"],
            item_name=item["item_name"],
            price=item["price"],
            volume=item["volume"],
            source="scraper_mock"
        )
        
        # B) Wyciągamy średnią z ostatnich 7 dni
        avg_price = get_average_price_7d(item["item_id"])
        
        # C) Szukamy anomalii (teraz podajemy też wolumen!)
        is_deal, ratio = check_for_anomaly(
            current_price=item["price"], 
            average_price=avg_price,
            current_volume=item["volume"]
        )
        
        # D) Reagujemy na wyniki
        if is_deal:
            # System Anty-Spamowy: Sprawdzamy czy nie wysłaliśmy już alertu w ciągu ostatniej godziny
            if can_send_alert(item["item_id"]):
                print(f"🔥 ALARM OKAZJI: {item['item_name']} za {item['price']} (to {ratio*100:.1f}% średniej!). Wysyłam powiadomienie.")
                # Zapisujemy do bazy fakt wysłania alertu
                log_alert_sent(item["item_id"])
            else:
                print(f"🔇 Zignorowano okazję na {item['item_name']} - aktywny cooldown (anty-spam).")
        else:
            print(f"ℹ️ {item['item_name']}: Brak okazji (Cena: {item['price']}, Wolumen: {item['volume']}, Procent: {ratio*100:.1f}%).")

    print("--- Zakończono cykl ---")

def run_scheduler():
    """Uruchamia ciągłą pracę aplikacji."""
    print("Uruchamiam Schedulera Stalcraft Market Analyzer.")
    print("Cykliczne sprawdzanie rynku jest aktywne. Naciśnij CTRL+C, aby zatrzymać.")
    
    # Pierwszy start od razu
    market_cycle_job()
    
    # Potem co 10 minut
    schedule.every(10).minutes.do(market_cycle_job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_scheduler()