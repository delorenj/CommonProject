from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "template" / ".mise" / "scripts" / "sync-skills.py"
SPEC = importlib.util.spec_from_file_location("sync_skills", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class SyncSkillsTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-sync-topology-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.source = self.root / "source-skill"
        self.project.mkdir()
        self.source.mkdir()
        (self.source / "SKILL.md").write_text("source\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_canonical_claude_alias_is_accepted_without_mutating_managed_projection(self) -> None:
        managed = self.project / ".agents" / "skills"
        custom = managed / "custom-real-skill"
        custom.mkdir(parents=True)
        (custom / "SKILL.md").write_text("custom\n")
        claude = self.project / ".claude"
        claude.mkdir()
        (claude / "skills").symlink_to("../.agents/skills", target_is_directory=True)

        SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

        self.assertTrue((claude / "skills").is_symlink())
        self.assertEqual(os.readlink(claude / "skills"), "../.agents/skills")
        self.assertEqual((custom / "SKILL.md").read_text(), "custom\n")
        self.assertFalse(
            (managed / "managed-example").exists(),
            "the canonical alias must not make sync-skills mutate the provisioner-owned projection",
        )

    def test_external_cli_symlink_fails_before_any_destination_mutation(self) -> None:
        codex = self.project / ".codex"
        codex.mkdir()
        claude = self.project / ".claude"
        claude.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "sentinel").write_text("do-not-touch\n")
        (claude / "skills").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "Refusing symlinked CLI skills directory"):
            SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

        self.assertFalse((codex / "skills").exists())
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel"])
        self.assertEqual((outside / "sentinel").read_text(), "do-not-touch\n")

    def test_broken_canonical_alias_fails_before_mutation(self) -> None:
        codex = self.project / ".codex"
        codex.mkdir()
        claude = self.project / ".claude"
        claude.mkdir()
        (claude / "skills").symlink_to("../.agents/skills", target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "alias target is not a real directory"):
            SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

        self.assertFalse((codex / "skills").exists())
        self.assertTrue((claude / "skills").is_symlink())


if __name__ == "__main__":
    unittest.main()
