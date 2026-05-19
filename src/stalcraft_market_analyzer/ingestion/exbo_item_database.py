from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .catalog import normalize_catalog_rarity

logger = logging.getLogger(__name__)

QUALITY_KEY_PREFIX = "core.quality."


@dataclass(frozen=True, slots=True)
class ExboItemDatabaseConfig:
    repo_owner: str = "EXBO-Studio"
    repo_name: str = "stalcraft-database"
    ref: str = "main"
    realm: str = "global"
    timeout_seconds: int = 20
    max_retries: int = 3
    backoff_factor: float = 0.5
    cache_path: Path | None = None
    refresh_cache: bool = False


def fetch_exbo_artifact_rarity_index(
    *,
    config: ExboItemDatabaseConfig,
    item_ids: set[str] | None = None,
) -> dict[str, str]:
    if config.cache_path is not None and config.cache_path.is_file() and not config.refresh_cache:
        return _load_cached_rarity_index(config.cache_path)

    session = _build_session(config=config)
    paths = _fetch_artifact_item_paths(session=session, config=config, item_ids=item_ids)
    rarity_index: dict[str, str] = {}
    for path in paths:
        payload = _fetch_raw_item(session=session, config=config, path=path)
        if payload is None:
            continue
        item_id = str(payload.get("id") or Path(path).stem).strip()
        rarity = _rarity_from_item_payload(payload)
        if item_id and rarity != "unknown":
            rarity_index[item_id] = rarity

    if config.cache_path is not None:
        config.cache_path.parent.mkdir(parents=True, exist_ok=True)
        config.cache_path.write_text(json.dumps(rarity_index, indent=2, sort_keys=True), encoding="utf-8")
    return rarity_index


def _load_cached_rarity_index(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"EXBO item rarity cache is not a JSON object: {path}")
    return {
        str(item_id): rarity
        for item_id, value in raw.items()
        if (rarity := normalize_catalog_rarity(str(value))) != "unknown"
    }


def _fetch_artifact_item_paths(
    *,
    session: requests.Session,
    config: ExboItemDatabaseConfig,
    item_ids: set[str] | None,
) -> list[str]:
    url = _github_api_url(config=config, path=f"git/trees/{config.ref}")
    response = session.get(url, params={"recursive": "1"}, timeout=config.timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return []

    wanted = {item_id.strip() for item_id in item_ids or set() if item_id.strip()}
    root = f"{config.realm.strip().lower()}/items/artefact/"
    paths: list[str] = []
    tree = payload.get("tree")
    if not isinstance(tree, list):
        return []
    for row in tree:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        if not path.startswith(root) or not path.endswith(".json") or "/_variants/" in path:
            continue
        item_id = Path(path).stem
        if wanted and item_id not in wanted:
            continue
        paths.append(path)
    return sorted(paths)


def _fetch_raw_item(
    *,
    session: requests.Session,
    config: ExboItemDatabaseConfig,
    path: str,
) -> dict[str, Any] | None:
    url = (
        "https://raw.githubusercontent.com/"
        f"{config.repo_owner}/{config.repo_name}/{config.ref}/{path}"
    )
    try:
        response = session.get(url, timeout=config.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except requests.RequestException as error:
        logger.warning("EXBO item database fetch failed for %s: %s", path, error)
        return None
    except ValueError as error:
        logger.warning("EXBO item database JSON decode failed for %s: %s", path, error)
        return None


def _rarity_from_item_payload(payload: dict[str, Any]) -> str:
    color = normalize_catalog_rarity(str(payload.get("color") or "unknown"))
    if color not in {"unknown", "default", "common"}:
        return color
    return "unknown"


def _quality_from_info_blocks(value: Any) -> str:
    for node in _walk_json(value):
        if not isinstance(node, dict):
            continue
        key = str(node.get("key") or "")
        if key.startswith(QUALITY_KEY_PREFIX):
            return normalize_catalog_rarity(key.removeprefix(QUALITY_KEY_PREFIX))
    return "unknown"


def _walk_json(value: Any) -> list[Any]:
    out: list[Any] = [value]
    if isinstance(value, dict):
        for child in value.values():
            out.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_walk_json(child))
    return out


def _github_api_url(*, config: ExboItemDatabaseConfig, path: str) -> str:
    return f"https://api.github.com/repos/{config.repo_owner}/{config.repo_name}/{path}"


def _build_session(*, config: ExboItemDatabaseConfig) -> requests.Session:
    retry = Retry(
        total=config.max_retries,
        connect=config.max_retries,
        read=config.max_retries,
        status=config.max_retries,
        backoff_factor=config.backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"Accept": "application/vnd.github+json"})
    return session
