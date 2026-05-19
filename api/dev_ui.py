from __future__ import annotations

import json
import logging
import base64
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypedDict
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.analysis_jobs import run_price_anomaly_scan_job
from api.health import build_health_response, record_anomaly_scan, record_ingestion
from api import ops_state
from api.system_log import install_system_log_handler, tail_system_logs

install_system_log_handler()
from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_price_opportunity_embed
from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.core.pipeline import ingest_items, run_market_pipeline
from stalcraft_market_analyzer.storage.db import create_database, db_ping, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

APP_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = APP_ROOT / "ui" / "templates"
STATIC_DIR = APP_ROOT / "ui" / "static"
RAW_DATA_DIR = APP_ROOT / "data" / "raw"
OPS_STATE_FILE = ops_state.ops_state_path(APP_ROOT)
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


def _utc_day_start(now: datetime | None = None) -> datetime:
    dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _raw_snapshot_file_count() -> int:
    if not RAW_DATA_DIR.is_dir():
        return 0
    return len(list(RAW_DATA_DIR.glob("market_snapshot_*.json")))


def _format_recent_alerts(repo: SqlAlchemyRepository, *, limit: int = 8) -> list[dict[str, object]]:
    rows = repo.fetch_recent_alerts(limit=limit)
    formatted: list[dict[str, object]] = []
    for row in rows:
        created = row["created_at"]
        if isinstance(created, datetime):
            ts = created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            ts = str(created)
        formatted.append(
            {
                "created_at": ts,
                "alert_type": row["alert_type"],
                "fingerprint": row["fingerprint"],
                "item_id": row.get("item_id") or "",
            }
        )
    return formatted


