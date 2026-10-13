"""Codex app-server quota transport and response parsing."""

from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ALLOWED_METHODS = frozenset({"initialize", "initialized", "account/rateLimits/read"})
POLL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 20


def get_five_hour_usage(result: Any) -> float:
    """Return the Codex 300-minute used percentage, rejecting bad responses."""
    if not isinstance(result, dict):
        raise ValueError("Invalid Codex quota response.")

    buckets = result.get("rateLimitsByLimitId")
    bucket = buckets.get("codex") if isinstance(buckets, dict) else None
    if bucket is None:
        bucket = result.get("rateLimits")
        if isinstance(bucket, dict) and bucket.get("limitId") not in (None, "codex"):
            raise ValueError("The response does not contain the Codex quota.")
    if not isinstance(bucket, dict):
        raise ValueError("No 300-minute Codex quota is available.")

    for name in ("primary", "secondary"):
        window = bucket.get(name)
        if not isinstance(window, dict) or window.get("windowDurationMins") != 300:
            continue
        used = window.get("usedPercent")
        if isinstance(used, bool) or not isinstance(used, (int, float)):
            raise ValueError("Invalid quota percentage.")
        value = float(used)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Invalid quota percentage.")
        return value
    raise ValueError("No 300-minute Codex quota is available.")


def find_codex(explicit_path: str | None = None) -> str:
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError("Codex executable not found.")
        return str(path.resolve())

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        installed = Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if installed.is_file():
            return str(installed)
    for name in ("codex.exe", "codex"):
        found = shutil.which(name)
        if found:
            return found
    raise FileNotFoundError("Install Codex and sign in with ChatGPT, or supply --codex-path.")


def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    method = message.get("method")
    if method not in ALLOWED_METHODS:
        raise ValueError("Unsupported RPC method.")
    if process.stdin is None:
        raise RuntimeError("Codex app-server input is unavailable.")
    process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    process.stdin.flush()


class QuotaClient:
    """Owns a Codex child process and publishes quota/error events to a queue."""

    def __init__(
        self,
        codex_path: str,
        events: queue.Queue[tuple[str, Any]],
        *,
        command_prefix: list[str] | None = None,
    ) -> None:
        self.codex_path = codex_path
        self.events = events
        self.command_prefix = command_prefix
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="quota-client", daemon=True)
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._stop_process()
        self._thread.join(timeout=2)

    def _stop_process(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self._process = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_session()
            except Exception as exc:
                self._stop_process()
                if self._stop.is_set():
                    break
                self.events.put(("error", str(exc) or "Codex quota connection failed."))
                if self._stop.wait(POLL_SECONDS):
                    break

    def _run_session(self) -> None:
        command = list(self.command_prefix or [self.codex_path])
        command += ["app-server", "--listen", "stdio://"]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        self._process = process
        lines: queue.Queue[str | None] = queue.Queue()

        def read_stdout() -> None:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        def drain_stderr() -> None:
            assert process.stderr is not None
            for _ in process.stderr:
                pass  # Drain without exposing process diagnostics or credentials.

        threading.Thread(target=read_stdout, name="quota-stdout", daemon=True).start()
        threading.Thread(target=drain_stderr, name="quota-stderr", daemon=True).start()

        request_id = 1
        _send(process, {"id": request_id, "method": "initialize", "params": {
            "clientInfo": {
                "name": "quota_widget",
                "title": "Quota Widget",
                "version": "0.1.0",
            }
        }})
        response = self._wait_response(process, lines, request_id)
        if "error" in response:
            raise RuntimeError("Codex rejected initialization.")
        _send(process, {"method": "initialized", "params": {}})

        while not self._stop.is_set():
            request_id += 1
            _send(process, {"id": request_id, "method": "account/rateLimits/read"})
            response = self._wait_response(process, lines, request_id)
            if "error" in response:
                raise RuntimeError("Codex rejected the quota request. Check your ChatGPT sign-in.")
            self.events.put(("usage", get_five_hour_usage(response.get("result"))))
            if self._stop.wait(POLL_SECONDS):
                return
        if process.poll() is not None:
            raise RuntimeError("Codex app-server exited.")

    def _wait_response(
        self,
        process: subprocess.Popen[str],
        lines: queue.Queue[str | None],
        request_id: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Quota request timed out.")
            try:
                line = lines.get(timeout=min(0.2, remaining))
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("Codex app-server exited.")
                continue
            if line is None:
                raise RuntimeError("Codex closed its output stream.")
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Codex sent an invalid app-server response.") from exc
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        raise RuntimeError("Quota client stopped.")
