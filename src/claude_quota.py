"""Read Claude's five-hour usage from the local JSON file."""

from __future__ import annotations

import json
import math
import queue
import threading
import time
from pathlib import Path
from typing import Any

POLL_SECONDS = 60


def usage_path() -> Path:
    return Path.home() / ".claude" / "usage-widget" / "usage.json"


def get_five_hour_usage(document: Any, *, now: float | None = None) -> float:
    if not isinstance(document, dict):
        raise ValueError("Claude 사용률 파일의 형식이 올바르지 않습니다.")
    used = document.get("used_percentage")
    resets_at = document.get("resets_at")
    for value in (used, resets_at):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Claude 사용률 파일의 형식이 올바르지 않습니다.")
    if not 0 <= used <= 100:
        raise ValueError("Claude 사용률 파일의 형식이 올바르지 않습니다.")
    if resets_at < (time.time() if now is None else now):
        return 0.0
    return float(round(used))


def read_usage() -> float:
    try:
        document = json.loads(usage_path().read_text(encoding="utf-8"))
        return get_five_hour_usage(document)
    except (OSError, UnicodeError, ValueError):
        raise RuntimeError("Claude 연결 안됨") from None


class ClaudeQuotaClient:
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        self.events = events
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="claude-quota-client", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event = ("usage", read_usage())
            except RuntimeError as exc:
                event = ("error", str(exc))
            if self._stop.is_set():
                break
            self.events.put(event)
            if self._stop.wait(POLL_SECONDS):
                break
