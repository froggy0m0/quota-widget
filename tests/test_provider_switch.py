import argparse
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

from main import DeerWidget


class ProviderSwitchTests(unittest.TestCase):
    def make_widget(self):
        widget = DeerWidget.__new__(DeerWidget)
        widget.provider = "codex"
        widget.args = argparse.Namespace(demo=False, codex_path=None)
        widget.client = Mock()
        widget.events = queue.Queue()
        widget.usage = 80
        widget.healthy = True
        widget.error = ""
        widget.root = Mock()
        widget.provider_var = Mock()
        widget._render = Mock()
        widget.style = "round"
        widget.size = 128
        return widget

    @patch("main.ClaudeQuotaClient")
    def test_switch_detaches_old_replies_clears_usage_and_saves_selection(self, claude):
        widget = self.make_widget()
        old_client = widget.client
        old_events = widget.events
        old_events.put(("usage", 80))
        with tempfile.TemporaryDirectory() as directory:
            widget.settings_path = Path(directory) / "settings.json"
            widget._select_provider("claude")
            old_client.close.assert_called_once()
            claude.assert_called_once_with(widget.events)
            claude.return_value.start.assert_called_once()
            self.assertIsNot(widget.events, old_events)
            self.assertIsNone(widget.usage)
            self.assertFalse(widget.healthy)
            saved = json.loads(widget.settings_path.read_text())
            self.assertEqual(saved, {"style": "round", "size": 128, "provider": "claude"})
            restored = self.make_widget()
            restored.settings_path = widget.settings_path
            restored._load_settings()
            self.assertEqual(restored.provider, "claude")

    def test_old_settings_keep_codex_as_default(self):
        widget = self.make_widget()
        with tempfile.TemporaryDirectory() as directory:
            widget.settings_path = Path(directory) / "settings.json"
            widget.settings_path.write_text('{"style":"antlers","size":160}')
            widget._load_settings()
            self.assertEqual(widget.provider, "codex")
            self.assertEqual(widget.style, "antlers")
            self.assertEqual(widget.size, 160)


if __name__ == "__main__":
    unittest.main()
