import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from claude_quota import (ClaudeQuotaClient, RateLimited, get_five_hour_usage,
                          read_access_token, request_usage)


class ClaudeUsageTests(unittest.TestCase):
    def test_reads_five_hour_used_percent_without_converting_to_remaining(self):
        for value in (0, 37.5, 100):
            self.assertEqual(get_five_hour_usage({
                "five_hour": {"utilization": value, "resets_at": "2026-10-14T10:00:00Z"},
                "seven_day": {"utilization": 88},
            }), value)

    def test_rejects_missing_and_invalid_five_hour_usage(self):
        for value in (None, True, "42", -1, 101, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_five_hour_usage({"five_hour": {"utilization": value}})
        for response in ({}, {"five_hour": None}, {"seven_day": {"utilization": 20}}):
            with self.assertRaises(ValueError):
                get_five_hour_usage(response)

    def test_existing_claude_login_is_read_without_modifying_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".credentials.json"
            document = json.dumps({"claudeAiOauth": {"accessToken": "fake-test-token"}})
            path.write_text(document)
            self.assertEqual(read_access_token(path), "fake-test-token")
            self.assertEqual(path.read_text(), document)

    def test_expired_or_api_key_login_does_not_become_a_subscription_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".credentials.json"
            for document in ({"apiKey": "fake-test-key"},
                             {"claudeAiOauth": {"accessToken": "fake-test-token", "expiresAt": 1}}):
                path.write_text(json.dumps(document))
                with self.assertRaises(RuntimeError):
                    read_access_token(path)

    @patch("claude_quota.urllib.request.build_opener")
    def test_only_usage_get_is_sent_and_response_is_parsed(self, build_opener):
        response = MagicMock()
        response.read.return_value = b'{"five_hour":{"utilization":37.5}}'
        build_opener.return_value.open.return_value.__enter__.return_value = response
        self.assertEqual(request_usage("fake-test-token"), 37.5)
        request = build_opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Anthropic-beta"), "oauth-2025-04-20")
        self.assertEqual(request.get_header("Authorization"), "Bearer fake-test-token")
        self.assertIsNone(request.data)

    @patch("claude_quota.urllib.request.build_opener")
    def test_rate_limit_backoff_and_authentication_errors_are_sanitized(self, build_opener):
        build_opener.return_value.open.side_effect = urllib.error.HTTPError(
            "https://api.anthropic.com/api/oauth/usage", 429, "secret response", {"Retry-After": "180"}, None
        )
        with self.assertRaises(RateLimited) as raised:
            request_usage("fake-test-token")
        self.assertEqual(raised.exception.retry_seconds, 180)
        build_opener.return_value.open.side_effect = urllib.error.HTTPError(
            "https://api.anthropic.com/api/oauth/usage", 401, "secret response", {}, None
        )
        with self.assertRaises(RuntimeError) as raised:
            request_usage("fake-test-token")
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("fake-test-token", str(raised.exception))

    def test_not_installed_publishes_help_without_a_network_or_model_request(self):
        with tempfile.TemporaryDirectory() as directory:
            events = queue.Queue()
            with patch("claude_quota.credentials_path", return_value=Path(directory) / "missing.json"), \
                 patch("claude_quota.request_usage") as fetch:
                client = ClaudeQuotaClient(events)
                client.start()
                try:
                    kind, message = events.get(timeout=2)
                    self.assertEqual(kind, "error")
                    self.assertIn("Claude Code", message)
                    fetch.assert_not_called()
                finally:
                    client.close()


if __name__ == "__main__":
    unittest.main()
