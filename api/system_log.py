from __future__ import annotations

import logging
import threading
from collections import deque

_MAX_LINES = 500
_buffer: deque[str] = deque(maxlen=_MAX_LINES)
_lock = threading.Lock()
_installed = False


class SystemLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        with _lock:
            _buffer.append(message)


def install_system_log_handler() -> None:
    global _installed
    if _installed:
        return
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, SystemLogHandler):
            _installed = True
            return
    handler = SystemLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    if root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    _installed = True


def tail_system_logs(*, limit: int = 200) -> list[str]:
    lim = max(1, min(int(limit), _MAX_LINES))
    with _lock:
        return list(_buffer)[-lim:]


def clear_system_logs() -> None:
    with _lock:
        _buffer.clear()