def _form_int(raw: object, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _form_float(raw: object, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _form_bool(raw: object) -> bool:
    return str(raw or "").strip().lower() in ("1", "on", "true", "yes")


def _dev_ui_token() -> str:
    load_config(project_root=APP_ROOT)
    return os.environ.get("DEV_UI_TOKEN", "").strip()


def _is_basic_auth_valid(*, request: Request, token: str) -> bool:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _username, sep, password = decoded.partition(":")
    if not sep:
        return False
    return secrets.compare_digest(password, token)


def _load_ops_jobs() -> dict[str, Any]:
    state = ops_state.load_ops_state(OPS_STATE_FILE)
    jobs = state.get("jobs")
    return jobs if isinstance(jobs, dict) else {}


app = FastAPI(title="Stalcraft Market Web Console", version="0.2.0")
app.mount("/dev/static", StaticFiles(directory=str(STATIC_DIR)), name="dev-static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.middleware("http")
async def dev_ui_auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    token = _dev_ui_token()
    if not token:
        return await call_next(request)

    path = request.url.path
    if path.startswith("/dev/static"):
        return await call_next(request)

    if _is_basic_auth_valid(request=request, token=token):
        return await call_next(request)

    return PlainTextResponse(
        "Dev UI authentication required.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Stalcraft Dev UI"'},
    )


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
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
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
    day_start = _utc_day_start()
    alerts_today = repo.count_alerts_since(since=day_start, alert_type="price_anomaly")
    raw_files = _raw_snapshot_file_count()
    recent_alert_rows = _format_recent_alerts(repo, limit=8)
    ops_jobs = _load_ops_jobs()
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
            "raw_snapshot_files": raw_files,
            "alerts_today": alerts_today,
            "recent_alerts": recent_alert_rows,
            "ops_jobs": ops_jobs,
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
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    health = build_health_response(db_check=lambda: db_ping(db))
    day_start = _utc_day_start()
    return templates.TemplateResponse(
        request=request,
        name="web_actions.html",
        context={
            "title": "Stalcraft Market Analyzer",
            "subtitle": "Actions & Ops",
            "active_nav": "actions",
            "health": health,
            "hero_image_url": _hero_image_url(),
            "raw_snapshot_files": _raw_snapshot_file_count(),
            "alerts_today": repo.count_alerts_since(since=day_start, alert_type="price_anomaly"),
            "recent_alerts": _format_recent_alerts(repo, limit=10),
            "ops_jobs": _load_ops_jobs(),
            "flash_message": request.query_params.get("msg", ""),
            "flash_level": request.query_params.get("level", "ok"),
        },
    )


@app.get("/dev/api/logs")
def dev_logs_api(limit: int = 200) -> JSONResponse:
    lines = tail_system_logs(limit=limit)
    return JSONResponse({"lines": lines, "count": len(lines), "updated_at": datetime.now(timezone.utc).isoformat()})


@app.post("/dev/actions/clear-stuck-jobs")
def clear_stuck_jobs_action() -> RedirectResponse:
    removed = ops_state.clear_stuck_jobs(OPS_STATE_FILE)
    msg = f"Cleared {removed} stuck job(s) in error state." if removed else "No stuck error jobs to clear."
    return RedirectResponse(url=f"/app/actions?level=ok&msg={quote(msg)}", status_code=303)


@app.get("/dev/api/status")
def dev_status_api() -> JSONResponse:
    app_cfg = load_config(project_root=APP_ROOT)
    db = create_database(app_cfg.database_url)
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)
    health = build_health_response(db_check=lambda: db_ping(db))
    snapshot = _load_latest_snapshot()
    stats = _build_stats(snapshot=snapshot)
    day_start = _utc_day_start()
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
            "operations": {
                "raw_snapshot_files": _raw_snapshot_file_count(),
                "price_anomaly_alerts_today": repo.count_alerts_since(
                    since=day_start, alert_type="price_anomaly"
                ),
                "jobs": _load_ops_jobs(),
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


@app.post("/dev/actions/run-price-anomalies")
def run_price_anomalies_scan() -> RedirectResponse:
    t0 = time.perf_counter()
    try:
        app_cfg = load_config(project_root=APP_ROOT)
        db = create_database(app_cfg.database_url)
        init_schema(db)
        repo = SqlAlchemyRepository(db=db)

        result = run_price_anomaly_scan_job(repo=repo, send_discord=False)
        record_anomaly_scan()

        msg = (
            f"Anomaly scan: items={result.get('scanned_items')} signals={result.get('signals_found')} "
            f"inserted={result.get('alerts_inserted')} deduped={result.get('alerts_deduped')}"
        )
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="anomaly_scan",
            status="ok",
            message=msg,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={k: result.get(k) for k in result},
        )
        return RedirectResponse(url=f"/app/actions?level=ok&msg={quote(msg)}", status_code=303)
    except Exception as error:
        logger.warning("Price anomaly scan failed: %s", error)
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="anomaly_scan",
            status="error",
            message=str(error),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Price anomaly scan failed. Check logs.')}",
            status_code=303,
        )


@app.post("/dev/actions/run-price-anomalies-discord")
def run_price_anomalies_scan_discord() -> RedirectResponse:
    t0 = time.perf_counter()
    try:
        app_cfg = load_config(project_root=APP_ROOT)
        db = create_database(app_cfg.database_url)
        init_schema(db)
        repo = SqlAlchemyRepository(db=db)

        result = run_price_anomaly_scan_job(repo=repo, send_discord=True)
        record_anomaly_scan()

        level = "ok"
        if int(result.get("discord_failed", 0) or 0) > 0:
            level = "error"

        msg = (
            f"Anomaly scan+Discord: items={result.get('scanned_items')} signals={result.get('signals_found')} "
            f"inserted={result.get('alerts_inserted')} deduped={result.get('alerts_deduped')} "
            f"sent={result.get('discord_sent')} failed={result.get('discord_failed')}"
        )
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="anomaly_scan_discord",
            status="ok" if level == "ok" else "error",
            message=msg,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={k: result.get(k) for k in result},
        )
        return RedirectResponse(url=f"/app/actions?level={level}&msg={quote(msg)}", status_code=303)
    except Exception as error:
        logger.warning("Price anomaly scan (discord) failed: %s", error)
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="anomaly_scan_discord",
            status="error",
            message=str(error),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Price anomaly scan failed. Check logs.')}",
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


