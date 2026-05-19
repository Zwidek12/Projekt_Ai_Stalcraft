# Stalcraft Market Analyzer

Narzędzie do zbierania danych z rynku Stalcraft, analizy anomalii cenowych oraz wysyłania czytelnych alertów na Discord (webhook).

## Quick Start (< 20 minut)

1. **Wymagania**
   - Python **3.10+** (wymagane: w repo używane są m.in. `@dataclass(..., slots=True)`)
   - (Opcjonalnie) `venv`
   - Discord webhook URL (kanał, na który mają wpadać alerty)

2. **Klonowanie i środowisko**

```bash
cd /ścieżka/do/projektu
python -m venv .venv
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

Jeśli masz kilka interpreterów Pythona na Windows, upewnij się, że aktywujesz venv utworzony **3.10+**. Typowy objaw błędnej wersji to `TypeError: dataclass() got an unexpected keyword argument 'slots'` albo brak paczek z `requirements.txt`.

Repo zawiera plik `.python-version` (wskazuje wersję używaną w dev). Na Windows możesz też wymusić interpreter przez launcher:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
py -3.12 -m pip install -r requirements.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
```

3. **Konfiguracja `.env`**
   - Skopiuj plik przykładowy:

```bash
cp .env.example .env
```

   - Uzupełnij co najmniej `DISCORD_WEBHOOK_URL`.

4. **Pierwszy test wysyłki alertu (smoke test)**

```bash
python -c "import os; from notifications.message_builder import build_price_opportunity_embed; from notifications.discord_notifier import DiscordNotifier; os.environ['DISCORD_WEBHOOK_URL']=os.environ.get('DISCORD_WEBHOOK_URL',''); n=DiscordNotifier.from_env(); e=build_price_opportunity_embed({'severity':'low','item_name':'Smoke Test Item','price':12345,'deviation_pct':-5.5,'observed_at':'2026-04-28T18:20:00Z','source':'smoke'}); print(n.send_price_alert({}, embeds=[e]))"
```

Jeśli wszystko jest OK, na kanale Discord pojawi się embed z testowym alertem.

## Baza danych lokalnie (`data/market.db`)

Folder `data/` i plik `data/market.db` **nie są w repozytorium** (`.gitignore`). Każdy developer buduje je u siebie po sklonowaniu repo.

Po skonfigurowaniu `.env` (w tym `EXBO_CLIENT_ID` + `EXBO_CLIENT_SECRET`):

```powershell
mkdir data
py -3.12 scripts\refresh_item_catalog.py
py -3.12 scripts\run_full_market_ingestion.py --artifact-only --batch-size 10 --sleep-seconds 1.5
py -3.12 scripts\run_daily_review.py
```

Pełny scrape ~107 artefaktów trwa ok. 15–30 minut. W logu ingestion szukaj `exbo=...` (dane z oficjalnego API z `additional.qlt` → prawdziwe rarity na stronie).

Szybki test bez pełnej bazy:

```powershell
py -3.12 scripts\check_exbo_auth.py --item qoq6
```

## Developer Web UI (Stalcraft-style)

Projekt zawiera lekki panel developerski do testowania pipeline i diagnostyki:

- dashboard health (`db_status`, `webhook_status`, znaczniki ostatnich jobow),
- podglad ostatniego snapshotu z `data/raw`,
- szybkie akcje: mark ingestion, mark anomaly, send Discord test alert.
- wykres telemetryczny cen i sekcje statusu operacyjnego (zone cards).

Opcjonalnie ustaw `DEV_UI_TOKEN` w `.env`, żeby Dev UI wymagał Basic Auth w przeglądarce
(login dowolny, hasło = wartość `DEV_UI_TOKEN`). User Web pozostaje osobną aplikacją read-only.

Uruchomienie:

```bash
python scripts/run_dev_ui.py --host 127.0.0.1 --port 8080 --reload
```

Windows (PowerShell, Python 3.10 wymuszony automatycznie):

```powershell
.\scripts\run_dev_ui.ps1 -HostName 127.0.0.1 -Port 8080 -Reload
```

Nastepnie otworz:

```text
http://127.0.0.1:8080/app
```

## User Web (read-only)

