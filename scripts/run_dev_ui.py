from __future__ import annotations

import argparse
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
    reload_excludes: list[str] | None = None
    if args.reload:
        reload_excludes = [
            "data/*",
            "data/**",
            "*.db",
            "**/__pycache__/**",
            "**/*.pyc",
        ]
    uvicorn.run(
        "api.dev_ui:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # Avoid reload loops when ingestion writes snapshots into data/raw.
        reload_excludes=reload_excludes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
