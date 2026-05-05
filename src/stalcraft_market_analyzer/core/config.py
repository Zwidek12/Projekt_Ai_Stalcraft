from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    database_url: str
    discord_webhook_url: str | None
    raw_output_dir: Path


def load_config(*, project_root: Path) -> AppConfig:
    """
    Minimal config loader.

    - Environment variables are used by downstream modules (DiscordNotifier reads DISCORD_WEBHOOK_URL).
    - This function centralizes the core paths/URLs and provides sane defaults for dev.
    """
    _maybe_load_dotenv(project_root=project_root)

    # NOTE: We intentionally keep this minimal and avoid hard dependencies.
    base_url = _get_env("STALCRAFTDB_BASE_URL", default="https://stalcraftdb.example.com").strip()
    database_url = _get_env("DATABASE_URL", default=f"sqlite:///{(project_root / 'data' / 'market.db').as_posix()}").strip()
    webhook_url = _get_env("DISCORD_WEBHOOK_URL", default="").strip() or None
    raw_output_dir = Path(_get_env("RAW_OUTPUT_DIR", default=str(project_root / "data" / "raw"))).resolve()

    if not base_url:
        raise ValueError("STALCRAFTDB_BASE_URL is required.")
    if not database_url:
        raise ValueError("DATABASE_URL is required.")

    return AppConfig(
        base_url=base_url,
        database_url=database_url,
        discord_webhook_url=webhook_url,
        raw_output_dir=raw_output_dir,
    )


def _get_env(key: str, *, default: str) -> str:
    import os

    return os.environ.get(key, default)


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

