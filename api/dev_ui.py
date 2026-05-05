from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.health import build_health_response, record_anomaly_scan, record_ingestion
from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_price_opportunity_embed
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, db_ping

APP_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = APP_ROOT / "ui" / "templates"
STATIC_DIR = APP_ROOT / "ui" / "static"
RAW_DATA_DIR = APP_ROOT / "data" / "raw"
HERO_IMAGE_PATH = Path(
    r"C:\Users\Muzeum\.cursor\projects\c-Users-Muzeum-Desktop-projekt-pawel-mociek\assets\c__Users_Muzeum_AppData_Roaming_Cursor_User_workspaceStorage_87cc70eebfd48b9c1940e355dbd4ecba_images_image-b79a2e3c-c5bb-4a4f-bc6c-d99f76ca03a0.png"
)
logger = logging.getLogger(__name__)


class SnapshotPayload(TypedDict):
    snapshot_id: str
    generated_at: str
    records: list[dict[str, object]]


@dataclass(frozen=True)
class DashboardStats:
    total_records: int
    sources_summary: str
    last_snapshot_id: str
    last_snapshot_at: str
    unique_items: int
    avg_price: float


@dataclass(frozen=True)
class ZoneStatus:
    name: str
    state: str
    detail: str


app = FastAPI(title="Stalcraft Market Web Console", version="0.2.0")
app.mount("/dev/static", StaticFiles(directory=str(STATIC_DIR)), name="dev-static")
if HERO_IMAGE_PATH.exists():
    app.mount("/hero-assets", StaticFiles(directory=str(HERO_IMAGE_PATH.parent)), name="hero-assets")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.get("/")
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=302)


@app.get("/dev")
def dev_compat_redirect() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=302)


