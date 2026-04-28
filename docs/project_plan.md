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

#### Plan krok po kroku dla Zwidek (operacyjny)
##### Etap 0 - Wejscie i przygotowanie (0.5 dnia)
1. Potwierdzic liste monitorowanych itemow (ID + nazwa) i zapisac ja w dokumencie roboczym.
2. Spisac z zespolom kontrakt zwracanego rekordu (`item_id`, `item_name`, `price`, `volume`, `observed_at`, `source`).
3. Przygotowac roboczy plik notatek: endpointy, selektory, ryzyka.

**Output etapu:**
1. Lista itemow i kontrakt danych zatwierdzone przez zespol.
2. Startowa wersja `docs/selectors.md`.

##### Etap 1 - Rekonesans zrodla danych (1 dzien)
1. Sprawdzic czy StalcraftDB udostepnia JSON API:
   - przeanalizowac requesty sieciowe strony,
   - sprawdzic paging, limity, parametry zapytan.
2. Jezeli API istnieje:
   - spisac endpointy, parametry i przykladowe odpowiedzi.
3. Jezeli API jest niestabilne:
   - zdefiniowac strategy fallback do HTML.
4. Udokumentowac selektory HTML i potencjalne miejsca podatne na zmiany DOM.

**Output etapu:**
1. Tabela "API vs HTML fallback" z decyzja techniczna.
2. Uzupełnione `docs/selectors.md` (selektory i mapowanie kolumn).

##### Etap 2 - Implementacja scrapera API-first (1 dzien)
1. Zaimplementowac klienta HTTP (`requests`) z:
   - timeout,
   - retry (backoff),
   - obsluga bledow i czytelnym logowaniem.
2. Dodac mapowanie odpowiedzi API do kontraktu rekordu.
3. Dodac guard clauses:
   - brak pola w odpowiedzi,
   - puste rekordy,
   - niepoprawne typy.
4. Zwracac stabilny wynik (lista rekordow albo pusta lista, nigdy crash).

**Output etapu:**
1. Dzialajacy flow API-first.
2. Logi diagnostyczne dla przypadkow blednych.

##### Etap 3 - Parser HTML fallback (1 dzien)
1. Zaimplementowac parser tabeli cen (BeautifulSoup/lxml).
2. Dodac normalizacje wartosci:
   - cena (float),
   - wolumen (int),
   - data (datetime UTC).
3. Dodac obsluge brakow:
   - brak tabeli,
   - zmieniona kolejnosc kolumn,
   - brakujace komorki.
4. Utrzymac te same typy wyjsciowe co w API-first.

**Output etapu:**
1. Spójny fallback HTML.
2. Jednolity format danych niezaleznie od zrodla.

##### Etap 4 - Przygotowanie pod JS-only / Playwright (0.5-1 dnia)
1. Dodac interfejs fallback, ktory mozna podmienic na Playwright.
2. Na MVP zwracac mock z czytelnym oznaczeniem `source`.
3. Opisac warunek przejscia na Playwright (kiedy aktywujemy ten tryb).

**Output etapu:**
1. Gotowy punkt rozszerzenia pod renderowanie JS.
2. Brak blokady projektu na brak Playwright w MVP.

##### Etap 5 - Testy i stabilizacja (1-1.5 dnia)
1. Napisac testy jednostkowe parsera API.
2. Napisac testy parsera HTML na fixture (stabilne probki HTML).
3. Dodac testy regresyjne:
   - brak tabeli,
   - brak kolumny,
   - zly format ceny/dat.
4. Cel: min. 80% pokrycia dla `ingestion/*`.

**Output etapu:**
1. Testy uruchamiane lokalnie i w CI.
2. Raport przypadkow granicznych.

##### Etap 6 - Przekazanie i quality gate (ciagle)
1. Przygotowac checkliste review i stosowac ja do kazdego PR.
2. W review sprawdzac:
   - czy format danych nie zostal zlamany,
   - czy bledy sa logowane i obslugiwane,
   - czy testy pokrywaja nowe sciezki.
