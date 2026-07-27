#!/usr/bin/env python3
"""Provision project BMAD skills from the pinned Skillex pack."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


BMAD_PACK_VERSION = "6.10.2"
SKILLS_SCHEMA = "https://raw.githubusercontent.com/skillex/schemas/main/skills.schema.json"
SKILLS_REGISTRY = "https://github.com/delorenj/skillex.git"


def pack_root() -> Path:
    override = os.environ.get("PJ_BMAD_PACK_ROOT", "").strip()
    return (
        Path(override).expanduser()
        if override
        else Path.home() / "code" / "skillex" / "packs" / "bmad" / BMAD_PACK_VERSION
    ).resolve()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def is_bmad_entry(value: object) -> bool:
    if isinstance(value, str):
        return value.startswith("bmad-")
    if isinstance(value, dict):
        name = value.get("name")
        return isinstance(name, str) and name.startswith("bmad-")
    return False


def replace_with_symlink(link: Path, target: Path) -> bool:
    if link.is_symlink() and link.resolve(strict=False) == target:
        return False
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.exists():
        shutil.rmtree(link)
    link.symlink_to(target, target_is_directory=True)
    return True


def main() -> None:
    root = pack_root()
    if not root.is_dir():
        raise SystemExit(
            f"BMAD Skillex pack {BMAD_PACK_VERSION} not found at {root}; "
            "set PJ_BMAD_PACK_ROOT to the installed pack"
        )

    pack_skills = sorted(
        path.resolve()
        for path in root.iterdir()
        if path.is_dir() and path.name.startswith("bmad-")
    )
    if not pack_skills:
        raise SystemExit(f"BMAD Skillex pack contains no bmad-* skills: {root}")

    project_root = Path.cwd().resolve()
    manifest_path = project_root / ".agents" / "skills.json"
    manifest = load_manifest(manifest_path)
    existing = manifest.get("skills", [])
    if not isinstance(existing, list):
        raise ValueError(f"{manifest_path} skills must be an array")

    manifest["$schema"] = SKILLS_SCHEMA
    manifest["inherit_global"] = True
    manifest["registry"] = SKILLS_REGISTRY
    manifest["skills"] = [
        *[entry for entry in existing if not is_bmad_entry(entry)],
        *[{"name": path.name, "source": path.as_uri()} for path in pack_skills],
    ]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    next_manifest = json.dumps(manifest, indent=2) + "\n"
    if not manifest_path.exists() or manifest_path.read_text() != next_manifest:
        manifest_path.write_text(next_manifest)

    skills_dir = project_root / ".agents" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    expected = {path.name: path for path in pack_skills}
    changed = 0
    for entry in skills_dir.iterdir():
        if entry.name.startswith("bmad-") and entry.name not in expected:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            else:
                shutil.rmtree(entry)
            changed += 1
    for name, target in expected.items():
        changed += int(replace_with_symlink(skills_dir / name, target))

    print(
        f"bmad-skills: {len(pack_skills)} skills from pack "
        f"{BMAD_PACK_VERSION}; {changed} symlink(s) updated"
    )


if __name__ == "__main__":
    main()