@app.get("/app")
def app_dashboard(request: Request) -> object:
    app_cfg = load_config(project_root=APP_ROOT)
    db = create_database(app_cfg.database_url)
    health = build_health_response(db_check=lambda: db_ping(db))
    snapshot = _load_latest_snapshot()
    stats = _build_stats(snapshot=snapshot)
    latest_records = sorted(
        snapshot["records"],
        key=lambda row: str(row.get("observed_at", "")),
        reverse=True,
    )[:10]
    top_expensive = sorted(
        snapshot["records"],
        key=lambda row: float(row.get("price", 0) or 0),
        reverse=True,
    )[:6]
    top_expensive = [_decorate_record(row) for row in top_expensive]
    latest_records_decorated = [_decorate_record(row) for row in latest_records]
    chart_payload = _build_price_chart(snapshot["records"])
    zones = _build_zone_statuses(health=health, stats=stats)
    return templates.TemplateResponse(
        request=request,
        name="web_dashboard.html",
        context={
            "title": "Stalcraft Market Analyzer",
            "subtitle": "Developer Console",
            "active_nav": "dashboard",
            "health": health,
            "stats": stats,
            "latest_records": latest_records_decorated,
            "top_expensive": top_expensive,
            "chart_labels": chart_payload["labels"],
            "chart_values": chart_payload["values"],
            "zones": zones,
            "hero_image_url": _hero_image_url(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "flash_message": request.query_params.get("msg", ""),
            "flash_level": request.query_params.get("level", "ok"),
        },
    )


@app.get("/app/market")
def app_market(request: Request) -> object:
    snapshot = _load_latest_snapshot()
    source_filter = request.query_params.get("source", "").strip().lower()
    rarity_filter = request.query_params.get("rarity", "").strip().lower()
    faction_filter = request.query_params.get("faction", "").strip().lower()
    min_price_raw = request.query_params.get("min_price", "").strip()
    query = request.query_params.get("q", "").strip().lower()

    min_price = 0.0
    if min_price_raw and _is_number(min_price_raw):
        min_price = float(min_price_raw)

    decorated_all = [_decorate_record(row) for row in snapshot["records"]]
    filtered_records = decorated_all
    if source_filter:
        filtered_records = [
            row
            for row in filtered_records
            if str(row.get("source", "")).lower() == source_filter
        ]
    if rarity_filter:
        filtered_records = [
            row
            for row in filtered_records
            if str(row.get("rarity", "")).lower() == rarity_filter
        ]
    if faction_filter:
        filtered_records = [
            row
            for row in filtered_records
            if str(row.get("faction", "")).lower() == faction_filter
        ]
    if min_price > 0:
        filtered_records = [
            row
            for row in filtered_records
            if _is_number(row.get("price")) and float(str(row.get("price"))) >= min_price
        ]
    if query:
        filtered_records = [
            row
            for row in filtered_records
            if query in str(row.get("item_name", "")).lower() or query in str(row.get("item_id", "")).lower()
        ]

    sorted_records = sorted(
        filtered_records,
        key=lambda row: str(row.get("observed_at", "")),
        reverse=True,
    )
    return templates.TemplateResponse(
        request=request,
        name="web_market.html",
        context={
            "title": "Stalcraft Market Analyzer",
            "subtitle": "Market Feed",
            "active_nav": "market",
            "records": sorted_records[:200],
            "current_source": source_filter,
            "current_rarity": rarity_filter,
            "current_faction": faction_filter,
            "current_min_price": min_price_raw,
            "current_query": query,
            "available_sources": _collect_sources(snapshot["records"]),
            "available_rarities": _collect_rarities(decorated_all),
            "available_factions": _collect_factions(decorated_all),
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_at": snapshot["generated_at"],
            "records_total": len(snapshot["records"]),
            "records_filtered": len(filtered_records),
            "hero_image_url": _hero_image_url(),
            "flash_message": request.query_params.get("msg", ""),
            "flash_level": request.query_params.get("level", "ok"),
        },
    )


@app.get("/app/actions")
def app_actions(request: Request) -> object:
    app_cfg = load_config(project_root=APP_ROOT)
    db = create_database(app_cfg.database_url)
    health = build_health_response(db_check=lambda: db_ping(db))
    return templates.TemplateResponse(
        request=request,
        name="web_actions.html",
        context={
            "title": "Stalcraft Market Analyzer",
            "subtitle": "Actions & Ops",
            "active_nav": "actions",
            "health": health,
            "hero_image_url": _hero_image_url(),
            "flash_message": request.query_params.get("msg", ""),
            "flash_level": request.query_params.get("level", "ok"),
        },
    )


@app.get("/dev/api/status")
def dev_status_api() -> JSONResponse:
    app_cfg = load_config(project_root=APP_ROOT)
    db = create_database(app_cfg.database_url)
    health = build_health_response(db_check=lambda: db_ping(db))
    snapshot = _load_latest_snapshot()
    stats = _build_stats(snapshot=snapshot)
    return JSONResponse(
        {
            "health": health,
            "stats": {
                "total_records": stats.total_records,
                "sources_summary": stats.sources_summary,
                "last_snapshot_id": stats.last_snapshot_id,
                "last_snapshot_at": stats.last_snapshot_at,
                "unique_items": stats.unique_items,
                "avg_price": stats.avg_price,
            },
        }
    )


@app.post("/dev/actions/mark-ingestion")
def mark_ingestion() -> RedirectResponse:
    record_ingestion()
    return RedirectResponse(
        url=f"/app/actions?level=ok&msg={quote('Ingestion timestamp updated.')}",
        status_code=303,
    )


@app.post("/dev/actions/mark-anomaly")
def mark_anomaly() -> RedirectResponse:
    record_anomaly_scan()
    return RedirectResponse(
        url=f"/app/actions?level=ok&msg={quote('Anomaly scan timestamp updated.')}",
        status_code=303,
    )


@app.post("/dev/actions/send-test-alert")
def send_test_alert() -> RedirectResponse:
    try:
        notifier = DiscordNotifier.from_env()
        test_embed = build_price_opportunity_embed(
            {
                "severity": "medium",
                "item_name": "Dev Console Test",
                "price": 12750,
                "deviation_pct": -17.4,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source": "dev_ui",
                "notes": "Test alert generated from developer dashboard.",
            }
        )
        notifier.send_price_alert({"source": "dev_ui"}, embeds=[test_embed])
        return RedirectResponse(
            url=f"/app/actions?level=ok&msg={quote('Discord test alert sent.')}",
            status_code=303,
        )
    except Exception as error:
        # The dashboard action should not crash the whole app.
        logger.warning("Dev UI test alert failed: %s", error)
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Discord test alert failed. Check logs and env.')}",
            status_code=303,
        )


def _load_latest_snapshot() -> SnapshotPayload:
    if not RAW_DATA_DIR.exists():
        return {"snapshot_id": "none", "generated_at": "n/a", "records": []}

    snapshot_files = sorted(RAW_DATA_DIR.glob("market_snapshot_*.json"))
    if not snapshot_files:
        return {"snapshot_id": "none", "generated_at": "n/a", "records": []}

    latest = snapshot_files[-1]
    try:
        content = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"snapshot_id": "invalid", "generated_at": "n/a", "records": []}

    snapshot_id = str(content.get("snapshot_id", "unknown"))
    generated_at = str(content.get("generated_at", "n/a"))
    raw_records = content.get("records", [])
    records: list[dict[str, object]] = raw_records if isinstance(raw_records, list) else []
    return {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "records": records,
    }


