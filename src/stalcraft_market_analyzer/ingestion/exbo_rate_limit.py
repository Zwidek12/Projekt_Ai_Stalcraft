from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from requests import Response

logger = logging.getLogger(__name__)


def retry_after_seconds(response: Response, *, fallback_s: float) -> float:
    header = (response.headers.get("Retry-After") or "").strip()
    if not header:
        return max(0.0, float(fallback_s))

    try:
        return max(0.0, float(header))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(header)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError, OSError):
        return max(0.0, float(fallback_s))


def throttle_before_request(*, last_request_monotonic: float | None, min_interval_s: float) -> float:
    """
    Sleep if needed to respect a minimum interval between EXBO calls.

    Returns the monotonic timestamp recorded after any sleep (for the next call).
    """
    now = time.monotonic()
    if last_request_monotonic is None or min_interval_s <= 0:
        return now

    elapsed = now - last_request_monotonic
    wait_s = min_interval_s - elapsed
    if wait_s > 0:
        time.sleep(wait_s)
        return time.monotonic()
    return now
