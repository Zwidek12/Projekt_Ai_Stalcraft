from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_patch_impact_embed
from stalcraft_market_analyzer.analysis.patch_impact import analyze_patch_notes
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

logger = logging.getLogger(__name__)


def run_patch_impact_job(
    *,
    repo: SqlAlchemyRepository,
    patch_version: str,
    patch_text: str,
    send_discord: bool = False,
) -> dict[str, Any]:
    analyzed_at = datetime.now(timezone.utc)
    result = analyze_patch_notes(patch_version=patch_version, patch_text=patch_text)

    saved = repo.save_patch_analysis(patch_version=patch_version, analyzed_at=analyzed_at, result=result)

    discord_sent = 0
    discord_failed = 0

    min_conf = float(os.environ.get("PATCH_DISCORD_MIN_CONFIDENCE", "0.55"))
    impacts = {"BUFF", "NERF"}
    should_broadcast = saved and (
        str(result.get("impact", "")).upper() in impacts and float(result.get("confidence") or 0.0) >= min_conf
    )

    notifier: DiscordNotifier | None = None
    if send_discord:
        try:
            notifier = DiscordNotifier.from_env()
        except ValueError as error:
            logger.error("Discord not configured: %s", error)
            notifier = None

    if notifier is not None:
        embed_payload = {
            "severity": result.get("severity", "medium"),
            "impact": result.get("impact", "NEUTRAL"),
            "patch_version": patch_version,
            "observed_at": analyzed_at.isoformat(),
            "source": str(result.get("source", "patch_impact")),
            "confidence": result.get("confidence", 0.0),
            "buffed_items": list(result.get("buffed_items") or []),
            "nerfed_items": list(result.get("nerfed_items") or []),
        }
        embed = build_patch_impact_embed(embed_payload)

        if should_broadcast:
            resp = notifier.send_patch_alert({"patch_version": patch_version}, embeds=[embed])
            discord_sent += 1 if resp.status == "ok" else 0
            discord_failed += 0 if resp.status == "ok" else 1
        else:
            logger.info(
                "Skipping patch Discord broadcast (gates): saved=%s impact=%s conf=%s min_conf=%s",
                saved,
                result.get("impact"),
                result.get("confidence"),
                min_conf,
            )

    return {
        "patch_version": patch_version,
        "analysis_saved": saved,
        "result": result,
        "discord_sent": discord_sent,
        "discord_failed": discord_failed,
        "broadcast": should_broadcast and send_discord,
    }
