from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "template" / ".mise" / "scripts" / "provision-bmad-skills.py"
SPEC = importlib.util.spec_from_file_location("provision_bmad_skills", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROVISIONER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVISIONER)


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def snapshot(path: Path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return ("missing",)
    permissions = stat.S_IMODE(mode)
    if stat.S_ISLNK(mode):
        return ("symlink", permissions, os.readlink(path))
    if stat.S_ISREG(mode):
        return ("file", permissions, path.read_bytes())
    if stat.S_ISDIR(mode):
        return (
            "directory",
            permissions,
            tuple((child.name, snapshot(child)) for child in sorted(path.iterdir())),
        )
    return ("special", permissions)


class ProvisionTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        source = os.environ.get("PJ_BMAD_PACK_ROOT")
        if not source:
            self.skipTest("PJ_BMAD_PACK_ROOT must identify the canonical candidate pack")
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-bmad-transaction-")
        self.root = Path(self.temporary.name)
        self.pack = self.root / "pack"
        shutil.copytree(source, self.pack, symlinks=True)
        self.project = self.root / "project"
        skills = self.project / ".agents" / "skills"
        skills.mkdir(parents=True)
        manifest = self.project / ".agents" / "skills.json"
        manifest.write_text('{"skills":[{"name":"custom","source":"file:///custom"}]}\n')
        manifest.chmod(0o600)
        copied = skills / "bmad-agent-pm"
        copied.mkdir()
        (copied / "legacy.txt").write_text("preserve exactly\n")
        (skills / "bmad-agent-analyst").symlink_to(
            self.pack / "bmad-agent-analyst", target_is_directory=True
        )
        (skills / "bmad-stale").symlink_to("/tmp/stale-target", target_is_directory=True)
        custom = skills / "custom"
        custom.mkdir()
        (custom / "SKILL.md").write_text("custom\n")
        self.previous_pack = os.environ.get("PJ_BMAD_PACK_ROOT")
        os.environ["PJ_BMAD_PACK_ROOT"] = str(self.pack)

    def tearDown(self) -> None:
        if self.previous_pack is None:
            os.environ.pop("PJ_BMAD_PACK_ROOT", None)
        else:
            os.environ["PJ_BMAD_PACK_ROOT"] = self.previous_pack
        self.temporary.cleanup()

    def test_nth_link_failure_restores_exact_project_state(self) -> None:
        before = snapshot(self.project)

        def fail_fifth(target: Path, link: Path, index: int) -> None:
            if index == 5:
                raise OSError("injected fifth-link failure")
            link.symlink_to(target, target_is_directory=True)

        with working_directory(self.project):
            with self.assertRaisesRegex(OSError, "fifth-link"):
                PROVISIONER.provision(create_link=fail_fifth)

        self.assertEqual(snapshot(self.project), before)

    def test_pack_mutation_after_preflight_rolls_back_exactly(self) -> None:
        before = snapshot(self.project)

        def mutate_pack() -> None:
            (self.pack / "bmad-agent-pm" / "SKILL.md").write_text("mutated after preflight\n")

        with working_directory(self.project):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                PROVISIONER.provision(after_preflight=mutate_pack)

        self.assertEqual(snapshot(self.project), before)

    def test_malformed_manifest_fails_before_creating_skills_or_temp_paths(self) -> None:
        project = self.root / "malformed-project"
        agents = project / ".agents"
        agents.mkdir(parents=True)
        manifest = agents / "skills.json"
        manifest.write_bytes(b"{malformed\n")
        manifest.chmod(0o600)
        before = snapshot(project)

        with working_directory(project):
            with self.assertRaises(json.JSONDecodeError):
                PROVISIONER.provision()

        self.assertEqual(snapshot(project), before)
        self.assertFalse((agents / "skills").exists())
        self.assertFalse(any(path.name.startswith(".bmad-transaction-") for path in agents.iterdir()))

    def test_applied_projection_mismatch_rolls_back_exactly(self) -> None:
        before = snapshot(self.project)

        def corrupt_projection(_manifest: Path, skills: Path) -> None:
            link = skills / "bmad-agent-analyst"
            link.unlink()
            link.symlink_to("/tmp/wrong-after-apply", target_is_directory=True)

        with working_directory(self.project):
            with self.assertRaisesRegex(ValueError, "link differs from plan"):
                PROVISIONER.provision(after_apply=corrupt_projection)

        self.assertEqual(snapshot(self.project), before)

    def test_success_is_complete_and_idempotent(self) -> None:
        with working_directory(self.project):
            self.assertGreater(PROVISIONER.provision(), 0)
            after_first = snapshot(self.project)
            self.assertEqual(PROVISIONER.provision(), 0)

        self.assertEqual(snapshot(self.project), after_first)
        skills = self.project / ".agents" / "skills"
        self.assertEqual(len([path for path in skills.iterdir() if path.name.startswith("bmad-")]), 76)
        self.assertTrue(
            all(
                (skills / path.name).is_symlink()
                for path in PROVISIONER.validate_trusted_pack(self.pack)
            )
        )


if __name__ == "__main__":
    unittest.main()
