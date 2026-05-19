from __future__ import annotations

from stalcraft_market_analyzer.ingestion.exbo_openapi import (
    filter_exbo_endpoints,
    list_exbo_endpoints,
    validate_exbo_auction_contract,
)


def _spec() -> dict[str, object]:
    return {
        "paths": {
            "/regions": {
                "get": {
                    "summary": "List of Regions",
                    "tags": [],
                    "security": [],
                }
            },
            "/{region}/auction/{item}/history": {
                "get": {
                    "summary": "Item Price History",
                    "tags": ["Auction"],
                    "security": [{"AppAuth": []}],
                }
            },
            "/{region}/auction/{item}/lots": {
                "get": {
                    "summary": "Active Item Lots",
                    "tags": ["Auction"],
                    "security": [{"AppAuth": []}],
                }
            },
        }
    }


def test_list_exbo_endpoints_marks_public_and_auth() -> None:
    endpoints = list_exbo_endpoints(_spec())

    public = filter_exbo_endpoints(endpoints, auth="public")
    auction = filter_exbo_endpoints(endpoints, tag="Auction", auth="auth")

    assert [endpoint.path for endpoint in public] == ["/regions"]
    assert {endpoint.path for endpoint in auction} == {
        "/{region}/auction/{item}/history",
        "/{region}/auction/{item}/lots",
    }


def test_validate_exbo_auction_contract_accepts_current_paths() -> None:
    assert validate_exbo_auction_contract(_spec()) == []
