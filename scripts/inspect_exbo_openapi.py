from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.ingestion.exbo_openapi import (
    filter_exbo_endpoints,
    list_exbo_endpoints,
    load_exbo_openapi,
    validate_exbo_auction_contract,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect EXBO/STALCRAFT OpenAPI endpoints.")
    parser.add_argument("--api-base-url", default="", help="Defaults to EXBO_API_BASE_URL.")
    parser.add_argument("--cache", default="data/exbo_openapi.json", help="OpenAPI cache path.")
    parser.add_argument("--refresh", action="store_true", help="Fetch a fresh OpenAPI spec.")
    parser.add_argument("--tag", default="", help="Optional tag filter, e.g. Auction.")
    parser.add_argument("--auth", choices=("all", "public", "auth"), default="all", help="Filter by auth requirement.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(project_root=PROJECT_ROOT)
    api_base_url = args.api_base_url.strip() or cfg.exbo_api_base_url
    cache_path = (PROJECT_ROOT / str(args.cache)).resolve()

    spec = load_exbo_openapi(
        api_base_url=api_base_url,
        cache_path=cache_path,
        refresh=bool(args.refresh),
    )
    endpoints = filter_exbo_endpoints(
        list_exbo_endpoints(spec),
        tag=str(args.tag),
        auth=str(args.auth),
    )
    contract_errors = validate_exbo_auction_contract(spec)

    if args.json:
        print(
            json.dumps(
                {
                    "api_base_url": api_base_url,
                    "cache_path": str(cache_path),
                    "auction_contract_ok": not contract_errors,
                    "auction_contract_errors": contract_errors,
                    "endpoints": [
                        {
                            "method": endpoint.method,
                            "path": endpoint.path,
                            "summary": endpoint.summary,
                            "tags": list(endpoint.tags),
                            "requires_auth": endpoint.requires_auth,
                        }
                        for endpoint in endpoints
                    ],
                },
                indent=2,
            )
        )
        return 0 if not contract_errors else 1

    print(f"EXBO OpenAPI: {api_base_url}")
    print(f"Cache: {cache_path}")
    print(f"Auction contract: {'ok' if not contract_errors else 'error'}")
    for error in contract_errors:
        print(f"  - {error}")
    print()
    for endpoint in endpoints:
        auth = "auth" if endpoint.requires_auth else "public"
        tags = ",".join(endpoint.tags) if endpoint.tags else "-"
        print(f"{endpoint.method:6} {endpoint.path:45} {auth:6} {tags:12} {endpoint.summary}")
    return 0 if not contract_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
