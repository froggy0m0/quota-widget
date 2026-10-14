import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from claude_quota import ClaudeQuotaClient, get_five_hour_usage, read_usage, usage_path


class ClaudeUsageTests(unittest.TestCase):
    def test_percentage_is_rounded_used_usage_and_reset_boundary_is_strict(self):
        for used in (0, 14.4, 14.6, 42.5, 43.5, 100):
            with self.subTest(used=used):
                record = {"used_percentage": used, "resets_at": 2000}
                self.assertEqual(get_five_hour_usage(record, now=1000), round(used))
                self.assertEqual(get_five_hour_usage(record, now=2000), round(used))
                self.assertEqual(get_five_hour_usage(record, now=2001), 0)

    def test_invalid_records_are_errors_even_after_the_reset(self):
        records = [None, [], {}, {"used_percentage": 43}, {"resets_at": 2000}]
        for invalid in (None, True, "42", -1, 101, float("nan"), float("inf")):
            records.append({"used_percentage": invalid, "resets_at": 1})
        for invalid in (None, True, "2000", float("nan"), float("inf")):
            records.append({"used_percentage": 43, "resets_at": invalid})
        for record in records:
            with self.subTest(record=record), self.assertRaises(ValueError):
                get_five_hour_usage(record, now=1000)

    def test_home_path_is_used_and_cache_is_read_without_modification(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "claude_quota.Path.home", return_value=Path(directory)
        ), patch("claude_quota.time.time", return_value=1000):
            path = Path(directory) / ".claude" / "usage-widget" / "usage.json"
            self.assertEqual(usage_path(), path)
            path.parent.mkdir(parents=True)
            payload = '{"used_percentage": 43.4, "resets_at": 2000}'
            path.write_text(payload, encoding="utf-8")
            before = path.stat().st_mtime_ns
            self.assertEqual(read_usage(), 43)
            self.assertEqual(path.read_text(encoding="utf-8"), payload)
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_missing_unreadable_or_malformed_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "claude_quota.Path.home", return_value=Path(directory)
        ):
            with self.assertRaisesRegex(RuntimeError, "^Claude 연결 안됨$"):
                read_usage()
            path = usage_path()
            path.parent.mkdir(parents=True)
            for payload in (b'{', b'\xff', b'null'):
                path.write_bytes(payload)
                with self.assertRaisesRegex(RuntimeError, "^Claude 연결 안됨$"):
                    read_usage()
            with patch("claude_quota.Path.read_text", side_effect=PermissionError):
                with self.assertRaises(RuntimeError):
                    read_usage()

    def test_polling_recovers_after_cache_disappears_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "claude_quota.Path.home", return_value=Path(directory)
        ), patch("claude_quota.time.time", return_value=1000):
            path = usage_path()
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"used_percentage": 43, "resets_at": 2000}))
            events = queue.Queue()
            client = ClaudeQuotaClient(events)

            def next_read(seconds):
                self.assertEqual(seconds, 60)
                if not path.exists():
                    path.write_text(json.dumps({"used_percentage": 17.6, "resets_at": 2000}))
                else:
                    path.unlink()
                return real_wait(0.02)

            real_wait = client._stop.wait
            with patch.object(client._stop, "wait", side_effect=next_read):
                client.start()
                try:
                    self.assertEqual(events.get(timeout=2), ("usage", 43.0))
                    self.assertEqual(events.get(timeout=2)[0], "error")
                    self.assertEqual(events.get(timeout=2), ("usage", 18.0))
                finally:
                    client.close()
                self.assertFalse(client._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
