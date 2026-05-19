from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from stalcraft_market_analyzer.storage.repository_contract import CatalogItemInput

logger = logging.getLogger(__name__)

HOT_ARTIFACT_RARITIES = frozenset({"rare", "exclusive", "legendary", "unique", "pink", "red", "gold"})


@dataclass(frozen=True, slots=True)
class CatalogRefreshConfig:
    base_url: str
    region: str = "eu"
    timeout_seconds: int = 20
    max_retries: int = 3
    backoff_factor: float = 0.5


def fetch_stalcraftdb_catalog(config: CatalogRefreshConfig) -> list[CatalogItemInput]:
    api_origin = _derive_api_origin(config.base_url)
    if not api_origin:
        logger.warning("Catalog refresh skipped: base_url is not a stalcraftdb.net URL: %s", config.base_url)
        return []

    session = _build_session(config=config)
    endpoint = f"{api_origin}/api/listing/{config.region}/grouped?"
    response = session.get(endpoint, timeout=config.timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    return parse_stalcraftdb_catalog_listing(
        payload=payload,
        base_url=config.base_url,
        region=config.region,
    )


def apply_artifact_rarity_overrides(
    *,
    items: list[CatalogItemInput],
    overrides: dict[str, str],
) -> list[CatalogItemInput]:
    if not overrides:
        return items
    output: list[CatalogItemInput] = []
    normalized = {
        str(item_id).strip(): rarity
        for item_id, value in overrides.items()
        if (rarity := _normalize_rarity(value)) != "unknown"
    }
    for item in items:
        item_id = str(item.get("item_id", "")).strip()
        if item_id not in normalized:
            output.append(item)
            continue
        updated = CatalogItemInput(**dict(item))
        updated["rarity"] = normalized[item_id]
        updated["is_artifact"] = True
        output.append(updated)
    return output


def apply_artifact_rarity_enrichment(
    *,
    items: list[CatalogItemInput],
    rarity_by_item_id: dict[str, str],
) -> list[CatalogItemInput]:
    if not rarity_by_item_id:
        return items

    normalized = {
        str(item_id).strip(): rarity
        for item_id, value in rarity_by_item_id.items()
        if (rarity := normalize_catalog_rarity(value)) != "unknown"
    }
    output: list[CatalogItemInput] = []
    for item in items:
        item_id = str(item.get("item_id", "")).strip()
        current_rarity = normalize_catalog_rarity(str(item.get("rarity") or "unknown"))
        if item_id not in normalized or current_rarity != "unknown":
            output.append(item)
            continue
        updated = CatalogItemInput(**dict(item))
        updated["rarity"] = normalized[item_id]
        updated["is_artifact"] = True
        output.append(updated)
    return output


def load_artifact_rarity_overrides(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        return {
            str(k): rarity
            for k, v in raw.items()
            if (rarity := normalize_catalog_rarity(str(v))) != "unknown"
        }
    if isinstance(raw, list):
        output: dict[str, str] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("item_id", "")).strip()
            rarity = str(row.get("rarity", "")).strip()
            normalized_rarity = normalize_catalog_rarity(rarity)
            if item_id and normalized_rarity != "unknown":
                output[item_id] = normalized_rarity
        return output
    return {}


def parse_stalcraftdb_catalog_listing(
    *,
    payload: Any,
    base_url: str,
    region: str,
) -> list[CatalogItemInput]:
    items: list[CatalogItemInput] = []
    for group_name, raw_item in _iter_listing_items(payload):
        if not isinstance(raw_item, dict):
            continue

        item_id = _extract_item_id(raw_item)
        if not item_id:
            continue

        item_name = _extract_localized_name(raw_item) or f"item_{item_id}"
        category = _normalize_token(
            _first_str(
                raw_item.get("category"),
                raw_item.get("type"),
                raw_item.get("kind"),
                group_name,
            )
            or "unknown"
        )
        rarity = normalize_catalog_rarity(_first_str(raw_item.get("rarity"), raw_item.get("color"), raw_item.get("grade")))
        is_artifact = _is_artifact_item(raw_item=raw_item, group_name=str(group_name), item_name=item_name, category=category)

        items.append(
            CatalogItemInput(
                item_id=item_id,
                item_name=item_name,
                rarity=rarity,
                category=category,
                external_url=_item_external_url(base_url=base_url, region=region, item_id=item_id),
                is_artifact=is_artifact,
            )
        )

    return _dedupe_items(items)


def build_catalog_refresh_summary(items: list[CatalogItemInput]) -> dict[str, object]:
    artifacts = [item for item in items if bool(item.get("is_artifact", False))]
    rarity_counts: dict[str, int] = {}
    for item in items:
        rarity = str(item.get("rarity") or "unknown")
        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
    return {
        "items": len(items),
        "artifacts": len(artifacts),
        "hot_artifacts": sum(1 for item in artifacts if str(item.get("rarity")) in HOT_ARTIFACT_RARITIES),
        "rarities": dict(sorted(rarity_counts.items())),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _iter_listing_items(payload: Any) -> list[tuple[str, Any]]:
    if isinstance(payload, list):
        return [("", item) for item in payload]
    if not isinstance(payload, dict):
        return []

    output: list[tuple[str, Any]] = []
    for group_name, value in payload.items():
        if isinstance(value, list):
            output.extend((str(group_name), item) for item in value)
        elif isinstance(value, dict):
            nested_items = value.get("items")
            if isinstance(nested_items, list):
                output.extend((str(group_name), item) for item in nested_items)
            else:
                output.append((str(group_name), value))
    return output


def _extract_item_id(item: dict[str, Any]) -> str:
    value = _first_str(item.get("id"), item.get("item_id"), item.get("itemId"))
    return (value or "").strip()


def _extract_localized_name(item: dict[str, Any]) -> str:
    name = item.get("name")
    if isinstance(name, str):
        return name.strip()
    if isinstance(name, dict):
        lines = name.get("lines")
        if isinstance(lines, dict):
            for lang in ("en", "pl", "ru"):
                value = lines.get(lang)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("en", "pl", "ru", "value"):
            value = name.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_token(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_catalog_rarity(value: str | None) -> str:
    raw = _normalize_token(value or "")
    if raw in {"common", "uncommon", "special", "rare", "exclusive", "legendary", "unique"}:
        return raw
    if raw in {"pink", "purple", "violet"}:
        return "special"
    if raw in {"red", "orange"}:
        return "unique"
    if raw in {"gold", "yellow"}:
        return "legendary"
    if raw.startswith("core_quality_"):
        return normalize_catalog_rarity(raw.removeprefix("core_quality_"))
    if raw.startswith("core.quality."):
        return normalize_catalog_rarity(raw.removeprefix("core.quality."))
    return raw or "unknown"


def _normalize_rarity(value: str | None) -> str:
    return normalize_catalog_rarity(value)


def _is_artifact_item(*, raw_item: dict[str, Any], group_name: str, item_name: str, category: str) -> bool:
    candidates = [
        group_name,
        item_name,
        category,
        str(raw_item.get("group", "")),
        str(raw_item.get("section", "")),
        str(raw_item.get("categoryName", "")),
    ]
    joined = " ".join(candidates).lower()
    return "artifact" in joined or "artefact" in joined


def _item_external_url(*, base_url: str, region: str, item_id: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.netloc:
        return ""
    if "stalcraftdb.net" in parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/{region}/items/{item_id}"
    return f"{base_url.rstrip()}/items/{item_id}"


def _dedupe_items(items: list[CatalogItemInput]) -> list[CatalogItemInput]:
    seen: dict[str, CatalogItemInput] = {}
    for item in items:
        item_id = str(item.get("item_id", "")).strip()
        if item_id:
            seen[item_id] = item
    return list(seen.values())


def _derive_api_origin(base_url: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.netloc:
        return ""
    if "stalcraftdb.net" in parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _build_session(config: CatalogRefreshConfig) -> requests.Session:
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
    return session