def _build_stats(snapshot: SnapshotPayload) -> DashboardStats:
    records = snapshot["records"]
    source_counts: dict[str, int] = {}
    for record in records:
        source = str(record.get("source", "unknown"))
        source_counts[source] = source_counts.get(source, 0) + 1

    if source_counts:
        parts = [f"{name}: {count}" for name, count in sorted(source_counts.items())]
        sources_summary = ", ".join(parts)
    else:
        sources_summary = "No records yet."

    unique_items = len(
        {
            str(record.get("item_id", "")).strip()
            for record in records
            if str(record.get("item_id", "")).strip()
        }
    )

    prices = [
        float(record.get("price", 0) or 0)
        for record in records
        if _is_number(record.get("price"))
    ]
    avg_price = sum(prices) / len(prices) if prices else 0.0

    return DashboardStats(
        total_records=len(records),
        sources_summary=sources_summary,
        last_snapshot_id=snapshot["snapshot_id"],
        last_snapshot_at=snapshot["generated_at"],
        unique_items=unique_items,
        avg_price=avg_price,
    )


def _collect_sources(records: list[dict[str, object]]) -> list[str]:
    return sorted({str(record.get("source", "")).strip() for record in records if str(record.get("source", "")).strip()})


def _collect_rarities(records: list[dict[str, object]]) -> list[str]:
    return sorted({str(record.get("rarity", "")).strip() for record in records if str(record.get("rarity", "")).strip()})


def _collect_factions(records: list[dict[str, object]]) -> list[str]:
    return sorted({str(record.get("faction", "")).strip() for record in records if str(record.get("faction", "")).strip()})


def _is_number(value: object) -> bool:
    try:
        float(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _decorate_record(record: dict[str, object]) -> dict[str, object]:
    price_raw = record.get("price", 0)
    price = float(price_raw) if _is_number(price_raw) else 0.0
    rarity = _rarity_from_price(price)
    faction = _faction_from_source(str(record.get("source", "")))
    decorated = dict(record)
    decorated["rarity"] = rarity
    decorated["faction"] = faction
    return decorated


def _rarity_from_price(price: float) -> str:
    if price >= 45000:
        return "legendary"
    if price >= 25000:
        return "epic"
    if price >= 12000:
        return "rare"
    if price >= 6000:
        return "uncommon"
    return "common"


def _faction_from_source(source: str) -> str:
    source_lower = source.lower()
    if "api" in source_lower:
        return "signal-corps"
    if "html" in source_lower:
        return "scout-unit"
    if "mock" in source_lower:
        return "sim-lab"
    return "zone-neutral"


def _hero_image_url() -> str:
    if not HERO_IMAGE_PATH.exists():
        return ""
    return f"/hero-assets/{HERO_IMAGE_PATH.name}"


def _build_price_chart(records: list[dict[str, object]]) -> dict[str, list[object]]:
    sorted_records = sorted(
        records,
        key=lambda row: str(row.get("observed_at", "")),
    )
    labels: list[object] = []
    values: list[object] = []
    for row in sorted_records[-16:]:
        observed_at = str(row.get("observed_at", ""))[:19] or "n/a"
        price_raw = row.get("price", 0)
        price_value = float(price_raw) if _is_number(price_raw) else 0.0
        labels.append(observed_at)
        values.append(price_value)
    return {"labels": labels, "values": values}


def _build_zone_statuses(health: dict[str, object], stats: DashboardStats) -> list[ZoneStatus]:
    market_state = "stable" if stats.total_records >= 10 else "warming-up"
    pipeline_state = "online" if str(health.get("db_status", "")) == "ok" else "degraded"
    relay_state = "ready" if str(health.get("webhook_status", "")) == "ok" else "attention"
    return [
        ZoneStatus(
            name="Market Feed",
            state=market_state,
            detail=f"{stats.total_records} records captured",
        ),
        ZoneStatus(
            name="Data Pipeline",
            state=pipeline_state,
            detail=f"DB: {health.get('db_status', 'unknown')}",
        ),
        ZoneStatus(
            name="Alert Relay",
            state=relay_state,
            detail=f"Webhook: {health.get('webhook_status', 'unknown')}",
        ),
    ]
