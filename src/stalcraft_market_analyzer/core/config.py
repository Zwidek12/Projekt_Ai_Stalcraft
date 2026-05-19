from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalcraft_market_analyzer.storage.db import prepare_sqlite_database_url


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    database_url: str
    discord_webhook_url: str | None
    raw_output_dir: Path
    exbo_api_base_url: str
    exbo_region: str
    exbo_access_token: str
    exbo_client_id: str
    exbo_client_secret: str
    exbo_item_db_enabled: bool
    exbo_item_db_realm: str
    exbo_item_db_cache_file: Path


def load_config(*, project_root: Path) -> AppConfig:
    """
    Minimal config loader.

    - Environment variables are used by downstream modules (DiscordNotifier reads DISCORD_WEBHOOK_URL).
    - This function centralizes the core paths/URLs and provides sane defaults for dev.
    """
    _maybe_load_dotenv(project_root=project_root)

    # NOTE: We intentionally keep this minimal and avoid hard dependencies.
    base_url = _get_env("STALCRAFTDB_BASE_URL", default="https://stalcraftdb.example.com").strip()
    database_url = prepare_sqlite_database_url(
        _get_env("DATABASE_URL", default=f"sqlite:///{(project_root / 'data' / 'market.db').as_posix()}").strip(),
        project_root=project_root,
    )
    webhook_url = _get_env("DISCORD_WEBHOOK_URL", default="").strip() or None
    raw_output_dir = _resolve_project_path(
        _get_env("RAW_OUTPUT_DIR", default=str(project_root / "data" / "raw")),
        project_root=project_root,
    )
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    exbo_api_base_url = _get_env("EXBO_API_BASE_URL", default="https://eapi.stalcraft.net").strip()
    exbo_region = _get_env("EXBO_REGION", default="EU").strip().upper()
    exbo_access_token = _get_env("EXBO_ACCESS_TOKEN", default="").strip()
    exbo_client_id = _get_env("EXBO_CLIENT_ID", default="").strip()
    exbo_client_secret = _get_env("EXBO_CLIENT_SECRET", default="").strip()
    exbo_item_db_enabled = _get_env("EXBO_ITEM_DB_ENABLED", default="true").strip().lower() not in {"0", "false", "no"}
    exbo_item_db_realm = _get_env("EXBO_ITEM_DB_REALM", default="global").strip().lower()
    exbo_item_db_cache_file = _resolve_project_path(
        _get_env("EXBO_ITEM_DB_CACHE_FILE", default=str(project_root / "data" / "exbo_artifact_rarities.json")),
        project_root=project_root,
    )

    if not base_url:
        raise ValueError("STALCRAFTDB_BASE_URL is required.")
    if not database_url:
        raise ValueError("DATABASE_URL is required.")

    return AppConfig(
        base_url=base_url,
        database_url=database_url,
        discord_webhook_url=webhook_url,
        raw_output_dir=raw_output_dir,
        exbo_api_base_url=exbo_api_base_url,
        exbo_region=exbo_region,
        exbo_access_token=exbo_access_token,
        exbo_client_id=exbo_client_id,
        exbo_client_secret=exbo_client_secret,
        exbo_item_db_enabled=exbo_item_db_enabled,
        exbo_item_db_realm=exbo_item_db_realm,
        exbo_item_db_cache_file=exbo_item_db_cache_file,
    )


def _get_env(key: str, *, default: str) -> str:
    import os

    return os.environ.get(key, default)


def _resolve_project_path(value: str, *, project_root: Path) -> Path:
    path = Path(value.strip())
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


def _maybe_load_dotenv(*, project_root: Path) -> None:
    """
    Load local .env (if present) into process env.

    We keep this optional to avoid breaking environments that don't install python-dotenv.
    """
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
    except Exception:
        return

