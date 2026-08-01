#!/usr/bin/env python3
"""Provision project BMAD skills from the pinned Skillex pack."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


BMAD_PACK_VERSION = "6.10.1-next.31"
BMAD_PACK_CHECKSUMS_SHA256 = "a8bc005612ac60e3ec775fff5a11eafe38be6acdae96efa3d770b48322cb3224"
BMAD_PACK_SKILL_COUNT = 76
BMAD_PACK_PAYLOAD_FILES = 1072
SKILLS_SCHEMA = "https://raw.githubusercontent.com/skillex/schemas/main/skills.schema.json"
SKILLS_REGISTRY = "https://github.com/delorenj/skillex.git"


def pack_root() -> Path:
    override = os.environ.get("PJ_BMAD_PACK_ROOT", "").strip()
    return (
        Path(override).expanduser()
        if override
        else Path.home() / "code" / "skillex" / "packs" / "bmad" / BMAD_PACK_VERSION
    ).absolute()


def read_regular_file(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"BMAD pack entry is not a regular file: {path}")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def safe_checksum_path(value: str) -> Path:
    path = Path(value)
    if not value or "\\" in value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe BMAD checksum path: {value!r}")
    return path


def walk_regular_tree(root: Path) -> tuple[dict[str, bytes], set[str]]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()

    def visit(directory: Path) -> None:
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            path = Path(entry.path)
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"BMAD pack may not contain symlinks: {path}")
            if stat.S_ISDIR(mode):
                directories.add(path.relative_to(root).as_posix())
                visit(path)
            elif stat.S_ISREG(mode):
                files[path.relative_to(root).as_posix()] = read_regular_file(path)
            else:
                raise ValueError(f"BMAD pack may contain only regular files/directories: {path}")

    visit(root)
    return files, directories


def validate_trusted_pack(root: Path) -> list[Path]:
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ValueError(f"BMAD pack root must be a real directory: {root}")

    checksum_bytes = read_regular_file(root / "SHA256SUMS")
    if hashlib.sha256(checksum_bytes).hexdigest() != BMAD_PACK_CHECKSUMS_SHA256:
        raise ValueError(
            f"BMAD pack checksum manifest is not the trusted {BMAD_PACK_VERSION} manifest"
        )
    expected: dict[str, str] = {}
    for line in checksum_bytes.decode("utf-8").splitlines():
        digest, separator, value = line.partition("  ")
        if separator != "  " or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"Invalid BMAD SHA256SUMS entry: {line}")
        relative = safe_checksum_path(value).as_posix()
        if relative in expected:
            raise ValueError(f"Duplicate BMAD SHA256SUMS entry: {relative}")
        expected[relative] = digest

    actual, directories = walk_regular_tree(root)
    actual.pop("SHA256SUMS", None)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise ValueError(f"BMAD checksum coverage mismatch; missing={missing} extra={extra}")
    for relative, digest in expected.items():
        if hashlib.sha256(actual[relative]).hexdigest() != digest:
            raise ValueError(f"BMAD pack digest mismatch: {relative}")
    for directory in directories:
        if not any(relative.startswith(f"{directory}/") for relative in actual):
            raise ValueError(
                f"BMAD pack contains an unauthenticated empty directory: {directory}"
            )

    metadata = tomllib.loads(actual["pack.toml"].decode("utf-8"))
    pack = metadata.get("pack", {})
    source = metadata.get("source", {})
    freeform = metadata.get("freeform", {})
    policy = metadata.get("policy", {})
    if (
        pack.get("name") != "bmad"
        or pack.get("version") != BMAD_PACK_VERSION
        or source.get("upstream") != "bmad-method"
        or source.get("upstream_version") != BMAD_PACK_VERSION
        or source.get("rendered_from") != ".agent/skills"
        or policy.get("immutable") is not True
        or policy.get("project_projection") != "symlink"
    ):
        raise ValueError(f"BMAD pack.toml does not declare the trusted {BMAD_PACK_VERSION} contract")
    skill_names = freeform.get("skills")
    payload_files = source.get("payload_files")
    if (
        not isinstance(skill_names, list)
        or not all(isinstance(name, str) for name in skill_names)
        or len(skill_names) != BMAD_PACK_SKILL_COUNT
        or len(set(skill_names)) != len(skill_names)
    ):
        raise ValueError(f"BMAD pack.toml must declare exactly {BMAD_PACK_SKILL_COUNT} unique skills")
    if payload_files != BMAD_PACK_PAYLOAD_FILES:
        raise ValueError(f"BMAD pack.toml must declare exactly {BMAD_PACK_PAYLOAD_FILES} payload files")
    for name in skill_names:
        if not name.startswith("bmad-"):
            raise ValueError(f"Unsafe BMAD skill identity: {name!r}")
        validate_skill_name(name)

    top_level_directories = sorted(
        entry.name for entry in os.scandir(root) if stat.S_ISDIR(entry.stat(follow_symlinks=False).st_mode)
    )
    if top_level_directories != sorted(skill_names):
        raise ValueError("BMAD pack directory inventory differs from authenticated pack.toml skills")
    for name in skill_names:
        skill_md = root / name / "SKILL.md"
        if not stat.S_ISREG(skill_md.lstat().st_mode):
            raise ValueError(f"BMAD skill is missing a regular SKILL.md: {name}")
    skill_set = set(skill_names)
    payload_count = sum(1 for relative in actual if relative.split("/", 1)[0] in skill_set)
    if payload_count != payload_files:
        raise ValueError(f"BMAD payload inventory mismatch: {payload_count} != {payload_files}")
    return [root / name for name in skill_names]


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


def lexical_link_target(link: Path) -> Path | None:
    if not link.is_symlink():
        return None
    target = Path(os.readlink(link))
    return (target if target.is_absolute() else link.parent / target).absolute()


def remove_entry(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def provision(
    *,
    after_preflight: Callable[[], None] | None = None,
    create_link: Callable[[Path, Path, int], None] | None = None,
) -> int:
    root = pack_root()
    pack_skills = validate_trusted_pack(root)
    if after_preflight is not None:
        after_preflight()

    project_root = Path.cwd().resolve(strict=True)
    agents_path = project_root / ".agents"
    skills_path = agents_path / "skills"
    agents_existed = agents_path.exists() or agents_path.is_symlink()
    skills_existed = skills_path.exists() or skills_path.is_symlink()
    agents_dir, skills_dir = prepare_project_skill_dirs(project_root)
    manifest_path = agents_dir / "skills.json"
    if manifest_path.is_symlink():
        raise ValueError(f"Refusing symlinked skills manifest: {manifest_path}")
    if manifest_path.exists() and not manifest_path.is_file():
        raise ValueError(f"Skills manifest is not a regular file: {manifest_path}")
    manifest_existed = manifest_path.exists()
    manifest_bytes = read_regular_file(manifest_path) if manifest_existed else None
    manifest_mode = stat.S_IMODE(manifest_path.lstat().st_mode) if manifest_existed else 0o644
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
    next_manifest = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    expected = {path.name: path for path in pack_skills}
    affected: list[str] = []
    for entry in skills_dir.iterdir():
        if entry.parent.resolve(strict=True) != skills_dir.resolve(strict=True):
            raise ValueError(f"BMAD skill entry escapes skills directory: {entry}")
        if entry.name.startswith("bmad-"):
            validate_skill_name(entry.name)
            target = expected.get(entry.name)
            if target is None or lexical_link_target(entry) != target:
                affected.append(entry.name)
    for name, target in expected.items():
        link = skills_dir / validate_skill_name(name)
        if link.parent.resolve(strict=True) != skills_dir.resolve(strict=True):
            raise ValueError(f"BMAD skill destination escapes skills directory: {link}")
        if lexical_link_target(link) != target and name not in affected:
            affected.append(name)

    manifest_changed = manifest_bytes != next_manifest
    if not affected and not manifest_changed:
        validate_trusted_pack(root)
        return 0

    transaction = Path(tempfile.mkdtemp(prefix=".bmad-transaction-", dir=agents_dir))
    backup = transaction / "entries"
    backup.mkdir()
    moved: list[str] = []
    created: list[str] = []

    def rollback() -> None:
        errors: list[str] = []
        for name in reversed(created):
            try:
                remove_entry(skills_dir / name)
            except OSError as error:
                errors.append(f"remove {name}: {error}")
        for name in reversed(moved):
            try:
                remove_entry(skills_dir / name)
                os.replace(backup / name, skills_dir / name)
            except OSError as error:
                errors.append(f"restore {name}: {error}")
        try:
            if manifest_bytes is None:
                remove_entry(manifest_path)
            else:
                atomic_write(manifest_path, manifest_bytes, manifest_mode)
        except OSError as error:
            errors.append(f"restore manifest: {error}")
        shutil.rmtree(transaction, ignore_errors=True)
        try:
            if not skills_existed and skills_dir.exists() and not any(skills_dir.iterdir()):
                skills_dir.rmdir()
            if not agents_existed and agents_dir.exists() and not any(agents_dir.iterdir()):
                agents_dir.rmdir()
        except OSError as error:
            errors.append(f"remove created directories: {error}")
        if errors:
            raise RuntimeError("BMAD rollback was incomplete: " + "; ".join(errors))

    link_creator = create_link or (
        lambda target, link, _index: link.symlink_to(target, target_is_directory=True)
    )
    try:
        for name in affected:
            entry = skills_dir / name
            if entry.exists() or entry.is_symlink():
                os.replace(entry, backup / name)
                moved.append(name)
        for index, (name, target) in enumerate(expected.items(), start=1):
            link = skills_dir / name
            if lexical_link_target(link) == target:
                continue
            link_creator(target, link, index)
            created.append(name)
        if manifest_changed:
            atomic_write(manifest_path, next_manifest, manifest_mode)
        postflight = validate_trusted_pack(root)
        if [path.name for path in postflight] != list(expected):
            raise ValueError("BMAD pack inventory changed after preflight")
    except Exception as error:
        try:
            rollback()
        except Exception as rollback_error:
            raise RuntimeError(f"BMAD provisioning failed ({error}); {rollback_error}") from error
        raise

    shutil.rmtree(transaction)
    return len(affected)


def main() -> None:
    try:
        changed = provision()
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
        raise SystemExit(
            f"BMAD Skillex pack {BMAD_PACK_VERSION} provisioning failed: {error}; "
            "set PJ_BMAD_PACK_ROOT to the installed canonical pack"
        ) from error

    print(
        f"bmad-skills: {BMAD_PACK_SKILL_COUNT} skills from pack "
        f"{BMAD_PACK_VERSION}; {changed} symlink(s) updated"
    )


if __name__ == "__main__":
    main()
