from __future__ import annotations

import argparse
import inspect
import logging
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stalcraft developer dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_kw: dict[str, object] = {
        "app": "api.dev_ui:app",
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
    }
    if args.reload and "reload_excludes" in inspect.signature(uvicorn.run).parameters:
        # Avoid reload loops when ingestion writes snapshots into data/raw.
        run_kw["reload_excludes"] = [
            "data/*",
            "data/**",
            "*.db",
            "**/__pycache__/**",
            "**/*.pyc",
        ]
    elif args.reload:
        logging.getLogger(__name__).warning(
            "This uvicorn has no reload_excludes; file writes under data/ may trigger extra reloads. "
            "Upgrade uvicorn or use --reload only when debugging templates."
        )
    uvicorn.run(**run_kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
