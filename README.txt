# Stalcraft Market Analyzer

**Wymagania środowiskowe:**
- **Python:** Wersja `3.10+` jest ściśle wymagana ze względu na wykorzystanie nowoczesnych adnotacji typów i biblioteki SQLAlchemy 2.0+.
- **Baza danych:** Projekt używa lokalnej bazy SQLite. Plik `market.db` nie jest wersjonowany (znajduje się w `.gitignore`). Baza zostanie wygenerowana automatycznie w folderze `data/` przy pierwszym uruchomieniu.

## Instalacja

1. Aktywuj środowisko wirtualne.
2. Zainstaluj pakiety produkcyjne: `pip install -r requirements.txt`
3. (Opcjonalnie) Zainstaluj pakiety do testów: `pip install -r requirements-dev.txt`

## Kontrakt Danych (Ingestia -> Storage)
Dane pobierane przez scraper są mapowane na model `PriceHistory` w następujący sposób:
- `item_id` (str) -> `item_id`
- `item_name` (str) -> `item_name`
- `price` (float) -> `price`
- `volume` (int) -> `volume`
- `source` (str) -> `source` (np. json_api, html_fallback)
*Uwaga: Pole `observed_at` jest nadawane automatycznie w UTC po stronie repozytorium w momencie zapisu.*