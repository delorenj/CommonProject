from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "template/.agents/hooks/sync.py"
SPEC = importlib.util.spec_from_file_location("commonproject_hook_sync", PATH)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)
MASTER = json.loads((PATH.parent / "hooks.master.json").read_text())


class HubOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = self.root / "ownership.json"
        self.registry = self.root / "handlers.toml"
        self.registry.write_text("# test registry\n")
        self.env = mock.patch.dict(os.environ, {"BB_HOOK_OWNERSHIP": str(self.manifest)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def activate(self, handlers=None):
        self.manifest.write_text(json.dumps({"version": 1, "registry": str(self.registry), "clis": ["claude", "codex", "kimi", "hermes"], "handler_ids": handlers or ["skill-reminder", "hindsight-recall", "hindsight-retain", "hindsight-session-end"]}))

    def test_standalone_fallback_uses_seconds_and_true_session_end(self):
        groups = sync.build_event_groups(MASTER, "codex")
        self.assertEqual(groups["UserPromptSubmit"][0]["hooks"][0]["timeout"], 3)
        self.assertIn("SessionEnd", groups)
        self.assertNotIn("Stop", groups)
        self.assertTrue(sync.kimi_block(MASTER))

    def test_active_hub_removes_all_four_native_fallback_projections(self):
        self.activate()
        self.assertEqual(sync.build_event_groups(MASTER, "claude"), {})
        self.assertEqual(sync.build_event_groups(MASTER, "codex"), {})
        self.assertEqual(sync.kimi_block(MASTER), "")
        self.assertEqual(sync.hermes_commands(MASTER), [])

    def test_partial_ownership_preserves_other_concerns(self):
        self.activate(["hindsight-recall"])
        groups = sync.build_event_groups(MASTER, "codex")
        commands = [h["command"] for entries in groups.values() for group in entries for h in group["hooks"]]
        self.assertFalse(any("hindsight-recall.sh" in command for command in commands))
        self.assertTrue(any("hindsight-retain.sh" in command for command in commands))

    def test_claude_retirement_preserves_foreign_siblings_and_matcher(self):
        self.activate()
        settings = self.root / ".claude/settings.json"
        settings.parent.mkdir()
        foreign = {"type": "command", "command": "custom-project-hook"}
        settings.write_text(json.dumps({"theme": "dark", "hooks": {"PostToolUse": [{"matcher": "custom", "hooks": [foreign, {"command": "$CLAUDE_PROJECT_DIR/.agents/hooks/lib/hook-guard.sh hindsight-retain ignored"}]}]}}))
        with mock.patch.object(sync, "REPO_ROOT", self.root):
            result = sync.render_claude(MASTER)["settings"]
        self.assertEqual(result["theme"], "dark")
        self.assertEqual(result["hooks"]["PostToolUse"], [{"matcher": "custom", "hooks": [foreign]}])

    def test_kimi_removes_owned_block_even_with_foreign_hooks(self):
        target = self.root / "config.toml"
        foreign = '[[hooks]]\nevent="Stop"\ncommand="foreign"\n'
        original = foreign + "\n" + sync.kimi_block(MASTER)
        target.write_text(original)
        self.activate()
        with mock.patch.object(sync, "kimi_target", return_value=target):
            sync.install_kimi(MASTER)
            sync.install_kimi(MASTER)
        self.assertEqual(target.read_text(), foreign)
        self.assertFalse(any(self.root.glob("*.caf-bak")))


if __name__ == "__main__":
    unittest.main()
