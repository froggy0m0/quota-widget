"""Read Claude Code's five-hour subscription usage without a model request."""

from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
POLL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 65536


def get_five_hour_usage(response: Any) -> float:
    window = response.get("five_hour") if isinstance(response, dict) else None
    used = window.get("utilization") if isinstance(window, dict) else None
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        raise ValueError("Claude의 5시간 구독 사용률을 확인할 수 없습니다.")
    value = float(used)
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Claude에서 잘못된 사용률을 받았습니다.")
    return value


def credentials_path() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(configured).expanduser() if configured else Path.home() / ".claude"
    return base / ".credentials.json"


def read_access_token(path: Path) -> str:
    try:
        with path.open(encoding="utf-8-sig") as stream:
            text = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(text) > MAX_RESPONSE_BYTES:
            raise ValueError()
        document = json.loads(text)
    except FileNotFoundError:
        raise RuntimeError("Claude Code를 설치하고 구독 계정으로 로그인해 주세요.") from None
    except (OSError, ValueError):
        raise RuntimeError("Claude Code 로그인 정보를 읽을 수 없습니다. 다시 로그인해 주세요.") from None
    oauth = document.get("claudeAiOauth") if isinstance(document, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    if not isinstance(token, str) or not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise RuntimeError("Claude Code의 구독 로그인이 필요합니다.")
    expiry = oauth.get("expiresAt")
    if isinstance(expiry, (int, float)) and expiry < time.time() * 1000:
        raise RuntimeError("Claude Code 로그인 시간이 만료됐습니다. Claude Code를 실행해 갱신해 주세요.")
    return token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RateLimited(RuntimeError):
    def __init__(self, seconds: int) -> None:
        super().__init__("Claude 한도 조회가 잠시 제한됐습니다. 잠시 후 다시 확인합니다.")
        self.retry_seconds = max(POLL_SECONDS, min(seconds, 600))


def request_usage(access_token: str) -> float:
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {access_token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
    }, method="GET")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            try:
                seconds = int(exc.headers.get("Retry-After", "300"))
            except (TypeError, ValueError):
                seconds = 300
            raise RateLimited(seconds) from None
        if exc.code in (401, 403):
            raise RuntimeError("Claude 한도 조회에 로그인 권한이 필요합니다. Claude Code 로그인을 확인해 주세요.") from None
        raise RuntimeError(f"Claude 한도 조회 실패 (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Claude 한도 조회에 연결하지 못했습니다. 잠시 후 다시 확인합니다.") from None
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Claude에서 잘못된 한도 응답을 받았습니다.")
    try:
        document = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError("Claude에서 잘못된 한도 응답을 받았습니다.") from None
    return get_five_hour_usage(document)


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
            delay = POLL_SECONDS
            try:
                usage = request_usage(read_access_token(credentials_path()))
                event = ("usage", usage)
            except Exception as exc:
                event = ("error", str(exc) or "Claude 한도 조회에 실패했습니다.")
                if isinstance(exc, RateLimited):
                    delay = exc.retry_seconds
            if self._stop.is_set():
                break
            self.events.put(event)
            if self._stop.wait(delay):
                break
