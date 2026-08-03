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
SCRIPT = ROOT / "template" / ".mise" / "scripts" / "provision-packs.py"
SPEC = importlib.util.spec_from_file_location("provision_packs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROVISIONER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVISIONER)


def declared_pack_skills(pack: Path):
    """The declared inventory of a pack, via the shared sync engine."""
    metadata = PROVISIONER.engine.read_pack_metadata(pack)
    names = PROVISIONER.engine.pack_declared_skills(pack, metadata, {"name": "bmad"})
    return [pack / name for name in names]


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
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-packs-transaction-")
        self.root = Path(self.temporary.name)
        self.pack = self.root / "pack"
        shutil.copytree(source, self.pack, symlinks=True)
        self.project = self.root / "project"
        skills = self.project / ".agents" / "skills"
        skills.mkdir(parents=True)
        manifest = self.project / ".agents" / "skills.json"
        private = skills / "bmad-private-custom"
        private.mkdir()
        (private / "SKILL.md").write_text("private custom must survive\n")
        manifest.write_text(
            json.dumps(
                {
                    "skills": [
                        {"name": "custom", "source": "file:///custom"},
                        {"name": "bmad-private-custom", "source": private.as_uri()},
                        {"name": "bmad-stale", "source": (self.pack / "bmad-stale").as_uri()},
                    ]
                }
            )
            + "\n"
        )
        manifest.chmod(0o600)
        copied = skills / "bmad-agent-pm"
        copied.mkdir()
        (copied / "legacy.txt").write_text("preserve exactly\n")
        (skills / "bmad-agent-analyst").symlink_to(
            self.pack / "bmad-agent-analyst", target_is_directory=True
        )
        (skills / "bmad-stale").symlink_to(
            self.pack / "bmad-stale", target_is_directory=True
        )
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
        self.assertFalse(any(path.name.startswith(".packs-transaction-") for path in agents.iterdir()))

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
        self.assertTrue((skills / "bmad-private-custom").is_dir())
        self.assertEqual(
            (skills / "bmad-private-custom" / "SKILL.md").read_text(),
            "private custom must survive\n",
        )
        self.assertFalse((skills / "bmad-stale").exists())
        manifest = json.loads((self.project / ".agents" / "skills.json").read_text())
        self.assertIn(
            {
                "name": "bmad-private-custom",
                "source": (skills / "bmad-private-custom").as_uri(),
            },
            manifest["skills"],
        )
        self.assertNotIn("bmad-stale", [entry.get("name") for entry in manifest["skills"]])
        self.assertTrue(
            all(
                (skills / path.name).is_symlink()
                for path in declared_pack_skills(self.pack)
            )
        )

    def test_unowned_bmad_prefixed_custom_skill_is_preserved(self) -> None:
        custom = self.project / ".agents" / "skills" / "bmad-private-custom"
        before = snapshot(custom)

        with working_directory(self.project):
            self.assertGreater(PROVISIONER.provision(), 0)
            after_first = snapshot(self.project)
            self.assertEqual(PROVISIONER.provision(), 0)

        self.assertEqual(snapshot(custom), before)
        self.assertEqual(snapshot(self.project), after_first)


def write_skill(directory: Path) -> None:
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(f"# {directory.name}\n")


class DeclaredPackRedundancyTests(unittest.TestCase):
    """PACKS-CONTRACT section 6: "Never remove entries that point outside the pack."

    A pack family is `packs/<name>/<version>/`. Declaring `<name>` resolves ONE
    version, and only that version is the pack. A `skills[]` entry pointing at a
    SIBLING version is only redundant when the resolved pack also declares that
    skill; otherwise the entry is the sole reference to a skill nothing else
    provides and deleting it loses the skill. This mirrors pjangler's
    `isRedundantDeclaredPackEntry` so `pj migrate` and this script can never
    disagree about the same manifest.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-packs-redundancy-")
        self.root = Path(self.temporary.name)

        # A registry with a two-version `demo` family: 2.0.0 (the version that
        # resolves) dropped `beta`, which only 1.0.0 ever declared.
        self.registry = self.root / "registry"
        self.old = self.registry / "packs" / "demo" / "1.0.0"
        self.new = self.registry / "packs" / "demo" / "2.0.0"
        write_skill(self.old / "alpha")
        write_skill(self.old / "beta")
        write_skill(self.new / "alpha")

        # The implicit BMAD pin is sealed and always resolves; stub it out with
        # an empty sealed pack so this test never depends on ~/code/skillex.
        self.bmad = self.root / "bmad-stub"
        self.bmad.mkdir()
        (self.bmad / "SHA256SUMS").write_text("")

        self.outside = self.root / "outside" / "gamma"
        write_skill(self.outside)

        self.project = self.root / "project"
        (self.project / ".agents").mkdir(parents=True)
        self.manifest_path = self.project / ".agents" / "skills.json"
        self.manifest_path.write_text(
            json.dumps(
                {
                    "packs": ["demo"],
                    "skills": [
                        # Provided by the resolved pack, via a sibling version.
                        {"name": "alpha", "source": (self.old / "alpha").as_uri()},
                        # NOT provided by the resolved pack: must survive.
                        {"name": "beta", "source": (self.old / "beta").as_uri()},
                        # Straight into the resolved pack root: redundant.
                        {"name": "alpha-dup", "source": (self.new / "alpha").as_uri()},
                        # Nothing to do with the pack at all.
                        {"name": "gamma", "source": self.outside.as_uri()},
                    ],
                },
                indent=2,
            )
            + "\n"
        )

        self.previous = {
            name: os.environ.get(name)
            for name in ("PJ_SKILLS_REGISTRY_ROOT", "PJ_BMAD_PACK_ROOT", "PJ_PACK_ROOT_DEMO")
        }
        os.environ["PJ_SKILLS_REGISTRY_ROOT"] = str(self.registry)
        os.environ["PJ_BMAD_PACK_ROOT"] = str(self.bmad)
        os.environ.pop("PJ_PACK_ROOT_DEMO", None)

    def tearDown(self) -> None:
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.temporary.cleanup()

    def manifest_skills(self):
        return json.loads(self.manifest_path.read_text())["skills"]

    def test_sibling_version_entry_the_resolved_pack_does_not_declare_is_kept(self) -> None:
        with working_directory(self.project):
            PROVISIONER.provision()

        names = [entry["name"] for entry in self.manifest_skills()]
        self.assertIn("beta", names, "a skill no declared pack provides must never be dropped")
        self.assertIn("gamma", names)
        # Parity with pjangler is two-sided: entries the resolved pack DOES
        # provide are still pruned, whichever version they point at.
        self.assertNotIn("alpha", names)
        self.assertNotIn("alpha-dup", names)

        beta = next(entry for entry in self.manifest_skills() if entry["name"] == "beta")
        self.assertEqual(beta["source"], (self.old / "beta").as_uri())

        # The projection is the resolved pack only; `beta` stays sync-skills' job.
        skills = self.project / ".agents" / "skills"
        self.assertEqual(os.readlink(skills / "alpha"), str(self.new / "alpha"))
        self.assertFalse((skills / "beta").exists() or (skills / "beta").is_symlink())

    def test_redundancy_pruning_is_idempotent(self) -> None:
        with working_directory(self.project):
            PROVISIONER.provision()
            after_first = snapshot(self.project)
            self.assertEqual(PROVISIONER.provision(), 0)

        self.assertEqual(snapshot(self.project), after_first)

    def test_sibling_version_entry_is_dropped_once_the_pack_declares_it(self) -> None:
        """The gate is the resolved pack's inventory, not the path shape."""
        write_skill(self.new / "beta")

        with working_directory(self.project):
            PROVISIONER.provision()

        names = [entry["name"] for entry in self.manifest_skills()]
        self.assertNotIn("beta", names)
        self.assertIn("gamma", names)
        self.assertEqual(
            os.readlink(self.project / ".agents" / "skills" / "beta"),
            str(self.new / "beta"),
        )


if __name__ == "__main__":
    unittest.main()