@app.post("/dev/actions/run-ingestion")
async def run_ingestion_action(request: Request) -> RedirectResponse:
    t0 = time.perf_counter()
    form = await request.form()
    items = str(form.get("items", "")).strip()
    if not items:
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="ingestion",
            status="error",
            message="Missing item ids",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Ingestion: provide at least one item id.')}",
            status_code=303,
        )

    timeout_seconds = max(3, _form_int(form.get("timeout_seconds"), 15))
    base_url = str(form.get("base_url") or "").strip()
    region = str(form.get("region") or "").strip()

    try:
        rc = ingest_items(
            project_root=APP_ROOT,
            items_csv=items,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
            region=region,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0
        if rc != 0:
            msg = f"Ingestion exited with code {rc}."
            ops_state.record_job_run(
                path=OPS_STATE_FILE,
                job_key="ingestion",
                status="error",
                message=msg,
                duration_ms=duration_ms,
                detail={"exit_code": rc, "items": items},
            )
            return RedirectResponse(url=f"/app/actions?level=error&msg={quote(msg)}", status_code=303)

        record_ingestion()
        msg = "Ingestion completed and DB updated."
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="ingestion",
            status="ok",
            message=msg,
            duration_ms=duration_ms,
            detail={"items": items},
        )
        return RedirectResponse(url=f"/app/actions?level=ok&msg={quote(msg)}", status_code=303)
    except Exception as error:
        logger.warning("Dev UI ingestion failed: %s", error)
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="ingestion",
            status="error",
            message=str(error),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Ingestion failed. See server logs.')}",
            status_code=303,
        )


@app.post("/dev/actions/run-pipeline")
async def run_pipeline_action(request: Request) -> RedirectResponse:
    t0 = time.perf_counter()
    form = await request.form()
    items = str(form.get("items", "")).strip()
    if not items:
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="pipeline",
            status="error",
            message="Missing item ids",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Pipeline: provide at least one item id.')}",
            status_code=303,
        )

    args = SimpleNamespace(
        items=items,
        timeout_seconds=max(3, _form_int(form.get("timeout_seconds"), 15)),
        base_url=str(form.get("base_url") or "").strip(),
        region=str(form.get("region") or "").strip(),
        recent_hours=max(1, _form_int(form.get("recent_hours"), 48)),
        baseline_days=max(1, _form_int(form.get("baseline_days"), 7)),
        min_samples=max(3, _form_int(form.get("min_samples"), 6)),
        deal_pct=_form_float(form.get("deal_pct"), -35.0),
        spike_pct=_form_float(form.get("spike_pct"), 60.0),
        send_discord=_form_bool(form.get("send_discord")),
        force_discord_notify=_form_bool(form.get("force_discord_notify")),
        patch_version=str(form.get("patch_version") or "").strip(),
        patch_notes_file=str(form.get("patch_notes_file") or "").strip(),
        patch_notes=str(form.get("patch_notes") or ""),
        send_patch_discord=_form_bool(form.get("send_patch_discord")),
        discord_test=_form_bool(form.get("discord_test")),
    )

    try:
        rc = run_market_pipeline(project_root=APP_ROOT, args=args)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        if rc != 0:
            msg = f"Pipeline finished with exit code {rc}."
            ops_state.record_job_run(
                path=OPS_STATE_FILE,
                job_key="pipeline",
                status="error",
                message=msg,
                duration_ms=duration_ms,
                detail={"exit_code": rc, "items": items},
            )
            return RedirectResponse(url=f"/app/actions?level=error&msg={quote(msg)}", status_code=303)

        msg = "Pipeline OK: ingest + anomaly scan completed."
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="pipeline",
            status="ok",
            message=msg,
            duration_ms=duration_ms,
            detail={
                "items": items,
                "send_discord": bool(args.send_discord),
                "force_discord_notify": bool(args.force_discord_notify),
            },
        )
        return RedirectResponse(url=f"/app/actions?level=ok&msg={quote(msg)}", status_code=303)
    except Exception as error:
        logger.warning("Dev UI pipeline failed: %s", error)
        ops_state.record_job_run(
            path=OPS_STATE_FILE,
            job_key="pipeline",
            status="error",
            message=str(error),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            detail={},
        )
        return RedirectResponse(
            url=f"/app/actions?level=error&msg={quote('Pipeline failed. See server logs.')}",
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
    for candidate in sorted(STATIC_DIR.glob("hero*")):
        if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return f"/dev/static/{candidate.name}"
    return ""


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
