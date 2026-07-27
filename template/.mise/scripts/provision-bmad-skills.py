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


def validate_skill_name(name: str) -> str:
    if not name or name in {".", ".."} or Path(name).is_absolute():
        raise ValueError(f"Unsafe BMAD skill name: {name!r}")
    if "/" in name or "\\" in name or Path(name).name != name:
        raise ValueError(f"BMAD skill name must be one path component: {name!r}")
    return name


def preflight_project_directory(project_root: Path, target: Path) -> None:
    try:
        relative = target.absolute().relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"Project destination escapes {project_root}: {target}") from error
    if len(relative.parts) > 2:
        raise ValueError(f"Unexpected project skill destination depth: {target}")
    current = project_root
    for part in relative.parts:
        current = current / part
        if not current.exists() and not current.is_symlink():
            break
        if current.is_symlink():
            raise ValueError(f"Refusing symlinked project skill directory: {current}")
        if not current.is_dir():
            raise ValueError(f"Project skill parent is not a directory: {current}")


def prepare_project_skill_dirs(project_root: Path) -> tuple[Path, Path]:
    agents_dir = project_root / ".agents"
    skills_dir = agents_dir / "skills"
    # Validate the complete existing chain before creating or mutating anything.
    preflight_project_directory(project_root, agents_dir)
    preflight_project_directory(project_root, skills_dir)
    agents_dir.mkdir(exist_ok=True)
    skills_dir.mkdir(exist_ok=True)
    for path in (agents_dir, skills_dir):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"Unsafe project skill directory: {path}")
        resolved = path.resolve(strict=True)
        resolved.relative_to(project_root)
    return agents_dir, skills_dir


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

    for path in pack_skills:
        validate_skill_name(path.name)

    project_root = Path.cwd().resolve(strict=True)
    agents_dir, skills_dir = prepare_project_skill_dirs(project_root)
    manifest_path = agents_dir / "skills.json"
    if manifest_path.is_symlink():
        raise ValueError(f"Refusing symlinked skills manifest: {manifest_path}")
    if manifest_path.exists() and not manifest_path.is_file():
        raise ValueError(f"Skills manifest is not a regular file: {manifest_path}")
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

    expected = {path.name: path for path in pack_skills}
    changed = 0
    for entry in skills_dir.iterdir():
        if entry.parent.resolve(strict=True) != skills_dir.resolve(strict=True):
            raise ValueError(f"BMAD skill entry escapes skills directory: {entry}")
        if entry.name.startswith("bmad-") and entry.name not in expected:
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            else:
                shutil.rmtree(entry)
            changed += 1
    for name, target in expected.items():
        link = skills_dir / validate_skill_name(name)
        if link.parent.resolve(strict=True) != skills_dir.resolve(strict=True):
            raise ValueError(f"BMAD skill destination escapes skills directory: {link}")
        changed += int(replace_with_symlink(link, target))

    print(
        f"bmad-skills: {len(pack_skills)} skills from pack "
        f"{BMAD_PACK_VERSION}; {changed} symlink(s) updated"
    )


if __name__ == "__main__":
    main()
