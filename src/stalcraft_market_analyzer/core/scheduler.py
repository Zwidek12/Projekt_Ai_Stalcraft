import time
import schedule
from datetime import datetime

# Importy z Twojej działki (Osoba B)
from src.stalcraft_market_analyzer.storage.repository import save_price_record, get_average_price_7d
from src.stalcraft_market_analyzer.analysis.price_anomaly import check_for_anomaly

def market_cycle_job():
    """Główny cykl pracy aplikacji: Pobierz -> Zapisz -> Analizuj -> (W przyszłości: Wyślij)"""
    print(f"\n--- [ {datetime.now().strftime('%H:%M:%S')} ] Rozpoczynam cykl rynkowy ---")
    
    # 1. FAZA INGESTII (Miejsce na kod Zwidka)
    print("Pobieram najnowsze ceny ze StalcraftDB...")
    
    # TYMCZASOWY MOCK: Zamiast pytać prawdziwej strony, symulujemy, że scraper coś zwrócił.
    # Jak Zwidek skończy swój moduł, zamienimy to na import jego funkcji (np. fetch_market_data())
    mock_scraped_data = [
        {"item_id": "wpn_ak74u", "item_name": "AK-74U", "price": 125000.0, "volume": 12},
        {"item_id": "med_medkit", "item_name": "Apteczka", "price": 4500.0, "volume": 300},
        {"item_id": "art_sun", "item_name": "Słońce", "price": 800000.0, "volume": 2}
    ]
    
    # 2. FAZA STORAGE i 3. FAZA ANALIZY (Twoja działka)
    for item in mock_scraped_data:
        # A) Zapisujemy świeżą cenę do bazy
        save_price_record(
            item_id=item["item_id"],
            item_name=item["item_name"],
            price=item["price"],
            volume=item["volume"],
            source="scraper_mock"
        )
        
        # B) Wyciągamy średnią z ostatnich 7 dni dla tego przedmiotu
        avg_price = get_average_price_7d(item["item_id"])
        
        # C) Szukamy anomalii
        is_deal, ratio = check_for_anomaly(current_price=item["price"], average_price=avg_price)
        
        # D) Reagujemy na wyniki
        if is_deal:
            print(f"🔥 ALARM OKAZJI: {item['item_name']} za {item['price']} (to {ratio*100:.1f}% średniej z 7 dni!)")
            # W przyszłości Mociur podepnie tu: discord_notifier.send_deal_alert(item)
        else:
            print(f"ℹ️ {item['item_name']}: Cena stabilna ({ratio*100:.1f}% średniej).")

    print("--- Zakończono cykl ---")

def run_scheduler():
    """Uruchamia ciągłą pracę aplikacji."""
    print("Uruchamiam Schedulera Stalcraft Market Analyzer.")
    print("Cykliczne sprawdzanie rynku jest aktywne. Naciśnij CTRL+C, aby zatrzymać.")
    
    # Wykonujemy pierwszy strzał od razu po uruchomieniu
    market_cycle_job()
    
    # Ustawiamy harmonogram zgodnie z planem (co 10 minut). 
    # Do szybszego testowania możesz to zmienić na: schedule.every(10).seconds.do(...)
    schedule.every(10).minutes.do(market_cycle_job)
    
    # Główna pętla programu - trzyma skrypt przy życiu
    while True:
        schedule.run_pending()
        time.sleep(1) # Odpoczynek dla procesora

if __name__ == "__main__":
    run_scheduler()