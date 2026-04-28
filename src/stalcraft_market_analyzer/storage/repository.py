from sqlalchemy import func, and_
from datetime import timedelta
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from src.stalcraft_market_analyzer.storage.models import PriceHistory
from src.stalcraft_market_analyzer.storage.db import SessionLocal

def save_price_record(item_id: str, item_name: str, price: float, volume: int, source: str = "manual") -> bool:
    """
    Zapisuje nowy rekord ceny pobrany ze StalcraftDB do bazy danych.
    """
    # SessionLocal to nasza fabryka połączeń z bazą (którą stworzyłeś w db.py)
    with SessionLocal() as session:
        try:
            # Tworzymy nowy obiekt na podstawie naszego modelu
            new_record = PriceHistory(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=volume,
                source=source,
                observed_at=datetime.now(timezone.utc)
            )
            
            # Dodajemy "paczke" do sesji
            session.add(new_record)
            
            # Zatwierdzamy zmiany w bazie (fizyczny zapis na dysku)
            session.commit()
            
            print(f"✅ Zapisano do bazy: {item_name} | {price} rubli (Źródło: {source})")
            return True
            
        except Exception as e:
            # W razie jakiegokolwiek błędu, wycofujemy zmiany żeby nie zepsuć bazy
            session.rollback()
            print(f"❌ Błąd podczas zapisu do bazy: {e}")
            return False

# ----- Blok testowy -----
# Ten kod wykona się tylko wtedy, gdy uruchomimy ten konkretny plik
if __name__ == "__main__":
    print("Testowanie połączenia i zapisu...")
    
    # Symulujemy, że Zwidek zeskrapował dane i nam je przekazuje
    sukces = save_price_record(
        item_id="wpn_ak74u",
        item_name="AK-74U",
        price=155000.0,
        volume=24,
        source="test_script"
    )
    
    if sukces:
        print("Punkt 2 ze Sprintu 1 działa perfekcyjnie!")
def get_average_price_7d(item_id: str) -> float:
    """Oblicza średnią cenę przedmiotu z ostatnich 7 dni."""
    with SessionLocal() as session:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        # Wyciągamy średnią z kolumny price dla danego przedmiotu z ostatnich 7 dni
        result = session.query(func.avg(PriceHistory.price)).filter(
            and_(
                PriceHistory.item_id == item_id,
                PriceHistory.observed_at >= seven_days_ago
            )
        ).scalar()
        
        return float(result) if result else 0.0