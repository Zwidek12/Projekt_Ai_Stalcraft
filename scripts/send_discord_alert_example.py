"""
Przykład ręcznej wysyłki alertów na Discord — ten sam kierunek co MVP repo:

webhook + embedy, builder wiadomości (`notifications/message_builder.py`),
warstwa wysyłki (`notifications/discord_notifier.py`), oraz spójność operacyjna
z healthcheckiem (`api/health.py`), runbookiem (`Runbook.md`) i testem E2E
(`tests/test_e2e_pipeline.py`).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.health import build_health_response
from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_patch_impact_embed, build_price_opportunity_embed


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    notifier = DiscordNotifier.from_env()

    # Example 1: price opportunity
    alert = {
        "severity": "high",
        "item_name": "Worn Seeker Backpack",
        "price": 12400,
        "deviation_pct": -18.4,
        "observed_at": "2026-04-28T18:20:00Z",
        "source": "scraper:example",
        "notes": "Example alert (manual run)",
    }
    price_embed = build_price_opportunity_embed(alert)
    resp1 = notifier.send_price_alert(alert, embeds=[price_embed])
    logging.info("Price alert send result: %s", resp1)

    # Example 2: patch impact
    patch = {
        "severity": "medium",
        "impact": "NERF",
        "patch_version": "1.9.14",
        "confidence": 0.82,
        "observed_at": "2026-04-28T18:50:00Z",
        "source": "patch_notes:official",
        "buffed_items": [],
        "nerfed_items": ["VSS Vintorez", "RPD", "Polycarbonate Plate"],
    }
    patch_embed = build_patch_impact_embed(patch)
    resp2 = notifier.send_patch_alert(patch, embeds=[patch_embed])
    logging.info("Patch alert send result: %s", resp2)

    health = build_health_response()
    logging.info(
        "Health snapshot (por. Runbook /health): %s",
        json.dumps(health, ensure_ascii=False),
    )

    return 0 if resp1.status == "ok" and resp2.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
