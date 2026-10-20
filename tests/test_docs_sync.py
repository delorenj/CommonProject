"""Deterministic tests for the docs:sync core task (PJAN-175).

Covers the managed helper template/.mise/scripts/docs-sync.py and the
rendered [tasks."docs:sync"] block in template/mise.toml.jinja, rendered
with agent_hooks_layer both true and false. No network, no live vault,
no GUI: every sync runs with --no-open against a temp vault.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jinja2


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
SCRIPT = TEMPLATE / ".mise/scripts/docs-sync.py"

JINJA_CONTEXT = {
    "project_name": "Fixture App",
    "project_description": "",
    "project_slug": "fixture-app",
    "project_identifier": "FIXT",
    "ticket_provider": "plane",
    "plane_workspace": "33god",
    "plane_project_id": "",
    "plane_base": "",
    "is_obsidian_plugin": False,
}


def render_jinja(name, **overrides):
    env = jinja2.Environment(keep_trailing_newline=True)
    context = {**JINJA_CONTEXT, **overrides}
    return env.from_string((TEMPLATE / name).read_text()).render(**context)


class DocsSyncHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo with spaces"
        self.root.mkdir()
        self.vault = Path(self.tmp.name) / "Vault & notes"
        self.vault.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.manifest("fixture-app", "Fixture App")

    def manifest(self, project_id, project_name):
        (self.root / ".project.json").write_text(json.dumps(
            {"project_id": project_id, "project_name": project_name}))

    def write(self, name, content="# Example\n", age=0):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        os.utime(path, (time.time() - age, time.time() - age))
        return path

    def run_sync(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root),
             "--vault", str(self.vault), "--no-open", *args],
            text=True, capture_output=True,
        )

    def snapshot(self, project_id="fixture-app"):
        return next((self.vault / "Projects" / project_id).iterdir())

    # --- The nine original fixture cases, generalized ---

    def test_recent_docs_preserve_paths_and_skip_noise(self):
        self.write("docs/a/Note & one.md", "alpha")
        self.write("_bmad-output/specs/Note & one.md", "beta")
        self.write("README.md")
        self.write("docs/old.md", age=48 * 3600)
        self.write("docs/.private.md")
        self.write(".gitignore", "docs/ignored.md\n")
        self.write("docs/ignored.md")
        self.write("_bmad/framework.md")
        self.write("node_modules/library/README.md")
        self.write("docs/not-markdown.json", "{}")
        (self.root / "docs/link.md").symlink_to(self.root / "README.md")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = self.snapshot()
        self.assertEqual((snapshot / "docs/a/Note & one.md").read_text(), "alpha")
        self.assertEqual((snapshot / "_bmad-output/specs/Note & one.md").read_text(), "beta")
        self.assertEqual(len(list(snapshot.rglob("*.md"))), 4)
        self.assertIn("Note%20%26%20one.md", (snapshot / "_docs-sync/Index.md").read_text())

    def test_repeat_sync_preserves_previous_notes(self):
        self.write("docs/first.md", "first")
        self.assertEqual(self.run_sync().returncode, 0)
        self.write("docs/first.md", "updated")
        self.write("docs/second.md")
        self.assertEqual(self.run_sync().returncode, 0)
        snapshot = self.snapshot()
        (snapshot / "personal.md").write_text("my notes")
        (self.root / "docs/first.md").unlink()
        self.assertEqual(self.run_sync().returncode, 0)
        self.assertEqual((snapshot / "docs/first.md").read_text(), "updated")
        self.assertEqual((snapshot / "personal.md").read_text(), "my notes")
        self.assertIn("docs/first.md", (snapshot / "_docs-sync/Index.md").read_text())

    def test_empty_sync_does_not_create_snapshot(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No Markdown", result.stdout)
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_hours_controls_selection_and_rejects_invalid_values(self):
        self.write("docs/older.md", age=48 * 3600)
        self.assertEqual(self.run_sync("--hours", "72").returncode, 0)
        for value in ("0", "-1", "nan", "inf", "invalid"):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_sync("--hours", value).returncode, 0)

    def test_root_note_cannot_collide_with_index(self):
        self.write("Docs Sync.md", "keep this source note")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = self.snapshot()
        self.assertEqual((snapshot / "Docs Sync.md").read_text(), "keep this source note")
        self.assertIn("../Docs%20Sync.md", (snapshot / "_docs-sync/Index.md").read_text())

    def test_git_error_includes_diagnostic(self):
        shutil.rmtree(self.root / ".git")
        (self.root / ".git").write_text("gitdir: missing-repository\n")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a git repository", result.stderr)

    def test_missing_vault_is_not_created(self):
        self.vault.rmdir()
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("vault", result.stderr.lower())
        self.assertFalse(self.vault.exists())

    def load_module(self):
        spec = importlib.util.spec_from_file_location("docs_sync", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_opens_encoded_note_and_reports_launcher_failure(self):
        module = self.load_module()
        note = self.vault / "Projects/fixture-app/2026-10-20/Docs Sync.md"
        with patch.object(module.shutil, "which", return_value="/usr/bin/xdg-open"), patch.object(
            module.subprocess, "run"
        ) as run:
            module.open_note(note)
            uri = run.call_args.args[0][-1]
            self.assertEqual(parse_qs(urlparse(uri).query)["path"], [str(note)])
            self.assertIn("%20", uri)
            self.assertNotIn("+", uri)
            run.side_effect = subprocess.CalledProcessError(1, "xdg-open")
            with self.assertRaises(subprocess.CalledProcessError):
                module.open_note(note)
        with patch.object(module.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "no-open"):
                module.open_note(note)

    # --- Generalized project identity ---

    def test_manifest_identity_names_folder_and_heading(self):
        self.manifest("drum-machine", "Drum Machine Deluxe")
        self.write("docs/note.md", "hello")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        index = self.snapshot("drum-machine") / "_docs-sync/Index.md"
        heading = index.read_text().splitlines()[0]
        self.assertRegex(heading, r"^# Drum Machine Deluxe docs — \d{4}-\d{2}-\d{2}$")

    def test_different_project_names_including_spaces(self):
        for project_id, project_name in [
            ("tonnybox", "TonnyBox"),
            ("vern-voice", "Vernon Voice"),
            ("a", "A Project With Many Words In Its Name"),
        ]:
            with self.subTest(project_id=project_id):
                self.manifest(project_id, project_name)
                self.write("docs/note.md", project_id)
                result = self.run_sync()
                self.assertEqual(result.returncode, 0, result.stderr)
                snapshot = self.snapshot(project_id)
                self.assertEqual((snapshot / "docs/note.md").read_text(), project_id)
                self.assertIn(f"# {project_name} docs — ",
                              (snapshot / "_docs-sync/Index.md").read_text())

    def test_bare_repo_falls_back_to_directory_name(self):
        (self.root / ".project.json").unlink()
        self.write("docs/note.md")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = self.snapshot("repo with spaces")
        self.assertIn("# repo with spaces docs — ",
                      (snapshot / "_docs-sync/Index.md").read_text())

    def test_blank_identity_falls_back_to_directory_name(self):
        self.manifest("  ", "")
        self.write("docs/note.md")
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.snapshot("repo with spaces")

    def test_invalid_project_id_is_rejected_before_any_copy(self):
        for bad in ("..", "../escape", "a/b", "back\\slash", ".", "\x00"):
            with self.subTest(project_id=bad):
                self.manifest(bad, "Bad")
                self.write("docs/note.md")
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsafe", result.stderr)
                self.assertFalse((self.vault / "Projects").exists())

    def test_malformed_manifest_is_an_error_not_a_fallback(self):
        (self.root / ".project.json").write_text("{not json")
        self.write("docs/note.md")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot parse", result.stderr)
        self.assertFalse((self.vault / "Projects").exists())

    def test_no_concrete_project_references_in_template_script(self):
        source = SCRIPT.read_text().lower()
        for name in ("gruvato", "drumjangler", "tonnybox", "holocron"):
            self.assertNotIn(name, source)


class MiseTomlTemplateTests(unittest.TestCase):
    def render(self, agent_hooks_layer):
        return render_jinja("mise.toml.jinja", agent_hooks_layer=agent_hooks_layer)

    def test_docs_sync_task_renders_in_both_hook_layers(self):
        for flag in (True, False):
            with self.subTest(agent_hooks_layer=flag):
                text = self.render(flag)
                self.assertNotIn("{%", text)
                config = tomllib.loads(text)
                task = config["tasks"]["docs:sync"]
                self.assertIn("{{config_root}}/.mise/scripts/docs-sync.py", task["run"])
                self.assertIn('--root "{{config_root}}"', task["run"])
                self.assertNotIn("IMPLEMENT", task["run"])
                for option in ("--hours", "--vault", "--no-open"):
                    self.assertIn(option, task["usage"])
                self.assertEqual(("hooks:sync" in config["tasks"]), flag)

    def test_rendered_toml_has_no_project_specific_references(self):
        for flag in (True, False):
            text = self.render(flag).lower()
            for name in ("gruvato", "drumjangler", "tonnybox", "holocron"):
                self.assertNotIn(name, text)


@unittest.skipUnless(shutil.which("mise"), "mise CLI not installed")
class RenderedProjectEndToEndTests(unittest.TestCase):
    """Render mise.toml + .project.json + the helper into a temp project and
    run the generated task under an isolated mise env and temp vault."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "rendered project"
        (self.project / ".mise/scripts").mkdir(parents=True)
        (self.project / "mise.toml").write_text(render_jinja("mise.toml.jinja"))
        (self.project / ".project.json").write_text(render_jinja(".project.json.jinja"))
        shutil.copy2(SCRIPT, self.project / ".mise/scripts/docs-sync.py")
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        (self.project / "docs").mkdir()
        (self.project / "docs/note.md").write_text("# Note\n")
        self.vault = Path(self.tmp.name) / "vault"
        self.vault.mkdir()

    def test_generated_task_syncs_end_to_end(self):
        env = {
            **os.environ,
            "MISE_TRUSTED_CONFIG_PATHS": str(self.project),
            "MISE_DATA_DIR": str(Path(self.tmp.name) / "mise-data"),
            "MISE_CACHE_DIR": str(Path(self.tmp.name) / "mise-cache"),
            "MISE_STATE_DIR": str(Path(self.tmp.name) / "mise-state"),
            "MISE_CONFIG_DIR": str(Path(self.tmp.name) / "mise-config"),
        }
        result = subprocess.run(
            ["mise", "run", "--cd", str(self.project), "docs:sync",
             "--vault", str(self.vault), "--no-open"],
            text=True, capture_output=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        index = next((self.vault / "Projects/fixture-app").iterdir()) / "_docs-sync/Index.md"
        self.assertIn("# Fixture App docs — ", index.read_text())
        self.assertIn("docs/note.md", index.read_text())


if __name__ == "__main__":
    unittest.main()
