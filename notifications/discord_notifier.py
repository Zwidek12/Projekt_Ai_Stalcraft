from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from notifications.message_builder import DiscordEmbed


logger = logging.getLogger(__name__)


DiscordWebhookStatus = Literal["ok", "failed"]


class AllowedMentions(TypedDict, total=False):
    parse: list[str]


class DiscordWebhookPayload(TypedDict, total=False):
    content: str | None
    embeds: list[DiscordEmbed]
    allowed_mentions: AllowedMentions


@dataclass(frozen=True, slots=True)
class DiscordWebhookResponse:
    status: DiscordWebhookStatus
    http_status: int | None
    attempts: int
    error: str | None


@dataclass(frozen=True, slots=True)
class DiscordNotifierConfig:
    webhook_url: str
    timeout_s: float = 10.0
    max_retries: int = 3
    retry_backoff_s: float = 0.8


class DiscordNotifier:
    """
    Discord webhook sender (POST JSON).

    Responsibilities:
    - Send already-built embed dicts (no formatting/business logic).
    - Handle timeout + retries.
    - Emit readable logs with HTTP status and truncated response.
    """

    def __init__(self, config: DiscordNotifierConfig) -> None:
        if not config.webhook_url.strip():
            raise ValueError("DiscordNotifierConfig.webhook_url is required.")
        self._config = config

    @classmethod
    def from_env(cls) -> "DiscordNotifier":
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        timeout_s = float(os.environ.get("DISCORD_WEBHOOK_TIMEOUT_S", "10"))
        max_retries = int(os.environ.get("DISCORD_WEBHOOK_MAX_RETRIES", "3"))
        retry_backoff_s = float(os.environ.get("DISCORD_WEBHOOK_RETRY_BACKOFF_S", "0.8"))
        return cls(
            DiscordNotifierConfig(
                webhook_url=webhook_url,
                timeout_s=timeout_s,
                max_retries=max_retries,
                retry_backoff_s=retry_backoff_s,
            )
        )

    def send_price_alert(self, alert: Mapping[str, object], *, embeds: Sequence[DiscordEmbed]) -> DiscordWebhookResponse:
        return self._send(
            event="price_alert",
            meta=alert,
            embeds=embeds,
        )

    def send_patch_alert(self, result: Mapping[str, object], *, embeds: Sequence[DiscordEmbed]) -> DiscordWebhookResponse:
        return self._send(
            event="patch_alert",
            meta=result,
            embeds=embeds,
        )

    def _send(
        self,
        *,
        event: str,
        meta: Mapping[str, object],
        embeds: Sequence[DiscordEmbed],
    ) -> DiscordWebhookResponse:
        payload: DiscordWebhookPayload = {
            "content": None,
            "embeds": list(embeds),
            "allowed_mentions": {"parse": []},
        }
        return self._post_json(event=event, meta=meta, payload=payload)

    def _post_json(
        self,
        *,
        event: str,
        meta: Mapping[str, object],
        payload: DiscordWebhookPayload,
    ) -> DiscordWebhookResponse:
        attempts = 0
        last_error: str | None = None
        last_http_status: int | None = None

        for attempt_idx in range(self._config.max_retries + 1):
            attempts = attempt_idx + 1
            try:
                http_status, body = self._do_request(payload)
                last_http_status = http_status

                if 200 <= http_status < 300:
                    logger.info(
                        "Discord webhook sent (%s): http=%s attempts=%s",
                        event,
                        http_status,
                        attempts,
                    )
                    return DiscordWebhookResponse(
                        status="ok",
                        http_status=http_status,
                        attempts=attempts,
                        error=None,
                    )

                truncated = _truncate(body, 500)
                last_error = f"HTTP {http_status}: {truncated}"
                logger.warning(
                    "Discord webhook non-2xx (%s): http=%s attempts=%s body=%s meta_keys=%s",
                    event,
                    http_status,
                    attempts,
                    truncated,
                    sorted(meta.keys()),
                )

                if not _is_retryable_status(http_status):
                    break

            except HTTPError as e:
                last_http_status = int(getattr(e, "code", 0)) or None
                body = _read_http_error_body(e)
                truncated = _truncate(body, 500)
                last_error = f"HTTPError {last_http_status}: {truncated}"
                logger.warning(
                    "Discord webhook HTTPError (%s): http=%s attempts=%s body=%s meta_keys=%s",
                    event,
                    last_http_status,
                    attempts,
                    truncated,
                    sorted(meta.keys()),
                )
                if last_http_status is not None and not _is_retryable_status(last_http_status):
                    break

            except (URLError, TimeoutError) as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Discord webhook transport error (%s): attempts=%s err=%s meta_keys=%s",
                    event,
                    attempts,
                    last_error,
                    sorted(meta.keys()),
                )

            if attempt_idx < self._config.max_retries:
                time.sleep(self._compute_backoff(attempt_idx))

        logger.error(
            "Discord webhook failed (%s): http=%s attempts=%s err=%s meta_keys=%s",
            event,
            last_http_status,
            attempts,
            last_error,
            sorted(meta.keys()),
        )
        return DiscordWebhookResponse(
            status="failed",
            http_status=last_http_status,
            attempts=attempts,
            error=last_error,
        )

    def _do_request(self, payload: DiscordWebhookPayload) -> tuple[int, str]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self._config.webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "stalcraft-market-analyzer/discord-notifier",
            },
            method="POST",
        )
        with urlopen(req, timeout=self._config.timeout_s) as resp:
            status = int(getattr(resp, "status", 0))
            body_bytes = resp.read()
            body = body_bytes.decode("utf-8", errors="replace")
            return status, body

    def _compute_backoff(self, attempt_idx: int) -> float:
        # 0 -> base, 1 -> 2x, 2 -> 4x, ...
        return self._config.retry_backoff_s * (2**attempt_idx)


def _is_retryable_status(http_status: int) -> bool:
    # Retry on rate limit and transient server errors.
    return http_status in (429, 500, 502, 503, 504)


def _read_http_error_body(err: HTTPError) -> str:
    try:
        raw = err.read()
    except Exception:
        return ""
    if not raw:
        return ""
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"

