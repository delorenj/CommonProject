#!/usr/bin/env python3
"""
sync-skills.py — manifest-driven skill fanout.
Replaces the old symlink-based skillex monolithic fanout.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The list of agent CLI skill directories (relative to home or project root)
CLI_SKILL_DIRS = [
    ".gemini/skills",
    ".codex/skills",
    ".kimi/skills",
    ".augment/skills",
    ".config/opencode/skills",
    ".hermes/skills",
    ".claude/skills",
    ".openclaw/skills",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync skills from manifest to agent CLIs."
    )
    parser.add_argument(
        "--scope",
        choices=["global", "project"],
        required=True,
        help="Whether to sync global skills or project-local skills.",
    )
    return parser.parse_args()


def load_manifest(manifest_path):
    if not manifest_path.exists():
        return {"skills": []}
    with open(manifest_path, "r") as handle:
        return json.load(handle)


def ensure_cache_dir():
    cache_dir = Path(os.path.expanduser("~/.agents/.cache/skills"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def sync_registry(registry_url):
    # Sanitize registry_url to create a folder name
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", registry_url)
    cache_dir = (
        Path(os.path.expanduser("~/.agents/.cache/registries")) / safe_name
    )

    if cache_dir.exists():
        try:
            print(f"Updating registry {registry_url}...")
            subprocess.run(
                ["git", "-C", str(cache_dir), "pull"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as error:
            print(
                f"Warning: Failed to update registry {registry_url}: "
                f"{error.stderr.decode()}",
                file=sys.stderr,
            )
    else:
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning registry {registry_url}...")
        subprocess.run(["git", "clone", registry_url, str(cache_dir)], check=True)

    return cache_dir


def sync_git_skill(name, source, version, cache_dir):
    target_dir = cache_dir / name
    if target_dir.exists():
        # Just pull if it exists
        try:
            print(f"Updating git skill {name} in cache...")
            subprocess.run(
                ["git", "-C", str(target_dir), "pull"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as error:
            print(
                f"Warning: Failed to update {name}: {error.stderr.decode()}",
                file=sys.stderr,
            )
    else:
        print(f"Cloning git skill {name} to cache...")
        subprocess.run(["git", "clone", source, str(target_dir)], check=True)

    if version:
        subprocess.run(
            ["git", "-C", str(target_dir), "checkout", version], check=True
        )

    return target_dir


def resolve_skill_path(
    skill, cache_dir, base_dir, default_registry, registry_cache
):
    if isinstance(skill, str):
        path = skill if "/" in skill else f"all-skills/{skill}"
        name = path.split("/")[-1]
        skill = {"name": name, "registry_path": path}

    name = skill.get("name")

    if "registry_path" in skill:
        registry_url = skill.get("registry", default_registry)
        if registry_url not in registry_cache:
            registry_cache[registry_url] = sync_registry(registry_url)
        full_path = registry_cache[registry_url] / skill["registry_path"]
        if not full_path.exists():
            print(
                f"Warning: Registry skill {name} not found at {full_path}",
                file=sys.stderr,
            )
            return name, None
        return name, full_path

    source = skill.get("source", "")
    if source.startswith("git@") or source.startswith("https://"):
        return name, sync_git_skill(
            name, source, skill.get("version"), cache_dir
        )
    if source.startswith("file://"):
        local_path = source[len("file://") :]
        # Resolve relative paths against the directory of the manifest
        full_path = (base_dir / local_path).resolve()
        if not full_path.exists():
            print(
                f"Warning: Local skill {name} not found at {full_path}",
                file=sys.stderr,
            )
            return name, None
        return name, full_path

    print(
        f"Warning: Unknown source type for skill {name}: {source}",
        file=sys.stderr,
    )
    return name, None


def fanout_to_cli(cli_dirs_base, skills_map):
    """
    Creates symlinks in each of the CLI_SKILL_DIRS relative to cli_dirs_base
    pointing to the resolved paths in skills_map.
    """
    linked_total = 0
    for cli_rel_path in CLI_SKILL_DIRS:
        cli_dir = cli_dirs_base / cli_rel_path

        # Only fan out if the parent config directory exists
        # (e.g. only create .gemini/skills if .gemini exists)
        if not cli_dir.parent.exists():
            continue

        cli_dir.mkdir(parents=True, exist_ok=True)

        for name, actual_path in skills_map.items():
            symlink_target = cli_dir / name

            # If it's a symlink already pointing to the right place, skip
            if (
                symlink_target.is_symlink()
                and os.readlink(symlink_target) == str(actual_path)
            ):
                continue

            # If it exists but is wrong, remove it
            if symlink_target.exists() or symlink_target.is_symlink():
                if symlink_target.is_dir() and not symlink_target.is_symlink():
                    shutil.rmtree(symlink_target)
                else:
                    symlink_target.unlink()

            os.symlink(actual_path, symlink_target)
            linked_total += 1
            print(f"→ {symlink_target} -> {actual_path}")

    print(
        f"sync-skills: {linked_total} new/updated symlink(s) "
        f"across CLIs in {cli_dirs_base}"
    )


def main():
    args = parse_args()
    cache_dir = ensure_cache_dir()

    global_manifest_path = Path(os.path.expanduser("~/.agents/skills.json"))
    project_manifest_path = Path(os.getcwd()) / ".agents" / "skills.json"

    skills_to_sync = {}  # name -> actual_path
    registry_cache = {}

    if args.scope == "global":
        print(f"Loading global manifest from {global_manifest_path}")
        manifest = load_manifest(global_manifest_path)
        default_registry = manifest.get(
            "registry", "https://github.com/delorenj/skillex.git"
        )
        base_dir = global_manifest_path.parent
        for skill in manifest.get("skills", []):
            name, path = resolve_skill_path(
                skill,
                cache_dir,
                base_dir,
                default_registry,
                registry_cache,
            )
            if path:
                skills_to_sync[name] = path

        # Fanout globally (home dir)
        fanout_to_cli(Path(os.path.expanduser("~")), skills_to_sync)

    elif args.scope == "project":
        print(f"Loading project manifest from {project_manifest_path}")
        manifest = load_manifest(project_manifest_path)
        default_registry = manifest.get(
            "registry", "https://github.com/delorenj/skillex.git"
        )

        # Check if we should inherit global skills
        if manifest.get("inherit_global", False):
            print("Inheriting global skills...")
            global_manifest = load_manifest(global_manifest_path)
            global_registry = global_manifest.get(
                "registry", "https://github.com/delorenj/skillex.git"
            )
            for skill in global_manifest.get("skills", []):
                name, path = resolve_skill_path(
                    skill,
                    cache_dir,
                    global_manifest_path.parent,
                    global_registry,
                    registry_cache,
                )
                if path:
                    skills_to_sync[name] = path

        base_dir = project_manifest_path.parent
        for skill in manifest.get("skills", []):
            name, path = resolve_skill_path(
                skill,
                cache_dir,
                base_dir,
                default_registry,
                registry_cache,
            )
            if path:
                # Overrides global skill of the same name
                skills_to_sync[name] = path

        # Fanout locally (project dir)
        fanout_to_cli(Path(os.getcwd()), skills_to_sync)


if __name__ == "__main__":
    main()
