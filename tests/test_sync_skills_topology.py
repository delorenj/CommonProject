from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "template" / ".mise" / "scripts" / "sync-skills.py"
PROVISION_SCRIPT = ROOT / "template" / ".mise" / "scripts" / "provision-packs.py"
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

    def test_shipped_skill_scripts_are_executable(self) -> None:
        for script in (PROVISION_SCRIPT, SCRIPT):
            self.assertNotEqual(
                script.stat().st_mode & 0o111,
                0,
                f"fresh template script must be executable: {script}",
            )

    def test_canonical_alias_projects_into_the_managed_skills_dir(self) -> None:
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
        self.assertTrue(
            (managed / "managed-example").is_symlink(),
            "the alias makes .agents/skills the CLI's skills dir, so the projection lands there",
        )
        self.assertEqual(
            os.readlink(managed / "managed-example"), str(self.source)
        )

    def test_every_cli_aliased_projects_once_not_never(self) -> None:
        managed = self.project / ".agents" / "skills"
        managed.mkdir(parents=True)
        for relative in SYNC.cli_skill_dirs("project"):
            cli_dir = self.project / relative
            cli_dir.parent.mkdir(parents=True, exist_ok=True)
            cli_dir.symlink_to(
                os.path.relpath(managed, cli_dir.parent), target_is_directory=True
            )

        active = SYNC.preflight_cli_dirs(self.project, ["managed-example"])
        self.assertEqual(
            [expected for _, expected in active],
            [managed],
            "six aliases to one directory must yield exactly one fanout target",
        )

        SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

        self.assertTrue((managed / "managed-example").is_symlink())
        self.assertEqual(os.readlink(managed / "managed-example"), str(self.source))
        for relative in SYNC.cli_skill_dirs("project"):
            self.assertTrue((self.project / relative / "managed-example").exists())

    def test_alias_never_clobbers_a_real_skill_dir_in_the_managed_projection(self) -> None:
        managed = self.project / ".agents" / "skills"
        collision = managed / "managed-example"
        collision.mkdir(parents=True)
        (collision / "user-data").write_text("do not delete\n")
        codex = self.project / ".codex"
        codex.mkdir()
        claude = self.project / ".claude"
        claude.mkdir()
        (claude / "skills").symlink_to("../.agents/skills", target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "real skill directory in the managed projection"):
            SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

        self.assertTrue(collision.is_dir() and not collision.is_symlink())
        self.assertEqual((collision / "user-data").read_text(), "do not delete\n")
        self.assertFalse((codex / "skills").exists())

    def test_zero_destinations_with_skills_to_sync_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "refusing to silently drop"):
            SYNC.fanout_to_cli(self.project, {"managed-example": self.source})

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

    def test_source_ancestor_cycle_fails_before_any_destination_mutation(self) -> None:
        """A repo-root skill must never be linked back inside that same repo."""
        codex = self.project / ".codex"
        codex.mkdir()
        claude = self.project / ".claude"
        claude.mkdir()

        with self.assertRaisesRegex(ValueError, "recursive skill symlink"):
            SYNC.fanout_to_cli(self.project, {"self-skill": self.project})

        self.assertFalse((codex / "skills").exists())
        self.assertFalse((claude / "skills").exists())

    def test_catalog_alias_to_repo_root_is_also_rejected(self) -> None:
        claude = self.project / ".claude"
        claude.mkdir()
        catalog_alias = self.root / "catalog-skill"
        catalog_alias.symlink_to(self.project, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "recursive skill symlink"):
            SYNC.fanout_to_cli(self.project, {"self-skill": catalog_alias})

        self.assertFalse((claude / "skills").exists())

    def test_parent_swap_after_preflight_cannot_mutate_outside_project(self) -> None:
        codex = self.project / ".codex"
        codex.mkdir()
        outside = self.root / "outside"
        outside_skill = outside / "skills" / "managed-example"
        outside_skill.mkdir(parents=True)
        (outside / "sentinel").write_text("outside must survive\n")
        (outside_skill / "user-data").write_text("do not delete\n")
        active = SYNC.preflight_cli_dirs(self.project, ["managed-example"])
        original_codex = self.project / ".codex-original"

        def swap_parent() -> None:
            codex.rename(original_codex)
            codex.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "symlinked destination directory"):
            SYNC.fanout_to_cli(
                self.project,
                {"managed-example": self.source},
                active_cli_dirs=active,
                before_mutation=swap_parent,
            )

        self.assertTrue(codex.is_symlink())
        self.assertFalse((original_codex / "skills").exists())
        self.assertEqual((outside / "sentinel").read_text(), "outside must survive\n")
        self.assertEqual((outside_skill / "user-data").read_text(), "do not delete\n")
        self.assertTrue(outside_skill.is_dir())


