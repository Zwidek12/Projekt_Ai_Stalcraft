import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.stalcraft_market_analyzer.storage.models import Base, PriceHistory
from src.stalcraft_market_analyzer.storage.repository import get_average_price_7d

# Ustawiamy testową bazę w pamięci RAM (znika po wyłączeniu testu)
@pytest.fixture
def test_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Podmieniamy prawdziwą bazę na testową w naszym repozytorium
    monkeypatch.setattr("src.stalcraft_market_analyzer.storage.repository.SessionLocal", TestingSessionLocal)
    
    with TestingSessionLocal() as session:
        yield session

def test_get_average_price_7d_no_data(test_session):
    # Sprawdzamy zachowanie, gdy nie ma w ogóle przedmiotu w bazie
    avg = get_average_price_7d("item_ktorego_nie_ma")
    assert avg == 0.0

def test_get_average_price_7d_calculates_correctly(test_session):
    now = datetime.now(timezone.utc)
    
    # Dodajemy poprawne wpisy z ostatnich 7 dni
    test_session.add(PriceHistory(item_id="test_item", item_name="Test", price=100.0, observed_at=now))
    test_session.add(PriceHistory(item_id="test_item", item_name="Test", price=200.0, observed_at=now - timedelta(days=2)))
    
    # Dodajemy wpis stary (10 dni temu) – ten nie powinien wliczyć się do średniej
    test_session.add(PriceHistory(item_id="test_item", item_name="Test", price=9000.0, observed_at=now - timedelta(days=10)))
    test_session.commit()
    
    # Średnia z 100 i 200 to 150 (ignoruje 9000)
    avg = get_average_price_7d("test_item")
    assert avg == 150.0