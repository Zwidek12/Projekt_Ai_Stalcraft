# Stalcraft Market Analyzer - Kompletny Plan Realizacji (MVP -> v1)

## 1) Cel aplikacji
Tworzymy aplikacje, ktora:
1. Cyklicznie pobiera ceny i transakcje przedmiotow ze StalcraftDB.
2. Przechowuje dane historyczne i wylicza sygnaly okazji cenowych.
3. Analizuje patch notes przez LLM i mapuje zmiany na potencjalny ruch cen.
4. Wysyla estetyczne powiadomienia (Embeds) na Discord.
5. Daje zespolowi prosty pipeline do dalszego rozwoju (API/UI, kolejne reguly, nowe zrodla danych).

## 2) Zakres MVP i v1
### MVP (must-have)
1. Scraper API/HTML + fallback.
2. SQLite + SQLAlchemy + zapis historii cen.
3. Regula anomalii: cena <= 70% sredniej z ostatnich 7 dni.
4. Analiza patch notes przez LLM do formatu JSON (buff/nerf/neutral).
5. Discord notifier dla okazji i dla analizy patcha.

### v1 (should-have)
1. Retry/backoff, idempotencja i deduplikacja.
2. Konfiguracja przez `.env`.
3. Podstawowe API health/status.
4. Dashboard statusu (lekki, opcjonalny).
5. Testy integracyjne i CI.

## 3) Docelowa struktura projektu
```text
stalcraft-market-analyzer/
├─ requirements.txt
├─ .env.example
├─ README.md
├─ data/
│  ├─ raw/
│  ├─ processed/
│  └─ market.db
├─ docs/
│  ├─ project_plan.md
│  ├─ architecture.md
│  ├─ selectors.md
│  └─ runbook.md
├─ scripts/
│  ├─ run_ingestion.py
│  ├─ run_patch_analysis.py
│  ├─ run_anomaly_scan.py
│  └─ run_alerts.py
├─ tests/
│  ├─ test_scraper.py
│  ├─ test_repository.py
│  ├─ test_patch_analyzer.py
│  ├─ test_anomaly_detection.py
│  └─ test_notifier.py
└─ src/
   └─ stalcraft_market_analyzer/
      ├─ ingestion/
      │  ├─ scraper.py
      │  └─ parsers.py
      ├─ analysis/
      │  ├─ patch_analyzer.py
      │  ├─ price_anomaly.py
      │  └─ scoring.py
      ├─ storage/
      │  ├─ db.py
      │  ├─ models.py
      │  └─ repository.py
      ├─ notifications/
      │  ├─ discord_notifier.py
      │  └─ message_builder.py
      ├─ api/
      │  └─ health.py
      ├─ ui/
      │  └─ templates/
      └─ core/
         ├─ config.py
         ├─ scheduler.py
         └─ logging_config.py
```

## 4) Architektura i przeplyw danych (krok po kroku)
1. Scheduler uruchamia job `ingestion` (np. co 10 minut).
2. Scraper pobiera dane dla listy itemow:
   - probe JSON API,
   - fallback do HTML parsera,
   - fallback do mock/Playwright (gdy JS-only).
3. Repository zapisuje rekordy do tabeli historii cen.
4. Modol anomalii pobiera 7d historii i liczy reguly sygnalowe.
5. Gdy sygnal jest dodatni, notifier publikuje embed z detalami okazji.
6. Przy nowym patchu:
   - tekst patch notes trafia do patch_analyzer,
   - LLM zwraca JSON buff/nerf/neutral,
   - system mapuje zmiany do obserwowanych itemow,
   - Discord dostaje osobny embed patchowy.

## 5) Kontrakt danych (minimalny)
### Rekord ceny
1. `item_id: str`
2. `item_name: str`
3. `price: float`
4. `volume: int`
5. `observed_at: datetime`
6. `source: str` (`json_api` / `html_table` / `playwright` / `mock`)

### Wynik analizy patch notes
1. `patch_version: str`
2. `analyzed_at: datetime`
3. `buffed_items: list[str]`
4. `nerfed_items: list[str]`
5. `neutral_items: list[str]`
6. `confidence: float`
7. `raw_summary: str`

## 6) Podzial pracy - pelny plan zespolowy