Osobny panel dla użytkownika końcowego. Nie ma akcji operatorskich, nie uruchamia jobów i nie używa webhooka Discord.
Czyta gotowe dane z SQLite: `item_catalog`, `market_deals`, `price_history`.

Przygotowanie danych:

```powershell
py -3.12 scripts\run_daily_workflow.py --limit 20 --batch-size 5
```

Dodanie notatki update/balance:

```powershell
py -3.12 scripts\add_game_update.py --type balance --title "Balance patch" --summary "Krótka informacja dla usera" --link "https://example.com"
```

Uruchomienie:

```powershell
py -3.12 scripts\run_user_web.py --host 127.0.0.1 --port 8090
```

Następnie otwórz:

```text
http://127.0.0.1:8090/
```

## Testowa wiadomość na Discord (bez udostępniania `.env`)

Możesz wysłać testowe alerty lokalnie, bez przekazywania komukolwiek pliku `.env`:

- **1) Uzupełnij `.env`** (lokalnie): wklej swój `DISCORD_WEBHOOK_URL`
- **2) Uruchom przykład integracyjny**:

Windows (PowerShell):

```powershell
python scripts\send_discord_alert_example.py
```

Skrypt:
- buduje 2 przykładowe embedy (okazja cenowa + patch impact),
- wysyła je webhookiem,
- loguje wynik wysyłki (`DiscordWebhookResponse`).

## Instalacja krok po kroku

### 1) Zależności

Projekt jest zaprojektowany tak, aby **alerty na Discord działały bez dodatkowych zależności** (standardowa biblioteka Pythona).  
Jeśli w repo pojawią się moduły scraper/analizy wymagające paczek zewnętrznych, dodaj je do `requirements.txt`/`pyproject.toml`.

### 2) Zmienne środowiskowe

