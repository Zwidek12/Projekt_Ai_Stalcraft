from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Mapping, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DbStatus = Literal["ok", "error", "missing"]
WebhookStatus = Literal["ok", "error", "missing"]


class HealthResponse(TypedDict):
    db_status: DbStatus
    webhook_status: WebhookStatus
    last_ingestion_at: str | None
    last_anomaly_scan_at: str | None


DbCheck = Callable[[], None]


@dataclass(frozen=True, slots=True)
class HealthConfig:
    """
    Healthcheck configuration.

    This module stays framework-agnostic. Consumers can:
    - call `build_health_response(...)` in their web framework handler, OR
    - use the provided minimal WSGI app `wsgi_app`.
    """

    webhook_url: str | None = None
    timeout_s: float = 2.5


_last_ingestion_at: datetime | None = None
_last_anomaly_scan_at: datetime | None = None


def record_ingestion(at: datetime | None = None) -> None:
    """Record last successful ingestion timestamp (in-memory)."""
    global _last_ingestion_at
    _last_ingestion_at = _coerce_dt(at) or _now_utc()


def record_anomaly_scan(at: datetime | None = None) -> None:
    """Record last successful anomaly scan timestamp (in-memory)."""
    global _last_anomaly_scan_at
    _last_anomaly_scan_at = _coerce_dt(at) or _now_utc()


def build_health_response(
    *,
    db_check: DbCheck | None = None,
    config: HealthConfig | None = None,
) -> HealthResponse:
    """
    Build health response payload for /health.

    - db_check: optional callable that raises on DB failure (or returns normally on success).
    - config: optional HealthConfig (webhook_url + timeout).
    """
    cfg = config or HealthConfig(webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"))

    db_status: DbStatus = _check_db(db_check)
    webhook_status: WebhookStatus = _check_webhook(cfg.webhook_url, timeout_s=cfg.timeout_s)

    return {
        "db_status": db_status,
        "webhook_status": webhook_status,
        "last_ingestion_at": _format_iso(_last_ingestion_at),
        "last_anomaly_scan_at": _format_iso(_last_anomaly_scan_at),
    }


def wsgi_app(
    environ: Mapping[str, object],
    start_response: Callable[[str, list[tuple[str, str]]], None],
) -> list[bytes]:
    """
    Minimal WSGI app exposing GET /health with JSON output.

    This is intentionally tiny (no external deps). If you already use a web framework,
    you can ignore this and call `build_health_response(...)` directly.
    """
    path = str(environ.get("PATH_INFO", ""))
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()

    if path != "/health":
        start_response("404 Not Found", [("Content-Type", "application/json")])
        return [b'{"error":"not_found"}']

    if method != "GET":
        start_response("405 Method Not Allowed", [("Content-Type", "application/json")])
        return [b'{"error":"method_not_allowed"}']

    payload = build_health_response()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        "200 OK",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _check_db(db_check: DbCheck | None) -> DbStatus:
    if db_check is None:
        return "missing"
    try:
        db_check()
        return "ok"
    except Exception:
        return "error"


def _check_webhook(webhook_url: str | None, *, timeout_s: float) -> WebhookStatus:
    url = (webhook_url or "").strip()
    if not url:
        return "missing"

    # No-spam reachability check:
    # Discord webhook has no "ping" endpoint; instead, we send an intentionally invalid
    # request that should NOT create a message (empty embeds/content) and interpret
    # *any* HTTP response as "reachable". Network/transport errors are "error".
    req = Request(
        url,
        data=b'{"content":null,"embeds":[]}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read(1)
        return "ok"
    except HTTPError:
        # Reachable but rejected (expected for invalid payload) -> still "ok".
        return "ok"
    except (URLError, TimeoutError):
        return "error"


def _format_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def _coerce_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)

