from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check EXBO API auth and auction quality payloads.")
    parser.add_argument("--item", default="qoq6", help="Item id to probe, e.g. qoq6, wg3p.")
    parser.add_argument("--limit", type=int, default=20, help="Rows per endpoint, max 200.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(project_root=PROJECT_ROOT)
    headers = _auth_headers(
        access_token=cfg.exbo_access_token,
        client_id=cfg.exbo_client_id,
        client_secret=cfg.exbo_client_secret,
    )
    if not headers:
        print("EXBO auth is not configured. Fill EXBO_ACCESS_TOKEN or EXBO_CLIENT_ID + EXBO_CLIENT_SECRET in .env.")
        return 1

    base_url = cfg.exbo_api_base_url.rstrip("/")
    region = cfg.exbo_region.strip().upper() or "EU"
    item_id = str(args.item).strip()
    limit = str(max(1, min(int(args.limit), 200)))

    print(f"EXBO API: {base_url}")
    print(f"Region: {region}")
    print(f"Item: {item_id}")
    print(f"Auth mode: {_auth_mode(headers)}")

    history = _get_json(
        url=f"{base_url}/{region}/auction/{item_id}/history",
        headers=headers,
        params={"additional": "true", "limit": limit},
        timeout_seconds=max(3, int(args.timeout_seconds)),
    )
    lots = _get_json(
        url=f"{base_url}/{region}/auction/{item_id}/lots",
        headers=headers,
        params={"additional": "true", "limit": limit, "sort": "buyout_price", "order": "asc"},
        timeout_seconds=max(3, int(args.timeout_seconds)),
    )

    history_summary = _summarize_rows(history.get("prices") if history else None)
    lots_summary = _summarize_rows(lots.get("lots") if lots else None)
    print("History:", json.dumps(history_summary, ensure_ascii=False, sort_keys=True))
    print("Lots:", json.dumps(lots_summary, ensure_ascii=False, sort_keys=True))

    if history is None and lots is None:
        return 1
    if history_summary["with_qlt"] == 0 and lots_summary["with_qlt"] == 0:
        print("Auth works if statuses are 200, but this probe did not return additional.qlt for the selected item.")
    else:
        print("OK: EXBO returned additional.qlt. Ingestion can store real artifact rarity from this API.")
    return 0


def _auth_headers(*, access_token: str, client_id: str, client_secret: str) -> dict[str, str]:
    token = access_token.strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    if client_id.strip() and client_secret.strip():
        return {"Client-Id": client_id.strip(), "Client-Secret": client_secret.strip()}
    return {}


def _auth_mode(headers: dict[str, str]) -> str:
    return "bearer" if "Authorization" in headers else "client-secret"


def _get_json(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any] | None:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
        print(f"GET {response.url} -> {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except requests.RequestException as error:
        print(f"Request failed: {error}")
        return None
    except ValueError as error:
        print(f"JSON decode failed: {error}")
        return None


def _summarize_rows(rows: Any) -> dict[str, object]:
    if not isinstance(rows, list):
        return {"rows": 0, "with_qlt": 0, "qualities": {}}
    qualities: dict[str, int] = {}
    with_qlt = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        additional = row.get("additional")
        if not isinstance(additional, dict) or "qlt" not in additional:
            continue
        with_qlt += 1
        key = str(additional.get("qlt"))
        qualities[key] = qualities.get(key, 0) + 1
    return {"rows": len(rows), "with_qlt": with_qlt, "qualities": dict(sorted(qualities.items()))}


if __name__ == "__main__":
    raise SystemExit(main())
