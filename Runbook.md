# Runbook operacyjny — Stalcraft Market Analyzer

Dokument operacyjny do diagnozowania i stabilizowania pipeline:
**scraper → DB → analiza/anomalie → notifier → Discord**.

## Szybka triage (5 minut)

- **1) Sprawdź /health**
  - `db_status`, `webhook_status`
  - `last_ingestion_at`, `last_anomaly_scan_at`
- **2) Sprawdź logi z ostatnich 15 minut**
  - błędy sieci (timeout/DNS), HTTP 429/5xx, wyjątki DB
  - wyjątki parsera JSON (LLM)
- **3) Potwierdź “czy pipeline robi postęp”**
  - rosnący licznik rekordów ingestowanych
  - ostatni skan anomalii zmienia się w czasie
  - notifier ma próby wysyłki (ok/fail + status)

## Incydenty i procedury

### 1) Scraper nie zwraca danych

**Objawy**
- `last_ingestion_at` stoi w miejscu / brak nowych rekordów w DB
- licznik pobranych ofert = 0
- brak alertów mimo ruchu na rynku

**Najczęstsze przyczyny**
- zmiana API/HTML (breaking change)
- blokada (rate limit / captcha / WAF)
- błąd autoryzacji / token wygasł
- błąd deserializacji/parsowania danych wejściowych

**Diagnostyka**
- **Sprawdź logi scrapera**:
  - kody HTTP, treść błędu, czas odpowiedzi
  - liczba stron/rekordów na iterację
- **Sprawdź odpowiedź źródła “na surowo”** (1 próbka):
  - czy payload ma oczekiwaną strukturę
  - czy pola (np. item_id, price) istnieją i mają typy
- **Weryfikacja środowiska**:
  - proxy/firewall, DNS, certyfikaty
  - czy zegar systemowy jest poprawny (ważne dla tokenów)

**Remediacja**
- jeśli to **breaking change**: szybko wprowadź fallback parser / feature flag “old/new”
- jeśli **rate limit**:
  - zmniejsz częstotliwość / zwiększ jitter
  - cache po stronie scrapera
- jeśli **auth**: odśwież token/sekrety, zweryfikuj uprawnienia

**Po naprawie**
- uruchom ingest ręcznie (1 przebieg) i potwierdź wzrost rekordów w DB
- sprawdź `record_ingestion()` / `last_ingestion_at` (jeśli używane)

---

### 2) LLM zwraca błędny JSON

**Objawy**
- wyjątki typu: `JSONDecodeError`, brak wymaganych pól
- downstream nie widzi `severity`, `item_name`, itp.
- duża liczba odrzuconych wyników analizy

**Najczęstsze przyczyny**
- prompt nie wymusza ścisłego JSON
- LLM zwraca markdown/tekst wokół JSON
- długość odpowiedzi (ucięcie) / limity
- niezgodność schematu po zmianach w kodzie

**Diagnostyka**
- **Zapisz surową odpowiedź LLM** (sanity log; bez sekretów):
  - pierwsze ~500–1000 znaków + długość + request-id
- **Waliduj schemat**:
  - czy wymagane klucze istnieją
  - czy typy są zgodne (np. `confidence` float, listy stringów)
- **Sprawdź wersję prompta i model**

**Remediacja (stabilizacja)**
- wprowadź **twardą walidację** + fallback:
  - jeśli JSON niepoprawny: oznacz wynik jako `invalid`, nie wysyłaj alertu, policz metrykę
- zastosuj **“extract JSON”**:
  - wytnij pierwszy poprawny obiekt `{...}` lub tablicę `[...]` zanim zrobisz `json.loads`
- ogranicz output:
  - krótsze listy, limit na elementy, zwięzłe pola

**Prewencja**
- schema/prompt trzymać razem (jedno źródło prawdy)
- testy kontraktowe: “LLM output → parser → model typed”

---

### 3) Webhook Discord nie działa

**Objawy**
- `webhook_status = error` w /health
- logi notifiera: `HTTPError`, `URLError`, timeout
- statusy: 400/401/403/404/429/5xx

**Diagnostyka**
- **Zweryfikuj `DISCORD_WEBHOOK_URL`**:
  - czy nie jest pusty / nie ma spacji
  - czy webhook istnieje i jest aktywny
- **Sprawdź status HTTP z logów**:
  - **400**: niepoprawny payload (zbyt długi embed/field, zły typ)
  - **401/403**: webhook skasowany lub brak dostępu
  - **404**: zły URL
  - **429**: rate limit (spam)
  - **5xx**: problem po stronie Discord / transient
- **Sprawdź transport**:
  - DNS, firewall, proxy, TLS

