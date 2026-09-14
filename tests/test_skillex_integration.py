"""Exercise the rendered task with an installed Skillex package, never a clone import.

SKILLEX_TEST_TARBALL selects a prebuilt release candidate before npm publication.
The fixture installs it under /tmp and registers that prefix in an isolated mise.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"


def run(command, *, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)


def succeeded(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module")
def installed():
    with tempfile.TemporaryDirectory(
        prefix="commonproject-skillex-", dir="/tmp"
    ) as tmp:
        base = Path(tmp).resolve()
        node = Path(
            os.environ.get("SKILLEX_TEST_NODE_BIN") or shutil.which("node")
        ).resolve()
        npm = node.parent / "npm"
        mise = Path(shutil.which("mise")).resolve()
        copier = Path(shutil.which("copier"))
        prefix = base / "package"
        env = {
            "PATH": f"{node.parent}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(base / "install-home"),
            "npm_config_cache": str(base / "npm-cache"),
        }
        Path(env["HOME"]).mkdir()
        package = os.environ.get("SKILLEX_TEST_TARBALL", f"@delorenj/skillex@{VERSION}")
        succeeded(
            run(
                [
                    str(npm),
                    "install",
                    "--global",
                    "--prefix",
                    str(prefix),
                    "--ignore-scripts",
                    "--omit=dev",
                    "--no-audit",
                    "--no-fund",
                    package,
                ],
                cwd=base,
                env=env,
            )
        )
        cli = prefix / "bin/skillex"
        assert (
            succeeded(run([str(cli), "--version"], cwd=base, env=env)).stdout.strip()
            == VERSION
        )
        yield base, node, mise, copier, prefix


@pytest.fixture
def fixture(installed):
    base, node, mise, copier, prefix = installed
    with tempfile.TemporaryDirectory(prefix="case-", dir=base) as tmp:
        root = Path(tmp).resolve()
        home = root / "home"
        home.mkdir()
        (home / ".config/git").mkdir(parents=True)
        (home / ".config/git/ignore").write_text(
            "THIS-MACHINE-GLOBAL-RULE-MUST-NOT-BE-COPIED\n"
        )
        tools = root / "tools"
        tools.mkdir()
        for name, target in {"node": node, "mise": mise, "sh": Path("/bin/sh")}.items():
            (tools / name).symlink_to(target)
        registry = root / "catalog"
        for name in ("alpha", "beta"):
            skill = registry / "all-skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Fixture {name}\n---\n"
            )
        (home / ".agents").mkdir()
        global_manifest = home / ".agents/skills.json"
        global_manifest.write_text(json.dumps({"skills": [{"name": "alpha"}]}))
        env = {
            "PATH": f"{tools}{os.pathsep}{node.parent}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "MISE_DATA_DIR": str(root / "mise-data"),
            "MISE_CACHE_DIR": str(root / "mise-cache"),
            "MISE_CONFIG_DIR": str(root / "mise-config"),
            "PJ_SKILLS_REGISTRY_ROOT": str(registry),
        }
        succeeded(
            run(
                [str(mise), "link", f"npm:@delorenj/skillex@{VERSION}", str(prefix)],
                cwd=root,
                env=env,
            )
        )
        # Copy the current tracked template bytes, including pending edits, but
        # exclude unrelated untracked rendered files such as template/mise.toml.
        source = root / "template-source"
        tracked = (
            subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
        )
        for name in tracked:
            if name != "copier.yml" and not name.startswith("template/"):
                continue
            src = ROOT / name
            if not (src.is_file() or src.is_symlink()):
                continue
            dst = source / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
        yield {
            "root": root,
            "home": home,
            "tools": tools,
            "registry": registry,
            "env": env,
            "mise": mise,
            "copier": copier,
            "source": source,
            "global_bytes": global_manifest.read_bytes(),
        }


def render(fixture, *, hooks=False, project=None):
    project = project or fixture["root"] / "project with spaces"
    project.mkdir(exist_ok=True)
    (project / ".gitignore").write_text("# Existing project rule\nproject-cache/\n")
    result = run(
        [
            str(fixture["copier"]),
            "copy",
            "--trust",
            "--defaults",
            "--overwrite",
            "--data",
            "project_name=Fixture Project",
            "--data",
            f"agent_hooks_layer={str(hooks).lower()}",
            str(fixture["source"]),
            str(project),
        ],
        cwd=fixture["root"],
        env=fixture["env"],
    )
    succeeded(result)
    return project


def sync(fixture, project, *, cwd=None):
    # The task and actual installed CLI execute with no Python or uv available.
    env = dict(
        fixture["env"],
        PATH=str(fixture["tools"]),
        MISE_TRUSTED_CONFIG_PATHS=str(project / "mise.toml"),
    )
    assert shutil.which("python3", path=env["PATH"]) is None
    assert shutil.which("uv", path=env["PATH"]) is None
    return run(
        [str(fixture["mise"]), "run", "skills:sync"], cwd=cwd or project, env=env
    )


def snapshot(root):
    result = {}
    if not root.exists():
        return result
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            stat = path.lstat()
            value = (
                os.readlink(path)
                if path.is_symlink()
                else path.read_bytes()
                if path.is_file()
                else None
            )
            result[str(path.relative_to(root))] = (stat.st_ino, stat.st_mode, value)
    return result


def assert_task(config):
    tasks = config["tasks"]
    assert [name for name in tasks if name.startswith("skills:")] == ["skills:sync"]
    task = tasks["skills:sync"]
    assert task["tools"] == {"npm:@delorenj/skillex": VERSION}
    assert task["run"] == "skillex sync --scope project --project '{{config_root}}'"
    assert not task.get("depends")
    assert all(
        watch.get("task") != "skills:sync" for watch in config.get("watch_files", [])
    )
    assert all(
        "skillex" not in hook["script"]
        and "sync-skills" not in hook["script"]
        and "provision-packs" not in hook["script"]
        for hook in config["hooks"]["enter"]
    )


@pytest.mark.parametrize("hooks", [False, True])
def test_fresh_bootstrap_activates_project_only_and_preserves_other_hooks(
    fixture, hooks
):
    project = render(fixture, hooks=hooks)
    config = tomllib.loads((project / "mise.toml").read_text())
    assert_task(config)
    enter = "\n".join(hook["script"] for hook in config["hooks"]["enter"])
    for script in ("link-agentfiles.sh", "materialize-env.sh", "codegraph.sh"):
        assert script in enter
    assert (".agents/hooks/sync.py" in enter) is hooks
    assert (project / ".agents/hooks").exists() is hooks
    assert not (project / ".mise/scripts/sync-skills.py").exists()
    assert not (project / ".mise/scripts/provision-packs.py").exists()
    assert (project / ".agents/skills/alpha").resolve() == fixture[
        "registry"
    ] / "all-skills/alpha"
    for alias in (
        ".claude",
        ".codex",
        ".gemini",
        ".copilot",
        ".opencode",
        ".kimi-code",
    ):
        assert (project / alias / "skills/alpha/SKILL.md").is_file()
    assert not (fixture["home"] / ".agents/skills").exists()
    assert (fixture["home"] / ".agents/skills.json").read_bytes() == fixture[
        "global_bytes"
    ]
    assert not (project / ".env").exists(), (
        "bootstrap must not run the materialize-env enter hook"
    )
    assert "project-cache/\n" in (project / ".gitignore").read_text()
    ignore = (project / ".gitignore").read_text()
    assert "THIS-MACHINE-GLOBAL-RULE-MUST-NOT-BE-COPIED" not in ignore
    assert "\n/.agents/skills\n" in ignore and "\n!.env.op\n" in ignore
    assert (project / "CLAUDE.md").readlink() == Path("AGENTS.md")
    assert (project / "GEMINI.md").readlink() == Path("AGENTS.md")
    identity = json.loads((project / ".project.json").read_text())
    assert identity["repo_path"] == str(project)
    assert identity["project_name"] == "Fixture Project"
    assert identity["ticket_provider"]["type"] == "plane"
    assert not (project / ".plane.json").exists()


def test_nested_explicit_task_preserves_bmad_and_converges_without_python(fixture):
    project = render(fixture)
    manifest = project / ".agents/skills.json"
    manifest.write_text(json.dumps({"skills": [{"name": "beta"}]}))
    bmad = project / ".agents/skills/bmad-project-owned"
    bmad.mkdir()
    (bmad / "SKILL.md").write_text("installer-owned content\n")
    bmad_before = snapshot(bmad)
    nested = project / "nested/working directory"
    nested.mkdir(parents=True)
    succeeded(sync(fixture, project, cwd=nested))
    assert (project / ".agents/skills/beta").resolve() == fixture[
        "registry"
    ] / "all-skills/beta"
    assert (project / ".agents/skills/alpha").is_symlink()
    assert not (nested / ".agents").exists()
    assert snapshot(bmad) == bmad_before
    before = snapshot(project), snapshot(fixture["root"] / "state")
    succeeded(sync(fixture, project, cwd=nested))
    assert (snapshot(project), snapshot(fixture["root"] / "state")) == before
    assert not (fixture["home"] / ".agents/skills").exists()


def test_refresh_preserves_explicit_selection_bytes_and_prunes_only_owned(fixture):
    project = render(fixture)
    manifest = project / ".agents/skills.json"
    selection = b'{ "inherit_global": false, "skills": [{"name":"beta"}], "exclude": ["alpha"] }\n'
    manifest.write_bytes(selection)
    foreign = project / ".agents/skills/foreign"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("project skill\n")
    before = snapshot(foreign)
    render(fixture, project=project)
    assert manifest.read_bytes() == selection
    assert not (project / ".agents/skills/alpha").exists()
    assert (project / ".agents/skills/beta").is_symlink()
    assert snapshot(foreign) == before


def test_collision_refuses_without_changing_selection_or_skill_content(fixture):
    project = render(fixture)
    alias = project / ".codex/skills"
    alias.unlink()
    alias.mkdir()
    (alias / "local.txt").write_text("foreign alias directory\n")
    before = snapshot(project), snapshot(fixture["registry"])
    refused = sync(fixture, project)
    assert refused.returncode != 0
    assert "E_" in refused.stdout + refused.stderr
    assert (snapshot(project), snapshot(fixture["registry"])) == before


def test_root_dogfood_uses_the_same_explicit_task():
    assert_task(tomllib.loads((ROOT / "mise.toml").read_text()))
