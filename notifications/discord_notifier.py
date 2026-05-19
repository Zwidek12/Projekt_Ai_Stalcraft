from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence, TypedDict

import requests
from requests import Response
from requests.exceptions import RequestException, Timeout

from notifications.message_builder import DiscordEmbed


logger = logging.getLogger(__name__)

_DOTENV_BOOTSTRAPPED = False
DISCORD_MAX_EMBEDS_PER_MESSAGE = 10


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
        _bootstrap_dotenv()
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook_url:
            raise ValueError(
                "DISCORD_WEBHOOK_URL is required. Set it in the environment or in a .env file "
                "in the project root (example: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...)."
            )
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
        embed_list = list(embeds)
        if not embed_list:
            logger.error("Discord webhook skipped (%s): empty embed list meta_keys=%s", event, sorted(meta.keys()))
            return DiscordWebhookResponse(status="failed", http_status=None, attempts=0, error="empty embed list")

        chunks = _chunk_embeds(embed_list, max_size=DISCORD_MAX_EMBEDS_PER_MESSAGE)
        if len(chunks) > 1:
            logger.info(
                "Discord webhook batching (%s): embeds=%s batches=%s",
                event,
                len(embed_list),
                len(chunks),
            )

        last_response: DiscordWebhookResponse | None = None
        for batch_idx, chunk in enumerate(chunks):
            payload: DiscordWebhookPayload = {
                "content": None,
                "embeds": chunk,
                "allowed_mentions": {"parse": []},
            }
            batch_meta = dict(meta)
            batch_meta["discord_batch_index"] = batch_idx
            batch_meta["discord_batch_count"] = len(chunks)
            batch_meta["discord_embed_count"] = len(chunk)
            response = self._post_json(event=event, meta=batch_meta, payload=payload)
            last_response = response
            if response.status != "ok":
                return response
        assert last_response is not None
        return last_response

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
                resp = self._do_request(payload)
                last_http_status = resp.status_code

                if 200 <= resp.status_code < 300:
                    logger.info(
                        "Discord webhook sent (%s): http=%s attempts=%s",
                        event,
                        resp.status_code,
                        attempts,
                    )
                    return DiscordWebhookResponse(
                        status="ok",
                        http_status=resp.status_code,
                        attempts=attempts,
                        error=None,
                    )

                body = _safe_response_text(resp)
                truncated = _truncate(body, 500)
                last_error = f"HTTP {resp.status_code}: {truncated}"
                embed_count = len(payload.get("embeds") or [])
                log_fn = logger.warning
                if resp.status_code == 400:
                    log_fn = logger.error
                log_fn(
                    "Discord webhook non-2xx (%s): http=%s attempts=%s embeds=%s body=%s meta_keys=%s",
                    event,
                    resp.status_code,
                    attempts,
                    embed_count,
                    truncated,
                    sorted(meta.keys()),
                )
                if resp.status_code == 400 and "invalid form body" in body.lower():
                    logger.error(
                        "Discord Invalid Form Body (%s): embeds=%s payload_bytes=%s meta_keys=%s",
                        event,
                        embed_count,
                        len(json.dumps(payload, ensure_ascii=False)),
                        sorted(meta.keys()),
                    )

                if not _is_retryable_status(resp.status_code):
                    break

            except Timeout as e:
                last_error = f"Timeout: {e}"
                logger.warning(
                    "Discord webhook transport error (%s): attempts=%s err=%s meta_keys=%s",
                    event,
                    attempts,
                    last_error,
                    sorted(meta.keys()),
                )
            except RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Discord webhook request error (%s): attempts=%s err=%s meta_keys=%s",
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

    def _do_request(self, payload: DiscordWebhookPayload) -> Response:
        data = json.dumps(payload, ensure_ascii=False)
        return requests.post(
            self._config.webhook_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "stalcraft-market-analyzer/discord-notifier",
            },
            timeout=self._config.timeout_s,
        )

    def _compute_backoff(self, attempt_idx: int) -> float:
        # 0 -> base, 1 -> 2x, 2 -> 4x, ...
        return self._config.retry_backoff_s * (2**attempt_idx)


def _is_retryable_status(http_status: int) -> bool:
    # Retry on rate limit and transient server errors.
    return http_status in (429, 500, 502, 503, 504)


def _safe_response_text(resp: Response) -> str:
    try:
        return resp.text
    except Exception:
        return ""


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _chunk_embeds(embeds: list[DiscordEmbed], *, max_size: int) -> list[list[DiscordEmbed]]:
    size = max(1, int(max_size))
    return [embeds[idx : idx + size] for idx in range(0, len(embeds), size)]


def _bootstrap_dotenv() -> None:
    """
    Ensure local `.env` is loaded exactly once per process.

    Parsing `.env` on every notifier init makes CLI workflows feel like they "hang"
    during first network import + env bootstrap.
    """
    global _DOTENV_BOOTSTRAPPED
    if _DOTENV_BOOTSTRAPPED:
        return

    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / ".env",
        Path(".env"),
    ]

    loaded_any = False
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                load_dotenv(dotenv_path=candidate, override=False)
                loaded_any = True
    except Exception:
        loaded_any = False

    # Fallback path if python-dotenv isn't installed: minimal parser.
    if not loaded_any:
        for candidate in candidates:
            _load_dotenv_if_present(candidate)

    _DOTENV_BOOTSTRAPPED = True


def _load_dotenv_if_present(path: Path | None = None) -> None:
    """
    Minimal .env loader (no external deps).

    - Does not override already-set environment variables.
    - Supports lines like KEY=VALUE (VALUE may be quoted with single/double quotes).
    - Ignores empty lines and comments starting with '#'.
    """
    dotenv_path = path or Path(".env")
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    try:
        content = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        if "=" not in line:
            i += 1
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key in os.environ and os.environ.get(key, "").strip():
            continue

        if len(value) >= 2 and (
            (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
        ):
            value = value[1:-1]

        # If a line got split (e.g. "KEY=\rVALUE"), allow a single-line continuation.
        if not value and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and "=" not in nxt and (nxt.startswith("http://") or nxt.startswith("https://")):
                value = nxt
                i += 1

        os.environ[key] = value
        i += 1

