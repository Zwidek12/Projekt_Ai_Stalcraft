from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from notifications.discord_notifier import DiscordNotifier
from notifications.message_builder import build_price_opportunity_embed
from stalcraft_market_analyzer.analysis.analyzer import (
    AnomalyScanConfig,
    PriceAnomalySignal,
    build_price_anomaly_fingerprint,
    scan_price_anomalies,
)
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository

logger = logging.getLogger(__name__)


def run_price_anomaly_scan_job(
    *,
    repo: SqlAlchemyRepository,
    now: datetime | None = None,
    recent_hours: int = 48,
    item_ids: list[str] | None = None,
    send_discord: bool = False,
    force_discord_notify: bool = False,
    anomaly_config: AnomalyScanConfig | None = None,
) -> dict[str, object]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    targets = (
        item_ids[:] if item_ids else repo.get_distinct_item_ids(since=now_utc - timedelta(hours=max(1, recent_hours)))
    )
    cfg = anomaly_config or AnomalyScanConfig()

    signals = scan_price_anomalies(repo=repo, item_ids=targets, now=now_utc, config=cfg)
    logger.info(
        "Price anomaly scan: scanned_items=%s signals_found=%s send_discord=%s force_discord_notify=%s",
        len(targets),
        len(signals),
        bool(send_discord),
        bool(force_discord_notify),
    )

    notifier: DiscordNotifier | None = None
    if send_discord:
        try:
            logger.info("Initializing Discord notifier from environment...")
            notifier = DiscordNotifier.from_env()
            logger.info("Discord notifier ready.")
        except ValueError as error:
            logger.error("Discord not configured: %s", error)
            notifier = None

    inserted = 0
    deduped = 0
    skipped_cooldown = 0
    discord_sent = 0
    discord_failed = 0

    for idx, signal in enumerate(signals, start=1):
        logger.info(
            "Processing signal %s/%s: kind=%s item_id=%s deviation_pct=%.2f",
            idx,
            len(signals),
            signal.kind,
            signal.item_id,
            float(signal.deviation_pct),
        )
        inserted_flag, deduped_flag, cooldown_flag, sent_flag, failed_flag = _persist_and_maybe_notify(
            repo=repo,
            notifier=notifier,
            signal=signal,
            now=now_utc,
            force_discord_notify=bool(force_discord_notify),
        )
        inserted += inserted_flag
        deduped += deduped_flag
        skipped_cooldown += cooldown_flag
        discord_sent += sent_flag
        discord_failed += failed_flag

    logger.info(
        "Price anomaly scan done: alerts_inserted=%s alerts_deduped=%s cooldown_skipped=%s discord_sent=%s discord_failed=%s",
        inserted,
        deduped,
        skipped_cooldown,
        discord_sent,
        discord_failed,
    )

    return {
        "scanned_items": len(targets),
        "signals_found": len(signals),
        "alerts_inserted": inserted,
        "alerts_deduped": deduped,
        "cooldown_skipped": skipped_cooldown,
        "discord_sent": discord_sent,
        "discord_failed": discord_failed,
        "signals": [asdict(s) for s in signals],
    }


def _persist_and_maybe_notify(
    *,
    repo: SqlAlchemyRepository,
    notifier: DiscordNotifier | None,
    signal: PriceAnomalySignal,
    now: datetime,
    force_discord_notify: bool,
) -> tuple[int, int, int, int, int]:
    fingerprint = build_price_anomaly_fingerprint(signal=signal, now=now)
    payload: dict[str, object] = {"signal": asdict(signal), "detected_kind": signal.kind}

    cooldown_minutes_raw = os.environ.get("PRICE_ALERT_COOLDOWN_MINUTES", "60").strip()
    try:
        cooldown_minutes = int(cooldown_minutes_raw)
    except ValueError:
        cooldown_minutes = 60

    if cooldown_minutes > 0 and not force_discord_notify:
        since = now - timedelta(minutes=cooldown_minutes)
        if repo.has_recent_price_anomaly(item_id=signal.item_id, since=since):
            logger.info(
                "Skipping anomaly notify (cooldown): item_id=%s window_minutes=%s",
                signal.item_id,
                cooldown_minutes,
            )
            return 0, 0, 1, 0, 0

    try:
        saved = repo.save_alert(
            alert_type="price_anomaly",
            fingerprint=fingerprint,
            payload=payload,
            item_id=signal.item_id,
        )
    except Exception as error:
        logger.error("Failed to persist anomaly alert row: %s", error)
        raise
    if not saved:
        logger.info("Deduped anomaly alert (already exists): fingerprint=%s", fingerprint)
        if not (force_discord_notify and notifier is not None):
            return 0, 1, 0, 0, 0
        embed = build_price_opportunity_embed(
            {
                "severity": signal.severity,
                "item_name": signal.item_name,
                "price": signal.latest_price,
                "deviation_pct": signal.deviation_pct,
                "observed_at": signal.observed_at.isoformat(),
                "source": signal.source,
                "notes": "FORCE NOTIFY (deduped fingerprint) — baseline median (7d excl. latest): "
                + f"{signal.baseline_median:,.0f}".replace(",", " "),
            }
        )

        logger.info("Sending Discord price alert (force notify despite dedupe)...")
        resp = notifier.send_price_alert(
            {"item_id": signal.item_id, "kind": signal.kind, "fingerprint": fingerprint, "forced": True},
            embeds=[embed],
        )
        logger.info(
            "Discord send result: status=%s http=%s attempts=%s err=%s",
            resp.status,
            resp.http_status,
            resp.attempts,
            resp.error,
        )
        deduped = 1
        if resp.status == "ok":
            return 0, deduped, 0, 1, 0
        return 0, deduped, 0, 0, 1

    logger.info("Inserted anomaly alert row: fingerprint=%s", fingerprint)

    if notifier is None:
        logger.info("Skipping Discord notify (no notifier configured).")
        return 1, 0, 0, 0, 0

    embed = build_price_opportunity_embed(
        {
            "severity": signal.severity,
            "item_name": signal.item_name,
            "price": signal.latest_price,
            "deviation_pct": signal.deviation_pct,
            "observed_at": signal.observed_at.isoformat(),
            "source": signal.source,
            "notes": "Baseline median (7d excl. latest): "
            + f"{signal.baseline_median:,.0f}".replace(",", " "),
        }
    )

    logger.info("Sending Discord price alert...")
    resp = notifier.send_price_alert(
        {"item_id": signal.item_id, "kind": signal.kind, "fingerprint": fingerprint},
        embeds=[embed],
    )
    logger.info(
        "Discord send result: status=%s http=%s attempts=%s err=%s",
        resp.status,
        resp.http_status,
        resp.attempts,
        resp.error,
    )
    if resp.status == "ok":
        return 1, 0, 0, 1, 0
    return 1, 0, 0, 0, 1