Zobacz sekcję [Konfiguracja `.env`](#konfiguracja-env).

### 3) Uruchomienie

Najprostszy start to smoke test Discord z sekcji [Quick Start](#quick-start--20-minut).  
Dalej uruchamiasz joby jako skrypty w `scripts/` (każdy skrypt sam doda `src/` oraz (tam gdzie potrzeba) root repo do `sys.path`).

## Jak uruchomić scraper, analizę i alerty

Poniżej są **realne entrypointy** z repo (Windows: zamień ścieżki na `python scripts\\...`).

### Ingestion (StalcraftDB → SQLite + `data/raw`)

Wymaga sensownego `STALCRAFTDB_BASE_URL` (patrz `.env.example`, rekomendacja EU: `https://stalcraftdb.net/eu`).
Jeśli ustawisz `EXBO_ACCESS_TOKEN` albo parę `EXBO_CLIENT_ID` + `EXBO_CLIENT_SECRET`, ingestion najpierw użyje oficjalnego EXBO API (`/{region}/auction/{item}/history` i `/lots` z `additional=true`), a dopiero potem fallbacku StalcraftDB.

```bash
python scripts/run_ingestion.py --items ak-103,veteran-armor
```

Konfiguracja EXBO w `.env`:

```env
EXBO_API_BASE_URL=https://eapi.stalcraft.net
EXBO_REGION=EU
EXBO_ACCESS_TOKEN=
EXBO_CLIENT_ID=
EXBO_CLIENT_SECRET=
```

Po wpisaniu danych sprawdź auth bez zapisu do bazy:

```bash
python scripts/check_exbo_auth.py --item qoq6
python scripts/check_exbo_auth.py --item wg3p
```

Jeśli wynik pokaże `with_qlt > 0`, ingestion zapisze realną jakość egzemplarzy artefaktów z `additional.qlt`.

Możesz sprawdzić kontrakt OpenAPI bez Telegrama:

```bash
python scripts/inspect_exbo_openapi.py --tag Auction
python scripts/inspect_exbo_openapi.py --auth public
```

Ten skrypt pobiera `https://eapi.stalcraft.net/openapi`, zapisuje cache w `data/exbo_openapi.json` i pokazuje, które endpointy są publiczne, a które wymagają `AppAuth`. Endpointy aukcji w OpenAPI nadal wymagają autoryzacji aplikacji, więc sam plik OpenAPI nie daje dostępu do produkcyjnych danych rynku.

Do testów z demo API możesz użyć:

```env
EXBO_API_BASE_URL=https://dapi.stalcraft.net
EXBO_REGION=EU
EXBO_CLIENT_ID=1
EXBO_CLIENT_SECRET=E98cm6J9NNjTQopph0c2eIXNKafg4R1Cjz0TZh2D
```

### Katalog itemów (StalcraftDB listing → `item_catalog`)

To zasila lokalny katalog nazw, kategorii i flagi `is_artifact`. Jest potrzebne pod User Web i `--artifact-only`.
Listing StalcraftDB nie wystawia pewnie jakości konkretnej transakcji artefaktu, więc refresh katalogu automatycznie wzbogaca artefakty z publicznej bazy EXBO `EXBO-Studio/stalcraft-database` (`global/items/artefact/...`). To działa bez Telegram bota i bez tokena. Dokładniejsze rarity konkretnego lotu nadal jest pobierane z rynku z pola `additional.qlt`, jeśli EXBO auction API jest skonfigurowane.

```bash
python scripts/refresh_item_catalog.py
```

Wymuszenie świeżego pobrania publicznej bazy EXBO:

```bash
python scripts/refresh_item_catalog.py --refresh-exbo-item-db-cache
```

Wyłączenie wzbogacania z publicznej bazy EXBO:

```bash
python scripts/refresh_item_catalog.py --skip-exbo-item-db
```

Test bez zapisu do DB:

```bash
python scripts/refresh_item_catalog.py --dry-run
```

Opcjonalny, awaryjny eksport szablonu override dla katalogu artefaktów:

```bash
python scripts/export_artifact_rarity_template.py --only-unknown
```

Po uzupełnieniu `data/artifact_rarity_overrides.json` wartościami innymi niż `unknown`:

```bash
python scripts/refresh_item_catalog.py --artifact-rarity-overrides data/artifact_rarity_overrides.json
```

### Full market ingestion z katalogu

Scrapuje itemy zapisane w `item_catalog` w bezpiecznych paczkach. Najpierw odpal `refresh_item_catalog.py`.

```bash
python scripts/run_full_market_ingestion.py --batch-size 25 --sleep-seconds 1.5
```

Tylko artefakty, z automatycznym zapisem rarity transakcji jeśli EXBO/StalcraftDB zwróci `additional.qlt`:

```bash
python scripts/run_full_market_ingestion.py --artifact-only --batch-size 10 --sleep-seconds 1.5
```

Mały test na pierwszych 20 itemach:

```bash
python scripts/run_full_market_ingestion.py --limit 20 --batch-size 5
```

### Daily workflow (catalog → ingestion → review)

Jeden proces łączący: odświeżenie katalogu, ingestion z katalogu w paczkach i daily review.

```bash
python scripts/run_daily_workflow.py --batch-size 25 --sleep-seconds 1.5 --review-deal-pct -25
```

Bezpieczny mały test:

```bash
python scripts/run_daily_workflow.py --limit 20 --batch-size 5
```

Worker dzienny (blokujący proces, np. osobne okno terminala lub Windows Task Scheduler):

```bash
python scripts/run_daily_worker.py --at 06:00 --run-on-start --limit 20 --batch-size 5
```

### Analiza anomalii (SQLite → sygnały + opcjonalnie Discord)

```bash
python scripts/run_analysis.py --send-discord
```

Diagnostyka webhooka (deterministyczny test po skanie):

```bash
python scripts/run_analysis.py --discord-test
```

### Pipeline end-to-end (ingestion + skan + opcjonalnie patch impact)

```bash
python scripts/run_pipeline.py --items ak-103 --send-discord
```

Jeśli chcesz **wymusić** wysyłkę Discord mimo deduplikacji alertów w DB (dev/ops):

```bash
python scripts/run_pipeline.py --items ak-103 --send-discord --force-discord-notify
```

### Scheduler (cyklicznie, blokujący)

```bash
python scripts/run_scheduler.py --every-minutes 30 --run-on-start --items ak-103 --send-discord
```

### Daily review (DB → `market_deals`)

Przegląda historię z SQLite, liczy średnią 1d/7d i zapisuje aktywne okazje do tabeli `market_deals`.
To jest fundament pod publiczny User Web/Hot Deals. Na razie bazuje na danych, które już są w DB.

```bash
python scripts/run_daily_review.py --deal-pct -25 --limit 250
```

Tryb pod artefakty (używa `item_catalog.is_artifact` i hot rarity: `pink`, `red`, `gold`):

```bash
python scripts/run_daily_review.py --artifact-only --deal-pct -25
```

### Patch notes (LLM opcjonalne)

```bash
python scripts/run_patch_impact.py --patch-version 1.9.14 --notes-file patch.txt
```

Alerty składają się z dwóch warstw:
- **builder** (`notifications/message_builder.py`) – formatuje embedy,
- **notifier** (`notifications/discord_notifier.py`) – wysyła gotowe embedy webhookiem.

## Konfiguracja `.env`

Skopiuj `.env.example` do `.env` i uzupełnij wartości.

### Minimalna konfiguracja

- **`DISCORD_WEBHOOK_URL`**: wymagane do wysyłki alertów.
- **`STALCRAFTDB_BASE_URL`**: wymagane do realnego scrapingu (w `.env.example` jest sensowny default dla EU).
- **`DATABASE_URL`**: domyślnie SQLite w `./data/market.db` (katalog `data/` jest ignorowany przez git).

### Konfiguracja retry/timeout

- `DISCORD_WEBHOOK_TIMEOUT_S` (domyślnie `10`)
- `DISCORD_WEBHOOK_MAX_RETRIES` (domyślnie `3`)
- `DISCORD_WEBHOOK_RETRY_BACKOFF_S` (domyślnie `0.8`)

## Typowe problemy i debug

### 1) Brak alertów na Discord

- Sprawdź, czy `DISCORD_WEBHOOK_URL` jest poprawny.
- Upewnij się, że webhook nie został usunięty / kanał istnieje.
- Uruchom smoke test z Quick Start i sprawdź wynik `DiscordWebhookResponse`.

### 2) HTTP 429 (rate limit)

Notifier retry’uje 429 z backoffem. Jeśli 429 pojawia się często:
- ogranicz częstotliwość wysyłki (agregacja/dedupe w warstwie biznesowej),
- rozważ batching (1 wiadomość = kilka embedów).

### 3) HTTP 400 / “Invalid Form Body”

Najczęściej:
- zbyt długi `description`/`fields`,
- zbyt dużo embedów w jednym payloadzie,
- błędne typy pól.

W logach zobaczysz HTTP status + ucięte body odpowiedzi.

### 4) Timeout / problemy sieciowe

- Zwiększ `DISCORD_WEBHOOK_TIMEOUT_S`.
- Sprawdź proxy/firewall.

### 5) Brak logów

Włącz podstawową konfigurację logowania w entrypoincie:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Struktura projektu i moduły

Aktualnie w repo znajdują się m.in.:

- `src/stalcraft_market_analyzer/`
  - `ingestion/` – scraper + parsery + eksport raw snapshotów,
  - `analysis/` – reguły anomalii + (opcjonalnie) analiza patchy,
  - `storage/` – modele SQLite + repozytorium (dedupe/cooldown),
  - `core/` – konfiguracja, pipeline, scheduler.

- `api/` – joby HTTP/operacyjne (`analysis_jobs.py`, `patch_jobs.py`, `dev_ui.py`).

- `notifications/message_builder.py`
  - **formatowanie embedów** (okazje cenowe, patch impact),
  - stała struktura pól, kolory zależne od severity,
  - brak logiki biznesowej (tylko “rendering”).

- `notifications/discord_notifier.py`
  - **wysyłka webhookiem** (POST JSON),
  - timeout + retry (backoff),
  - czytelne logi statusów i błędów,
  - przyjmuje **już zbudowane** embedy.

**MVP powiadomień (spójny zestaw):** webhook + embedy, `message_builder`, healthcheck (`api/health.py`), runbook (`Runbook.md`) oraz scenariusz E2E (`tests/test_e2e_pipeline.py`). Lokalny „ręczny” smoke: `python scripts/send_discord_alert_example.py`.

## Bezpieczeństwo

- Nie commituj `.env`.
- Webhook URL traktuj jak sekret (po wycieku natychmiast zresetuj webhook).

