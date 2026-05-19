from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, db_ping, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

APP_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = APP_ROOT / "ui" / "templates"
STATIC_DIR = APP_ROOT / "ui" / "static"

HOT_RARITIES = {"pink", "red", "gold", "exclusive", "legendary", "unique"}
DISPLAY_RARITIES = ["exclusive", "legendary", "unique", "rare", "special", "uncommon", "common", "pink", "red", "gold"]
RARITY_SORT_RANK = {
    "exclusive": 0,
    "legendary": 1,
    "unique": 2,
    "gold": 3,
    "red": 4,
    "pink": 5,
    "rare": 6,
    "special": 7,
    "uncommon": 8,
    "common": 9,
    "unknown": 99,
}

app = FastAPI(title="Stalcraft Market User Web", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="user-static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> object:
    repo = _repo()
    hot_deals = [_decorate_market_row(row) for row in repo.get_hot_deals(rarities=HOT_RARITIES, artifact_only=True, limit=6)]
    fallback_deals = [] if hot_deals else [_decorate_market_row(row) for row in repo.get_hot_deals(artifact_only=False, limit=6)]
    latest_update = _format_update(repo.get_latest_game_update())
    return templates.TemplateResponse(
        request=request,
        name="user_home.html",
        context={
            "title": "Stalcraft Market",
            "active_nav": "home",
            "hot_deals": hot_deals or fallback_deals,
            "using_fallback_deals": not bool(hot_deals) and bool(fallback_deals),
            "latest_update": latest_update,
            "updated_at": _now_iso(),
        },
    )


@app.get("/deals", response_class=HTMLResponse)
def hot_deals(request: Request) -> object:
    repo = _repo()
    rarity = request.query_params.get("rarity", "").strip().lower()
    rarities = {rarity} if rarity else HOT_RARITIES
    deals = [_decorate_market_row(row) for row in repo.get_hot_deals(rarities=rarities, artifact_only=True, limit=100)]
    return templates.TemplateResponse(
        request=request,
        name="user_deals.html",
        context={
            "title": "Hot Deals",
            "active_nav": "deals",
            "deals": deals,
            "current_rarity": rarity,
            "available_rarities": DISPLAY_RARITIES,
        },
    )


@app.get("/artifacts", response_class=HTMLResponse)
def artifacts(request: Request) -> object:
    repo = _repo()
    query = request.query_params.get("q", "").strip()
    rarity = request.query_params.get("rarity", "").strip().lower()
    sort = request.query_params.get("sort", "name").strip().lower()
    rows = [_decorate_market_row(row) for row in repo.search_artifacts(query=query, rarity=rarity, artifact_only=True, limit=200)]
    rows = _sort_artifact_rows(rows, sort=sort)
    return templates.TemplateResponse(
        request=request,
        name="user_artifacts.html",
        context={
            "title": "Artifacts",
            "active_nav": "artifacts",
            "artifacts": rows,
            "current_query": query,
            "current_rarity": rarity,
            "current_sort": sort,
            "available_rarities": DISPLAY_RARITIES,
        },
    )


@app.get("/updates", response_class=HTMLResponse)
def updates(request: Request) -> object:
    repo = _repo()
    update_type = request.query_params.get("type", "").strip().lower()
    rows = [_format_update(row) for row in repo.list_game_updates(update_type=update_type, limit=50)]
    return templates.TemplateResponse(
        request=request,
        name="user_updates.html",
        context={
            "title": "Updates",
            "active_nav": "updates",
            "updates": rows,
            "current_type": update_type,
            "available_types": ["update", "balance", "patch"],
        },
    )


@app.get("/artifacts/{item_id}", response_class=HTMLResponse)
def artifact_detail(request: Request, item_id: str) -> object:
    repo = _repo()
    item = repo.get_catalog_item(item_id=item_id)
    deal = repo.get_latest_deal_for_item(item_id=item_id)
    if item is not None:
        item = _decorate_market_row(item)
    if deal is not None:
        deal = _decorate_market_row(deal)
    history = _format_history(repo.get_item_price_history_1d(item_id=item_id))
    if item is None and deal is None:
        item = {
            "item_id": item_id,
            "item_name": f"item_{item_id}",
            "rarity": "unknown",
            "category": "unknown",
            "external_url": "",
            "is_artifact": False,
        }
    return templates.TemplateResponse(
        request=request,
        name="user_artifact_detail.html",
        context={
            "title": str((item or deal or {}).get("item_name", item_id)),
            "active_nav": "artifacts",
            "item": item,
            "deal": deal,
            "history": history,
            "avg_1d": _average([float(row["price"]) for row in history]),
        },
    )


@app.get("/api/health")
def health_api() -> JSONResponse:
    cfg = load_config(project_root=APP_ROOT)
    db = create_database(cfg.database_url)
    try:
        db_ping(db)
        status = "ok"
    except Exception:
        status = "error"
    return JSONResponse({"status": status, "updated_at": _now_iso()})


def _repo() -> SqlAlchemyRepository:
    cfg = load_config(project_root=APP_ROOT)
    db = create_database(cfg.database_url)
    init_schema(db)
    return SqlAlchemyRepository(db=db)


def _format_history(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    formatted: list[dict[str, object]] = []
    for row in rows:
        observed_at = row["observed_at"]
        if isinstance(observed_at, datetime):
            observed = observed_at.replace(tzinfo=observed_at.tzinfo or timezone.utc).astimezone(timezone.utc)
            observed_str = observed.strftime("%Y-%m-%d %H:%M UTC")
        else:
            observed_str = str(observed_at)
        formatted.append(
            {
                "price": float(row["price"]),
                "observed_at": observed_str,
                "source": str(row["source"]),
                **_decorate_market_row({"rarity": row.get("rarity", "unknown")}),
            }
        )
    return formatted


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _format_update(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    published = row.get("published_at")
    if isinstance(published, datetime):
        published_str = published.replace(tzinfo=published.tzinfo or timezone.utc).astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
    else:
        published_str = str(published or "")
    return {
        **row,
        "published_at_display": published_str,
    }


def _sort_artifact_rows(rows: list[dict[str, object]], *, sort: str) -> list[dict[str, object]]:
    if sort == "rarity":
        return sorted(
            rows,
            key=lambda row: (
                RARITY_SORT_RANK.get(str(row.get("rarity", "unknown")).lower(), 50),
                str(row.get("item_name", "")).lower(),
            ),
        )
    if sort == "rarity_desc":
        return sorted(
            rows,
            key=lambda row: (
                -RARITY_SORT_RANK.get(str(row.get("rarity", "unknown")).lower(), -50),
                str(row.get("item_name", "")).lower(),
            ),
        )
    return sorted(rows, key=lambda row: str(row.get("item_name", "")).lower())


def _decorate_market_row(row: dict[str, object]) -> dict[str, object]:
    decorated = dict(row)
    rarity = str(decorated.get("rarity") or "unknown").strip().lower()
    category = str(decorated.get("category") or "").strip().lower()
    is_artifact = bool(decorated.get("is_artifact", False)) or "artefact" in category or "artifact" in category
    if rarity == "unknown" and is_artifact:
        decorated["rarity_display"] = "artifact"
        decorated["rarity_class"] = "artifact"
    elif rarity == "unknown":
        decorated["rarity_display"] = "market"
        decorated["rarity_class"] = "unknown"
    else:
        decorated["rarity_display"] = rarity
        decorated["rarity_class"] = rarity
    return decorated


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