### Zwidek (Osoba A) - Data Scraper + Code Review (tylko ten obszar)
#### Zakres odpowiedzialnosci
1. Implementacja `ingestion/scraper.py` i `ingestion/parsers.py`.
2. Utrzymanie selektorow i mapowania danych.
3. Testy scrapera (API, HTML, fallback).
4. Code review wszystkich PR-ow (quality gate).

#### Taski wykonawcze
1. Sprawdzic czy StalcraftDB ma endpoint JSON i opisac URL-e.
2. Zaimplementowac klienta `requests` z timeout/retry.
3. Zrobic parser HTML tabeli cen.
4. Dodac fallback dla stron JS-only (interfejs pod Playwright).
5. Dodac logowanie bledow i debug snapshotow HTML.
6. Napisac testy jednostkowe parserow i testy regresyjne.
7. Prowadzic `docs/selectors.md`.

#### Definition of Done dla Zwidek
1. Scraper zwraca poprawny format danych dla min. 20 itemow.
2. Nie crashuje przy braku tabeli/zmianie DOM.
3. Pokrycie testami parserow min. 80%.
4. Review checklista jest gotowa i uzywana na kazdym PR.

#### Prompt roboczy dla Zwidek
```text
Jestes odpowiedzialny za modul scrapera i code review.
Cel: dostarczyc stabilny scraper StalcraftDB i testy parserow.
Wymagania:
- API-first, HTML fallback, przygotowanie pod Playwright.
- Brak typu any, pelne typowanie, guard clauses.
- Kazda operacja async/IO z czytelnym logowaniem bledow.
Wyjscie:
1) lista endpointow i selektorow,
2) gotowy kod scrapera,
3) testy i raport co zostalo pokryte,
4) lista ryzyk po stronie danych.
```

### Luxber (Osoba B) - Backend, Storage, LLM
#### Zakres odpowiedzialnosci
1. `storage/*` - modele, repozytorium, operacje DB.
2. `analysis/price_anomaly.py` i reguly sygnalowe.
3. `analysis/patch_analyzer.py` (OpenAI + adapter Ollama).
4. `core/scheduler.py` i orchestracja jobow.

#### Taski wykonawcze
1. Zaprojektowac schemat tabel: `price_history`, `patch_analysis`, `alerts`.
2. Dodac warstwe repository (zapis, odczyt 7d, deduplikacja).
3. Zaimplementowac pierwsza regule anomalii (>=30% odchylenia od sredniej 7d).
4. Zdefiniowac prompt LLM i kontrakt odpowiedzi JSON.
5. Dodac walidacje odpowiedzi LLM (np. pydantic).
6. Zrobic adapter `provider=openai|ollama`.
7. Dodac scheduler i task runner.

#### Definition of Done dla Luxber
1. Pipeline od zapisu danych do sygnalu dziala lokalnie.
2. Brak duplikatow rekordow dla tego samego snapshotu.
3. Odpowiedz LLM zawsze mapowana do ustalonego JSON schema.
4. Testy jednostkowe i integracyjne przechodza.

#### Prompt roboczy dla Luxber
```text
Jestes odpowiedzialny za backend, baze danych i integracje LLM.
Cel: zbudowac stabilna warstwe storage+analysis z schedulerem.
Wymagania:
- SQLAlchemy + SQLite na MVP.
- Regula anomalii cen i klasyfikacja patch notes (buff/nerf/neutral).
- Adapter providerow LLM (OpenAI i Ollama) pod wspolny interfejs.
- Pelne typowanie, bez any, czytelne logi bledow.
Wyjscie:
1) modele DB i repozytorium,
2) moduly analityczne,
3) scheduler i skrypty uruchomieniowe,
4) test plan i known issues.
```

### Mociur (Osoba C) - UI/UX, Integracje, DevEx
#### Zakres odpowiedzialnosci
1. `notifications/*` - format i estetyka embedow.
2. Konfiguracja projektu (`.env.example`, README, runbook).
3. Lekki health/status (API/dashboard opcjonalnie).
4. Testy integracyjne i przeplyw end-to-end.

#### Taski wykonawcze
1. Zaprojektowac 2 typy embedow: okazja cenowa i patch impact.
2. Dodac builder wiadomosci z kolorami i sekcjami.
3. Przygotowac `README.md` i instrukcje lokalnego startu.
4. Dodac `.env.example` i opis wszystkich zmiennych.
5. Przygotowac healthcheck (`api/health.py`) + prosty widok statusu.
6. Dopracowac runbook reakcji na awarie.