3. Raz na sprint robic mini-audyt stabilnosci parsera.

**Output etapu:**
1. Spójna jakosc kodu i mniej regresji.
2. Transparentna historia decyzji review.

##### Priorytety Zwidek (kolejnosc bezdyskusyjna)
1. Stabilnosc danych > szybkosc wdrozenia.
2. API-first > HTML fallback > mock/Playwright.
3. Guard clauses i logi > "cichy fail".
4. Testy regresyjne > nowe funkcje.

##### Gotowa checklista "PR Review by Zwidek"
1. Czy wejsciowy i wyjsciowy kontrakt danych jest zachowany?
2. Czy brak `any` i sa typy zwracane?
3. Czy kazde IO ma obsluge bledu i log?
4. Czy dodano test dla nowej sciezki i scenariusza bledu?
5. Czy fallback nie psuje glownego flow API-first?
6. Czy zmiana nie zwieksza ryzyka duplikatow danych?

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

#### Plan krok po kroku dla Luxber (operacyjny)
##### Etap 0 - Uzgodnienie interfejsow (0.5 dnia)
1. Potwierdzic kontrakt wejscia od scrapera (format rekordu ceny).
2. Potwierdzic kontrakt wyjscia do notifiera (struktura alertu).
3. Zdefiniowac wersje JSON schema dla analizy patch notes.

**Output etapu:**
1. Spis interfejsow miedzy modulami A-B-C.
2. Minimalny dokument `architecture.md` z flow i zaleznosciami.

##### Etap 1 - Storage i modele danych (1 dzien)
1. Zaimplementowac `storage/models.py`:
   - `price_history`,
   - `patch_analysis`,
   - `alerts`.
2. Dodac constraints:
   - indeks po `item_id` i `observed_at`,
   - unikalnosc snapshotu (hash lub klucz biznesowy).
3. Zaimplementowac `storage/db.py` (init engine, session factory).
4. Przygotowac helper inicjalizujacy DB lokalnie.

**Output etapu:**
1. Dzialajacy schemat SQLite.
2. Stabilna warstwa inicjalizacji bazy.

##### Etap 2 - Repository i operacje na danych (1 dzien)
1. Zaimplementowac `storage/repository.py`:
   - insert historii cen,
   - odczyt historii 7d,
   - zapis odczyt patch analysis,
   - zapis alertow.
2. Dodac guard clauses i walidacje danych wejsciowych.
3. Dodac obsluge deduplikacji i idempotencji zapisu.
4. Dolozyc logi techniczne dla odczytow/zapisow.

**Output etapu:**
1. Jednolity interfejs data-access dla calej aplikacji.
2. Brak duplikatow przy ponownym uruchomieniu joba.

##### Etap 3 - Analiza anomalii cenowych (1 dzien)
1. Zaimplementowac `analysis/price_anomaly.py`.
2. Policzac:
   - srednia 7d,
   - procentowe odchylenie od sredniej,
   - score okazji (np. 0-100).
3. Wprowadzic prog alarmowy MVP (np. >=30% ponizej sredniej).
4. Zwracac gotowy obiekt sygnalu do powiadomien.

**Output etapu:**
1. Modol sygnalowy gotowy do podpiecia pod Discord.
2. Czytelny kontrakt obiektu alertu.

##### Etap 4 - Integracja LLM (OpenAI + Ollama) (1-1.5 dnia)
1. Zaimplementowac `analysis/patch_analyzer.py` z adapterem providerow.
2. Dodac wspolny interfejs:
   - `analyze_patch_notes(text: str) -> PatchImpactResult`.
3. Przygotowac prompt systemowy i user prompt pod JSON-only response.
4. Dodac walidacje odpowiedzi:
   - schema validation,
   - fallback przy niepoprawnym JSON.
5. Dodac confidence threshold i flage "requires_manual_review".

