import json
import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path

from quota import ALLOWED_METHODS, QuotaClient, find_codex, get_five_hour_usage


class UsageParsingTests(unittest.TestCase):
    def test_accepts_boundaries_and_secondary_window(self):
        self.assertEqual(get_five_hour_usage({"rateLimits": {"primary": {"usedPercent": 0, "windowDurationMins": 300}}}), 0)
        self.assertEqual(get_five_hour_usage({"rateLimits": {"primary": {"usedPercent": 100, "windowDurationMins": 300}}}), 100)
        self.assertEqual(get_five_hour_usage({"rateLimits": {"primary": {"usedPercent": 80, "windowDurationMins": 10080}, "secondary": {"usedPercent": 42, "windowDurationMins": 300}}}), 42)

    def test_prefers_codex_bucket_and_supports_legacy_fallback(self):
        result = {
            "rateLimits": {"primary": {"usedPercent": 8, "windowDurationMins": 300}},
            "rateLimitsByLimitId": {"codex": {"secondary": {"usedPercent": 12, "windowDurationMins": 300}}},
        }
        self.assertEqual(get_five_hour_usage(result), 12)
        self.assertEqual(get_five_hour_usage({"rateLimits": result["rateLimits"], "rateLimitsByLimitId": None}), 8)

    def test_rejects_invalid_percentages_and_other_limits(self):
        for value in (-1, 101, "42", True, None, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_five_hour_usage({"rateLimits": {"primary": {"usedPercent": value, "windowDurationMins": 300}}})
        with self.assertRaises(ValueError):
            get_five_hour_usage({"rateLimits": {"limitId": "other", "primary": {"usedPercent": 42, "windowDurationMins": 300}}})
        with self.assertRaises(ValueError):
            get_five_hour_usage({"rateLimits": {"primary": {"usedPercent": 42, "windowDurationMins": 10080}}})

    def test_rpc_allowlist_is_narrow(self):
        self.assertEqual(ALLOWED_METHODS, {"initialize", "initialized", "account/rateLimits/read"})


class AppServerTests(unittest.TestCase):
    def test_handshake_and_quota_read(self):
        fake_server = r'''import json, sys
for line in sys.stdin:
    message = json.loads(line)
    method = message["method"]
    if method == "initialize":
        print(json.dumps({"id": message["id"], "result": {}}), flush=True)
    elif method == "account/rateLimits/read":
        print(json.dumps({"id": message["id"], "result": {"rateLimits": {"primary": {"usedPercent": 42, "windowDurationMins": 300}}}}), flush=True)
    elif method != "initialized":
        sys.exit(9)
'''
        events = queue.Queue()
        client = QuotaClient("unused", events, command_prefix=[sys.executable, "-u", "-c", fake_server])
        client.start()
        try:
            kind, value = events.get(timeout=3)
            self.assertEqual((kind, value), ("usage", 42.0))
        finally:
            client.close()
        self.assertFalse(client._thread.is_alive())

    def test_codex_path_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "codex.exe"
            file.write_text("", encoding="utf-8")
            self.assertEqual(find_codex(str(file)), str(file.resolve()))
            with self.assertRaises(FileNotFoundError):
                find_codex(str(file) + ".missing")


if __name__ == "__main__":
    unittest.main()
