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

## Developer Web UI (Stalcraft-style)

Projekt zawiera lekki panel developerski do testowania pipeline i diagnostyki:

- dashboard health (`db_status`, `webhook_status`, znaczniki ostatnich jobow),
- podglad ostatniego snapshotu z `data/raw`,
- szybkie akcje: mark ingestion, mark anomaly, send Discord test alert.
- wykres telemetryczny cen i sekcje statusu operacyjnego (zone cards).

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

Minimalnie możesz uruchamiać moduły/entrypointy jako skrypty Pythona. Przykłady poniżej zakładają, że w repo istnieją osobne entrypointy dla:
- scrapera,
- analizy,
- alertów.

Jeśli jeszcze ich nie ma, najprostszy start to uruchomienie smoke testu z Quick Start.

## Jak uruchomić scraper, analizę i alerty

Poniższe komendy są **szablonami** (docelowe nazwy plików/entrypointów dopasuj do repo, gdy będą dodane):

### Scraper

```bash
python -m scraper.run
```

### Analiza

```bash
python -m analyzer.run
```

### Alerty (Discord webhook)

Alerty składają się z dwóch warstw:
- **builder** (`notifications/message_builder.py`) – formatuje embedy,
- **notifier** (`notifications/discord_notifier.py`) – wysyła gotowe embedy webhookiem.

Przykładowy “runner” alertów (gdy dodasz pipeline):

```bash
python -m notifications.run_alerts
```

## Konfiguracja `.env`

Skopiuj `.env.example` do `.env` i uzupełnij wartości.

### Minimalna konfiguracja

- **`DISCORD_WEBHOOK_URL`**: wymagane do wysyłki alertów.

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

W kolejnych etapach zwykle dochodzą:
- `scraper/` – pobieranie danych z rynku,
- `analyzer/` – wykrywanie okazji/anomalii oraz wpływu patchy,
- `storage/` – zapis i odczyt danych (cache/DB/pliki),
- `notifications/` – pipeline dedupe/agregacja i wysyłka alertów.

## Bezpieczeństwo

- Nie commituj `.env`.
- Webhook URL traktuj jak sekret (po wycieku natychmiast zresetuj webhook).

