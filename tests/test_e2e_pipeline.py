from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

import pytest

from notifications.discord_notifier import DiscordNotifier, DiscordNotifierConfig
from notifications.message_builder import build_price_opportunity_embed


@dataclass(frozen=True, slots=True)
class ScrapedMarketRow:
    item_name: str
    price: int
    deviation_pct: float
    observed_at: str
    source: str


def _mock_scraper_rows() -> list[ScrapedMarketRow]:
    # One "normal", one strong opportunity to ensure a signal is detected.
    return [
        ScrapedMarketRow(
            item_name="Common Ammo",
            price=1200,
            deviation_pct=-2.1,
            observed_at="2026-04-28T18:00:00Z",
            source="scraper:mock",
        ),
        ScrapedMarketRow(
            item_name="Worn Seeker Backpack",
            price=12400,
            deviation_pct=-18.4,
            observed_at="2026-04-28T18:20:00Z",
            source="scraper:mock",
        ),
    ]


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          item_name TEXT NOT NULL,
          price INTEGER NOT NULL,
          deviation_pct REAL NOT NULL,
          observed_at TEXT NOT NULL,
          source TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _persist_rows(conn: sqlite3.Connection, rows: list[ScrapedMarketRow]) -> None:
    conn.executemany(
        """
        INSERT INTO market_observations (item_name, price, deviation_pct, observed_at, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(r.item_name, r.price, r.deviation_pct, r.observed_at, r.source) for r in rows],
    )
    conn.commit()


def _find_price_opportunities(
    conn: sqlite3.Connection, *, threshold_pct: float = 10.0
) -> list[dict[str, object]]:
    """
    Minimal anomaly detector for E2E test.
    Treat large negative deviation as a price opportunity.
    """
    cur = conn.execute(
        """
        SELECT item_name, price, deviation_pct, observed_at, source
        FROM market_observations
        WHERE deviation_pct <= ?
        ORDER BY deviation_pct ASC
        """,
        (-abs(threshold_pct),),
    )
    out: list[dict[str, object]] = []
    for item_name, price, deviation_pct, observed_at, source in cur.fetchall():
        out.append(
            {
                "severity": "high",
                "item_name": item_name,
                "price": price,
                "deviation_pct": deviation_pct,
                "observed_at": observed_at,
                "source": source,
                "notes": "E2E test signal",
            }
        )
    return out


class _CapturedRequest:
    def __init__(self, path: str, headers: dict[str, str], body: bytes) -> None:
        self.path = path
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class _WebhookHandler(BaseHTTPRequestHandler):
    captured: list[_CapturedRequest] = []
    lock = threading.Lock()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with _WebhookHandler.lock:
            _WebhookHandler.captured.append(
                _CapturedRequest(
                    path=self.path,
                    headers={k: v for k, v in self.headers.items()},
                    body=body,
                )
            )

        # Discord webhook commonly returns 204 No Content on success.
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        # Silence default HTTP server logs during tests.
        return


class _MockDiscordWebhookServer:
    def __init__(self) -> None:
        self._server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/webhook"

    def start(self) -> None:
        with _WebhookHandler.lock:
            _WebhookHandler.captured.clear()
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def wait_for_requests(self, *, count: int, timeout_s: float = 2.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with _WebhookHandler.lock:
                got = len(_WebhookHandler.captured)
            if got >= count:
                return
            time.sleep(0.02)
        with _WebhookHandler.lock:
            got = len(_WebhookHandler.captured)
        raise AssertionError(f"Expected {count} webhook request(s), got {got}.")

    def captured(self) -> list[_CapturedRequest]:
        with _WebhookHandler.lock:
            return list(_WebhookHandler.captured)


@pytest.fixture()
def webhook_server() -> Callable[[], _MockDiscordWebhookServer]:
    server = _MockDiscordWebhookServer()
    server.start()
    try:
        yield lambda: server
    finally:
        server.stop()


def test_e2e_scraper_db_anomaly_notifier_discord(webhook_server: Callable[[], _MockDiscordWebhookServer]) -> None:
    """
    E2E scenario:
    scraper -> DB -> anomaly scan -> embed builder -> notifier -> Discord webhook (mock).
    """
    server = webhook_server()

    # 1) Scraper (mock)
    scraped = _mock_scraper_rows()
    assert scraped, "Mock scraper returned no rows."

    # 2) DB (sqlite in-memory)
    conn = sqlite3.connect(":memory:")
    _init_db(conn)
    _persist_rows(conn, scraped)

    count = conn.execute("SELECT COUNT(*) FROM market_observations").fetchone()[0]
    assert count == len(scraped), f"Expected {len(scraped)} rows in DB, got {count}."

    # 3) Anomaly scan (minimal detector)
    opportunities = _find_price_opportunities(conn, threshold_pct=10.0)
    assert opportunities, "Expected at least one price opportunity signal."

    # 4) Embed builder (real)
    embed = build_price_opportunity_embed(opportunities[0])  # formatting-only module
    assert "title" in embed and embed["title"], "Embed title missing."
    assert "fields" in embed and embed["fields"], "Embed fields missing."

    # 5) Notifier -> Discord webhook (real notifier, mock HTTP endpoint)
    notifier = DiscordNotifier(
        DiscordNotifierConfig(
            webhook_url=server.url,
            timeout_s=1.0,
            max_retries=0,
            retry_backoff_s=0.0,
        )
    )
    resp = notifier.send_price_alert(opportunities[0], embeds=[embed])
    assert resp.status == "ok", f"Expected notifier ok, got {resp}."

    server.wait_for_requests(count=1, timeout_s=2.0)
    req = server.captured()[0]
    payload = req.json()

    # Assertions with readable failure messages ("error reporting").
    assert payload.get("content") is None, f"Expected content=null, got {payload.get('content')!r}"
    embeds = payload.get("embeds")
    assert isinstance(embeds, list) and embeds, "Expected non-empty embeds list."
    assert embeds[0].get("title", "").startswith("OKAZJA CENOWA"), "Unexpected embed title."
    assert payload.get("allowed_mentions") == {"parse": []}, "allowed_mentions should suppress pings."

