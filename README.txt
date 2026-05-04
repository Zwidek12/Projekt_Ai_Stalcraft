# Stalcraft Market Analyzer

**Wymagania systemowe:**
- Python 3.10 lub nowszy (wymagane ze względu na nowoczesne adnotacje typów i SQLAlchemy 2.0).

## Baza danych
Projekt używa lokalnej bazy SQLite. Plik `market.db` **nie jest** trzymany w repozytorium. Baza zostanie wygenerowana automatycznie w folderze `data/` przy pierwszym uruchomieniu skryptu inicjalizującego (`db.py`) lub przy pierwszej próbie zapisu.

## Kontrakt Danych (Scraper -> Storage)
Dane ze scrapera są mapowane na model `PriceHistory` w następujący sposób:
- `item_id` (str) -> `item_id`
- `item_name` (str) -> `item_name`
- `price` (float) -> `price`
- `volume` (int) -> `volume`
- `source` (str) -> `source` (np. json_api, html_fallback)
- **Uwaga:** Pole `observed_at` nie musi być przekazywane przez scraper. Baza danych automatycznie nadaje mu obecny czas w strefie UTC w momencie zapisu.