**Output etapu:**
1. Powtarzalna analiza buff/nerf/neutral.
2. Kontrolowany fallback przy bledach modelu.

##### Etap 5 - Orkiestracja i scheduler (1 dzien)
1. Zaimplementowac `core/scheduler.py`:
   - job ingestion,
   - job anomaly scan,
   - job patch analysis.
2. Dodac skrypty uruchomieniowe do `scripts/`.
3. Zapewnic idempotencje wielokrotnego uruchamiania.
4. Dodac logowanie start/stop/czas trwania jobow.

**Output etapu:**
1. Dzialajacy pipeline uruchamiany komenda.
2. Przewidywalny harmonogram z logami operacyjnymi.

##### Etap 6 - Testy backendu i stabilizacja (1 dnia)
1. Testy dla repository (insert/read/dedupe).
2. Testy dla anomalii (poprawne liczenie progu i score).
3. Testy dla patch analyzera (mock odpowiedzi LLM).
4. Testy bledu:
   - timeout modelu,
   - niepoprawny JSON,
   - brak danych 7d.

**Output etapu:**
1. Zestaw testow krytycznych sciezek backendu.
2. Raport ryzyk i ograniczen MVP.

##### Priorytety Luxber (kolejnosc bezdyskusyjna)
1. Poprawnosc danych i idempotencja > nowe funkcje.
2. Stabilny kontrakt miedzy modulami > lokalna optymalizacja.
3. Walidacja odpowiedzi LLM > "szybki sukces bez kontroli".
4. Testy backendu > refaktor stylistyczny.

##### Gotowa checklista "PR Review by Luxber"
1. Czy model danych i constraints sa zgodne z kontraktem?
2. Czy operacje DB sa idempotentne?
3. Czy analiza ma test dla sciezki pozytywnej i bledu?
4. Czy integracja LLM ma walidacje schema i fallback?
5. Czy scheduler nie powoduje duplikatow i race conditions?

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

#### Plan krok po kroku dla Mociur (operacyjny)
##### Etap 0 - Uzgodnienie UX i komunikatow (0.5 dnia)
1. Zdefiniowac szablony komunikatow:
   - alert okazji cenowej,
   - alert patch impact.
2. Uzgodnic ton, poziom szczegolow i kolory embedow.
3. Uzgodnic minimalny zestaw pol wymaganych w kazdym komunikacie.

**Output etapu:**
1. Specyfikacja formatu embedow.
2. Makieta tresci alertow zaakceptowana przez zespol.

##### Etap 1 - Implementacja warstwy powiadomien (1 dzien)
1. Zaimplementowac `notifications/discord_notifier.py`.
2. Zaimplementowac `notifications/message_builder.py`:
   - builder okazji,
   - builder patch impact.
3. Dodac mapowanie `severity -> color`.
4. Dodac bezpieczna obsluge bledow webhooka (timeout/retry/log).

**Output etapu:**
1. Powtarzalne embedy o stalej strukturze.
2. Notifier odporny na chwilowe problemy sieciowe.

##### Etap 2 - DevEx i onboarding (0.5-1 dnia)
1. Przygotowac `.env.example` z opisem kazdej zmiennej.
2. Przygotowac `README.md`:
   - instalacja,
   - uruchomienie,
   - debug typowych problemow.
3. Dodac szybki scenariusz "quick start" dla nowej osoby.

**Output etapu:**
1. Dokumentacja uruchomienia od zera.
2. Czas onboardingu <=20 minut.

##### Etap 3 - Healthcheck i obserwowalnosc (0.5-1 dnia)
1. Zaimplementowac `api/health.py` lub skrypt statusu.
2. Raportowac status:
   - polaczenie z DB,
   - status webhooka,
   - czas ostatniego joba.
3. Dodac minimalne metryki w logach (liczba alertow, liczba bledow).

**Output etapu:**
1. Szybka diagnoza "czy system zyje?".
2. Lepsza utrzymywalnosc produkcyjna.