**Remediacja**
- 400: zmniejsz opis/fields, ogranicz liczbę embedów, usuń nietypowe znaki, waliduj długości
- 429:
  - zwiększ agregację/dedupe w logice biznesowej
  - wysyłaj paczkami (1 payload = kilka embedów) zamiast wielu wiadomości
- 401/403/404: wygeneruj nowy webhook i zaktualizuj sekrety
- timeout: zwiększ `DISCORD_WEBHOOK_TIMEOUT_S`, sprawdź sieć

**Weryfikacja**
- uruchom smoke test z `README.md` i potwierdź `status=ok`

---

### 4) Baza ma duplikaty

**Objawy**
- ten sam item/obserwacja pojawia się wielokrotnie w krótkim czasie
- rosną koszty/rozmiar DB, a jakość sygnałów spada
- analiza anomalii zaczyna “wzmacniać” fałszywe sygnały

**Najczęstsze przyczyny**
- brak klucza unikalnego (natural key) / brak upsertu
- retry ingestu zapisuje ponownie te same rekordy
- scraper zwraca powtórzenia (paginacja, cache, race condition)

**Diagnostyka**
- policz duplikaty po kluczu naturalnym (przykład):
  - `(item_id, observed_at, source)` albo `(item_name, price, observed_at, source)`
- sprawdź, czy ingest używa transakcji
- sprawdź retry/backoff w scraperze i czy retry jest idempotentny

**Remediacja**
- dodaj **unikalny indeks** na natural key
- używaj **UPSERT** (INSERT ... ON CONFLICT DO NOTHING/UPDATE)
- dodaj **dedupe w ingest** (bufor ostatnich N kluczy, jeśli brak DB constraintów)

**Cleanup (po incydencie)**
- deduplikacja historyczna:
  - zostaw najnowszy rekord per klucz, usuń resztę
- przelicz metryki/anomalia jeśli bazują na zagregowanych danych

## Procedury diagnostyczne (checklisty)

### Zbieranie dowodów (minimum)
- **Czas zdarzenia** (UTC) + zakres (np. ostatnie 30 min)
- **request-id / run-id** (jeśli istnieje)
- **statusy HTTP** (źródło + Discord)
- **ostatnie 20 linii logów** z komponentu (scraper/analyzer/notifier)
- **metryki**: ingestion rate, error rate, queue depth (jeśli macie)

### Testy “na skróty”
- **Discord**: smoke test z README
- **DB**: prosty SELECT COUNT(*) + ostatni timestamp
- **Scraper**: 1 ręczny run “single page” i zapis surowej odpowiedzi

## Metryki do monitorowania

### Scraper
- `scraper_requests_total` (tagi: status_code, endpoint)
- `scraper_items_scraped_total`
- `scraper_empty_responses_total`
- `scraper_latency_ms` (p50/p95/p99)

### DB / Ingestion
- `ingestion_rows_inserted_total`
- `ingestion_rows_deduped_total`
- `db_write_latency_ms`
- `db_errors_total`
- `duplicates_detected_total` (po kluczu naturalnym)

### Analyzer / LLM
- `anomaly_scans_total`
- `anomalies_found_total` (tagi: severity)
- `llm_requests_total` / `llm_errors_total`
- `llm_invalid_json_total`
- `llm_latency_ms` (p95)

### Notifications (Discord)
- `discord_webhook_requests_total` (tagi: http_status)
- `discord_webhook_failures_total`
- `discord_rate_limited_total` (429)
- `alerts_sent_total` (tagi: alert_type)
- `alerts_suppressed_total` (dedupe/cooldown w logice biznesowej)

### SLO/Watchdogs
- **staleness**:
  - `now - last_ingestion_at` (alert, gdy > X min)
  - `now - last_anomaly_scan_at` (alert, gdy > Y min)

## Checklista po wdrożeniu (operacyjna)

Skopiuj do taska/issue po deployu:

- [ ] `GET /health` zwraca 200 i poprawny JSON
- [ ] `db_status` = ok (albo świadomie missing) i brak błędów DB w logach
- [ ] `webhook_status` = ok i smoke test przechodzi
- [ ] Scraper wytwarza rekordy (ingestion rośnie)
- [ ] Analyzer wykonuje skany (last_anomaly_scan_at się aktualizuje)
- [ ] Brak wzrostu: 429 / 5xx / timeoutów
- [ ] Brak nadmiarowych alertów (agregacja/dedupe działa — jeśli wdrożona)
- [ ] Dashboard/metryki dostępne (jeśli istnieją) i mają sensowne wartości
- [ ] Sekrety/`.env` poprawne (bez wycieku do repo)
- [ ] Plan rollbacku znany + artefakty poprzedniej wersji dostępne