class RegistryPackLadderTests(unittest.TestCase):
    REGISTRY = "https://github.com/delorenj/skillex.git"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-pack-ladder-")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.previous_home = os.environ.get("HOME")
        self.previous_override = os.environ.get("PJ_SKILLS_REGISTRY_ROOT")
        os.environ["HOME"] = str(self.home)
        os.environ.pop("PJ_SKILLS_REGISTRY_ROOT", None)
        self.cache = SYNC.registry_cache_dir(self.REGISTRY)
        self.fallback = self.home / "code" / "skillex"
        self.cache.mkdir(parents=True)
        self.fallback.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.previous_home
        if self.previous_override is None:
            os.environ.pop("PJ_SKILLS_REGISTRY_ROOT", None)
        else:
            os.environ["PJ_SKILLS_REGISTRY_ROOT"] = self.previous_override
        self.temporary.cleanup()

    def write_pack(self, registry: Path, *, name: str = "demo", version: str = "2.0.0", attested: bool) -> Path:
        pack = registry / "packs" / "demo" / "2.0.0"
        skill = pack / "alpha"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# alpha\n")
        if attested:
            (pack / "pack.toml").write_text(
                f'[pack]\nname = "{name}"\nversion = "{version}"\n\n'
                '[freeform]\nskills = ["alpha"]\n'
            )
        return pack

    def resolve(self) -> Path:
        entry = SYNC.normalize_pack_entry({"name": "demo", "version": "2.0.0"})
        root, _description = SYNC.resolve_pack_root(
            entry,
            self.root,
            self.root / "skill-cache",
            {},
            self.REGISTRY,
        )
        return root

    def test_attested_lower_checkout_outranks_unattested_cache(self) -> None:
        self.write_pack(self.cache, attested=False)
        expected = self.write_pack(self.fallback, attested=True)
        self.assertEqual(self.resolve(), expected)

    def test_hostile_metadata_never_falls_through(self) -> None:
        self.write_pack(self.cache, name="other", attested=True)
        self.write_pack(self.fallback, attested=True)
        with self.assertRaisesRegex(ValueError, "declares name 'other'"):
            self.resolve()

    def test_explicit_missing_checkout_is_exclusive(self) -> None:
        self.write_pack(self.fallback, attested=True)
        os.environ["PJ_SKILLS_REGISTRY_ROOT"] = str(self.root / "missing")
        with self.assertRaisesRegex(SYNC.PackUnavailable, "Explicit registry checkout"):
            self.resolve()


class FlattenedLeafNameTests(unittest.TestCase):
    """Contract 3b: a flattened LEAF name is lifted straight off the filesystem.

    Without flatten a `pack.toml` pack projects exactly the strings its author typed
    into `[freeform].skills`.  Flatten is the one place an upstream directory name
    becomes a symlink name in six CLI skill directories, where `-rf`, `--help`, `*`
    and embedded control characters are argv- and glob-hostile.
    """

    HOSTILE = ["*", "--help", "-rf", "a\nb", "con:", "tab\there", "SKILL.md-ish", "Upper"]

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="commonproject-flatten-names-")
        self.root = Path(self.temporary.name) / "pack"
        (self.root / "grp").mkdir(parents=True)
        (self.root / "grp" / "DESCRIPTION.md").write_text("container metadata\n")
        for name in [*self.HOSTILE, "good-leaf"]:
            leaf = self.root / "grp" / name
            leaf.mkdir()
            (leaf / "SKILL.md").write_text("leaf\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def flatten(self, declared):
        return SYNC.flatten_pack_inventory(self.root, "demo", declared)

    def test_hostile_leaf_basenames_are_skipped(self) -> None:
        projected = [name for name, _relative in self.flatten(["grp"])]
        self.assertEqual(projected, ["good-leaf"])
        for name in self.HOSTILE:
            self.assertNotIn(name, projected)

    def test_container_of_only_hostile_leaves_still_reports(self) -> None:
        allbad = self.root / "allbad"
        allbad.mkdir()
        for name in ("-delete", "?glob"):
            leaf = allbad / name
            leaf.mkdir()
            (leaf / "SKILL.md").write_text("leaf\n")
        self.assertEqual([name for name, _ in self.flatten(["allbad"])], [])

    def test_declared_leaf_keeps_its_author_declared_name(self) -> None:
        """The gate applies to EXPANSION only, never to a name the author typed."""
        legacy = self.root / "Legacy_Skill"
        legacy.mkdir()
        (legacy / "SKILL.md").write_text("leaf\n")
        self.assertEqual(
            [name for name, _ in self.flatten(["Legacy_Skill"])], ["Legacy_Skill"]
        )


if __name__ == "__main__":
    unittest.main()
