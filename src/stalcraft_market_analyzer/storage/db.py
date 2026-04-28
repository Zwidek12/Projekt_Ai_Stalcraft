import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.stalcraft_market_analyzer.storage.models import Base

# Ustawiamy ścieżkę do pliku w folderze 'data'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Upewniamy się, że folder data istnieje
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'market.db')
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Tworzymy silnik bazy danych. 'check_same_thread' jest wymagane dla SQLite przy schedulerach
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

# Tworzymy fabrykę sesji (tego będziesz używać w repozytorium do zapisywania)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Funkcja tworząca tabele w bazie (jeśli jeszcze nie istnieją)."""
    Base.metadata.create_all(bind=engine)
    print(f"Baza danych została zainicjowana w: {DB_PATH}")

if __name__ == "__main__":
    init_db()