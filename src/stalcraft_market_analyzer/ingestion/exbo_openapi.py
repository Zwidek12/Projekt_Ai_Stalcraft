from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class ExboOpenApiEndpoint:
    method: str
    path: str
    summary: str
    tags: tuple[str, ...]
    requires_auth: bool


def fetch_exbo_openapi(*, api_base_url: str, timeout_seconds: int = 20) -> dict[str, Any]:
    response = requests.get(f"{api_base_url.rstrip('/')}/openapi", timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("EXBO OpenAPI response is not a JSON object.")
    return payload


def load_exbo_openapi(
    *,
    api_base_url: str,
    cache_path: Path | None = None,
    refresh: bool = False,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    if cache_path is not None and cache_path.is_file() and not refresh:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"Cached EXBO OpenAPI file is not a JSON object: {cache_path}")

    spec = fetch_exbo_openapi(api_base_url=api_base_url, timeout_seconds=timeout_seconds)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec


def list_exbo_endpoints(spec: dict[str, Any]) -> list[ExboOpenApiEndpoint]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    endpoints: list[ExboOpenApiEndpoint] = []
    for path, path_config in paths.items():
        if not isinstance(path, str) or not isinstance(path_config, dict):
            continue
        for method, operation in path_config.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            endpoints.append(_endpoint_from_operation(method=method, path=path, operation=operation))
    return sorted(endpoints, key=lambda endpoint: (endpoint.path, endpoint.method))


def filter_exbo_endpoints(
    endpoints: list[ExboOpenApiEndpoint],
    *,
    tag: str = "",
    auth: str = "all",
) -> list[ExboOpenApiEndpoint]:
    normalized_tag = tag.strip().lower()
    normalized_auth = auth.strip().lower()

    output: list[ExboOpenApiEndpoint] = []
    for endpoint in endpoints:
        if normalized_tag and normalized_tag not in {value.lower() for value in endpoint.tags}:
            continue
        if normalized_auth == "public" and endpoint.requires_auth:
            continue
        if normalized_auth == "auth" and not endpoint.requires_auth:
            continue
        output.append(endpoint)
    return output


def validate_exbo_auction_contract(spec: dict[str, Any]) -> list[str]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return ["OpenAPI spec has no paths object."]

    errors: list[str] = []
    required_paths = {
        "/{region}/auction/{item}/history": "Item Price History",
        "/{region}/auction/{item}/lots": "Active Item Lots",
    }
    for path, summary in required_paths.items():
        operation = paths.get(path, {}).get("get") if isinstance(paths.get(path), dict) else None
        if not isinstance(operation, dict):
            errors.append(f"Missing GET {path}.")
            continue
        if str(operation.get("summary") or "") != summary:
            errors.append(f"Unexpected summary for GET {path}: {operation.get('summary')!r}.")
        security = operation.get("security")
        if not security:
            errors.append(f"GET {path} does not declare AppAuth security.")
    return errors


def _endpoint_from_operation(*, method: str, path: str, operation: dict[str, Any]) -> ExboOpenApiEndpoint:
    security = operation.get("security")
    tags_raw = operation.get("tags")
    tags = tuple(str(tag) for tag in tags_raw if isinstance(tag, str)) if isinstance(tags_raw, list) else ()
    return ExboOpenApiEndpoint(
        method=method.upper(),
        path=path,
        summary=str(operation.get("summary") or ""),
        tags=tags,
        requires_auth=bool(security),
    )