#### Definition of Done dla Mociur
1. Embedy sa czytelne i stale strukturalnie.
2. Nowa osoba uruchamia projekt wg README w <=20 minut.
3. Integracyjny scenariusz E2E przechodzi lokalnie.
4. Healthcheck zwraca status modulow.

#### Prompt roboczy dla Mociur
```text
Jestes odpowiedzialny za UX powiadomien, integracje i DevEx.
Cel: dostarczyc czytelna warstwe komunikacji i onboarding projektu.
Wymagania:
- Discord embedy musza byc estetyczne i informacyjne.
- Dokumentacja uruchomienia ma byc jednoznaczna.
- Dodaj health/status i podstawowy monitoring.
- Pelne typowanie i obsluga bledow.
Wyjscie:
1) notifier + message builder,
2) README i .env.example,
3) test scenariusza E2E,
4) runbook i checklista utrzymaniowa.
```

## 7) Kolejnosc realizacji (punkt po punkcie)
1. Uzgodnic liste itemow monitorowanych i zakres patch notes.
2. Uzgodnic kontrakt danych i nazwy tabel.
3. Implementacja scrapera (A) + testy parserow.
4. Implementacja storage i modeli (B).
5. Implementacja analizy anomalii (B).
6. Implementacja notifiera i formatu embedow (C).
7. Integracja end-to-end: scraper -> DB -> analiza -> Discord (B+C).
8. Implementacja analizy patch notes przez LLM (B).
9. Integracja alertu patchowego (C).
10. Stabilizacja: retry, deduplikacja, logi (A+B+C).
11. Dokumentacja i onboarding (C).
12. Finalne testy i review gate (A jako reviewer).

## 8) Harmonogram sprintow (4 sprinty)
### Sprint 1 - Fundamenty
1. Repo setup, config, wymagania, struktura.
2. Scraper MVP (API/HTML).
3. Baza SQLite + modele.
4. Pierwszy zapis danych historycznych.

### Sprint 2 - Alerty cenowe
1. Reguly anomalii cen.
2. Discord embedy dla okazji.
3. Scheduler i job ingestion+scan.
4. Testy E2E podstawowego flow.

### Sprint 3 - Patch Notes AI
1. Integracja OpenAI i adapter Ollama.
2. Prompt engineering i schema JSON.
3. Alerty patchowe na Discord.
4. Walidacja i fallback przy bledach LLM.

### Sprint 4 - Hardening i release
1. Retry/backoff i idempotencja.
2. CI (lint + tests).
3. Runbook operacyjny.
4. Finalna stabilizacja i release v1.

## 9) Rytualy pracy zespolowej
1. Daily 15 min: status, blokery, plan dnia.
2. PR workflow: max 300 linii, minimum 1 reviewer (A obowiazkowo).
3. Definition of Ready: task ma cel, scope, kryteria akceptacji.
4. Definition of Done: kod + testy + logi + dokumentacja.

## 10) Ryzyka i plan awaryjny
1. Zmiana struktury strony StalcraftDB -> parser guard clauses + szybkie hotfixy.
2. Brak stabilnego API -> fallback HTML/Playwright.
3. Halucynacje LLM -> schema validation i confidence threshold.
4. Spam alertow -> cooldown i agregacja alertow.
5. Duplikaty danych -> hash snapshotu + unique constraints.

## 11) Checklisty odbioru
### Odbior techniczny
1. Wszystkie moduly przechodza testy.
2. Brak krytycznych errorow w logach.
3. Wszystkie sekrety sa poza kodem (ENV).
4. Embedy sa zgodne z UX formatem.

### Odbior produktowy
1. Co najmniej 1 realna okazja zostala poprawnie zidentyfikowana.
2. Co najmniej 1 patch został przeanalizowany i opublikowany.
3. Zespol potrafi uruchomic projekt od zera wg README.

## 12) Definicja finalnego sukcesu
Projekt jest uznany za gotowy, gdy:
1. Dziala automatyczny cykl pobierania, analizy i alertowania.
2. Analiza patch notes dziala powtarzalnie i zwraca strukturalny JSON.
3. Alerty Discord sa czytelne, trafne i nie zalewaja kanalu.
4. Kod jest utrzymywalny, testowalny i gotowy do dalszego rozwoju.