##### Etap 4 - Integracja end-to-end i UX korekty (1 dzien)
1. Podpiac notifier do sygnalow od Luxbera.
2. Przejsc scenariusze:
   - okazja cenowa,
   - patch buff/nerf.
3. Dopracowac czytelnosc embedow:
   - kolejnosc pol,
   - procenty,
   - oznaczenia czasu.
4. Dodac cooldown/agregacje zeby nie spamowac kanalu.

**Output etapu:**
1. Stabilne i czytelne alerty produkcyjne.
2. Mniejsza liczba falszywych/spamowych powiadomien.

##### Etap 5 - Testy integracyjne i runbook (1 dzien)
1. Przygotowac test scenariusza E2E (scraper -> DB -> analiza -> Discord).
2. Opisac runbook:
   - brak danych z ingestii,
   - bledy LLM,
   - niedzialajacy webhook.
3. Dodac checkliste operacyjna po wdrozeniu.

**Output etapu:**
1. Gotowy plan reakcji na awarie.
2. Powtarzalny proces utrzymania systemu.

##### Priorytety Mociur (kolejnosc bezdyskusyjna)
1. Czytelnosc i jakosc alertu > efekty wizualne.
2. Onboarding i dokumentacja > dodatkowe ficzery UI.
3. Stabilnosc integracji > szybkie kosmetyczne zmiany.
4. E2E i runbook > lokalne eksperymenty.

##### Gotowa checklista "PR Review by Mociur"
1. Czy alert jest zrozumialy dla odbiorcy nietechnicznego?
2. Czy format embeda jest spójny miedzy typami alertow?
3. Czy README i `.env.example` sa aktualne po zmianie?
4. Czy healthcheck i logi pomagaja diagnozowac problem?
5. Czy zmiana nie zwieksza ryzyka spamu na Discordzie?

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

## 9.1) Pelny workflow zespolowy (A+B+C)
### Krok 1 - Planowanie tygodnia (poniedzialek)
1. Zespol wybiera 3-6 zadan sprintowych o najwyzszym priorytecie.
2. Kazde zadanie dostaje wlasciciela: A lub B lub C.
3. Zadania maja kryteria akceptacji i przewidziany reviewer.

### Krok 2 - Implementacja dzienna
1. Zwidek realizuje data ingestion i rownolegle robi review PR-ow.
2. Luxber rozwija backend, logike i scheduler na aktualnych danych.
3. Mociur rozwija warstwe alertow, dokumentacje i testy E2E.
4. Po kazdym wiekszym tasku autor robi self-check: typy, logi, testy.

### Krok 3 - Integracja miedzy osobami (codziennie po daily)
1. A przekazuje B aktualny kontrakt danych i ewentualne zmiany parsera.
2. B przekazuje C kontrakt obiektu alertu i status pipeline.
3. C raportuje A/B, czy alerty sa poprawne i czytelne.

### Krok 4 - PR i review gate
1. Autor otwiera PR z opisem: cel, zakres, testy, ryzyka.
2. Zwidek robi review techniczne (kontrakt, odpornosc, regresje).
3. Osoba domenowa (B lub C) robi review funkcjonalne.
4. Merge tylko gdy testy przejda i checklista review jest domknieta.

### Krok 5 - Test end-to-end (co najmniej 2 razy w tygodniu)
1. Uruchomic scenariusz: scraper -> DB -> analiza -> Discord.
2. Potwierdzic:
   - zapis danych,
   - wykrycie sygnalu,
   - publikacje embeda.
3. Zapisac wynik i ewentualne blokery w runbooku.

### Krok 6 - Hardening i zamkniecie sprintu
1. Domknac bugfixy krytyczne.
2. Uporzadkowac dokumentacje po zmianach.
3. Zweryfikowac metryki jakosci (testy, bledy, stabilnosc jobow).
4. Zrobic retro: co poprawic w kolejnym sprincie.

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
