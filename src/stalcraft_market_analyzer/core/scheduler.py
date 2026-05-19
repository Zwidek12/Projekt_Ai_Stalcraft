from __future__ import annotations

import logging
import signal
import time

import schedule

logger = logging.getLogger(__name__)


def run_forever(*, stop_on_sigint: bool = True) -> None:
    """
    Minimal blocking scheduler loop for jobs registered on the global `schedule` object.
    """
    if stop_on_sigint:

        def _handler(signum: int, frame: object) -> None:  # pragma: no cover
            _ = (signum, frame)
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, _handler)

    logger.info("Scheduler started (Ctrl+C to stop).")

    while True:
        schedule.run_pending()
        time.sleep(1)
