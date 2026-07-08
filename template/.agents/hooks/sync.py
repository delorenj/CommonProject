#!/usr/bin/env python3
"""
sync.py — project-scoped agent-hooks fan-out engine for CoachingAgentFramework.

ONE source of truth (`hooks.master.json`) is propagated to each agent CLI's
native hook-config dialect. This is the /ssot-fanout pattern, right-sized for a
handful of hooks: the master is the only hand-edited artifact; every per-agent
config is GENERATED and idempotent (re-running with an unchanged master writes
zero bytes).

Targets (v1):
  - claude : the repo's committed `.claude/settings.json` `hooks` key
             (uses $CLAUDE_PROJECT_DIR; all devs get it with no bootstrap)
  - codex  : injected into the per-user `~/.codex/hooks.json` on enter,
             removed on leave (absolute paths; no project-scoped codex file exists)
  - hermes : STUB — bindings are printed only (payload adaptation deferred)

Commands:
  --install     Regenerate claude settings + inject codex hooks (mise `enter`).
  --uninstall   Remove the codex injection (mise `leave`). Claude's committed
                settings are left in place.
  --check       Read-only drift gate: nonzero exit if the committed claude
                settings don't match the master, or (if codex is installed) the
                codex injection is missing/stale. For CI.
  --quiet       Suppress normal output (errors still print to stderr).

Env:
  CAF_HOOKS_SKIP_CODEX=1   Skip the codex target entirely.

install/uninstall never hard-fail the shell (exit 0 on internal error, warn to
stderr); --check returns nonzero on drift so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent          # <repo>/.agents/hooks
REPO_ROOT = HOOK_DIR.parent.parent                   # <repo>
MASTER = HOOK_DIR / "hooks.master.json"

QUIET = False


def log(msg: str) -> None:
    if not QUIET:
        print(msg)


def warn(msg: str) -> None:
    print(f"[caf-hooks] {msg}", file=sys.stderr)


def load_master() -> dict:
    with MASTER.open() as fh:
        return json.load(fh)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_local() -> dict:
    """Per-dev overrides from .agents/local.json (gitignored). Fails open.

    Note: individual disabled HOOKS are enforced at RUNTIME by lib/hook-guard.sh
    (so even Claude's committed hooks honor them); this only needs disabled
    AGENTS, which gate install. CAF_HOOKS_SKIP_CODEX=1 is an env shortcut.

    `defer_to_global` (under either `hooks` or `skills`) means "I already run
    these hooks from a global agent system" — so the shared per-user injections
    (codex/kimi/hermes) are suppressed and actively removed. Claude's committed
    repo settings are harmless and left in place.
    """
    disabled_agents: set[str] = set()
    defer_to_global = False
    p = REPO_ROOT / ".agents" / "local.json"
    if p.exists():
        try:
            data = json.loads(p.read_text() or "{}")
            hooks_cfg = data.get("hooks") or {}
            skills_cfg = data.get("skills") or {}
            disabled_agents = set(hooks_cfg.get("disabled_agents") or [])
            defer_to_global = bool(hooks_cfg.get("defer_to_global")) or bool(skills_cfg.get("defer_to_global"))
        except (json.JSONDecodeError, OSError) as exc:
            warn(f"ignoring malformed .agents/local.json: {exc}")
    if os.environ.get("CAF_HOOKS_SKIP_CODEX") == "1":
        disabled_agents.add("codex")
    if defer_to_global:
        disabled_agents.update({"codex", "kimi", "hermes"})
    return {"disabled_agents": disabled_agents}


# --------------------------------------------------------------------------- #
# Shared: turn the master into per-event hook groups for a given agent.
# Returns {event_name: [ {matcher?, hooks:[{type,command,timeout}]} ]}.
# Hooks sharing an event + matcher are merged into one group (Claude/Codex shape).
# --------------------------------------------------------------------------- #
def build_event_groups(master: dict, agent_key: str) -> dict:
    agent = master["agents"][agent_key]
    base_dir = agent["base_dir"].replace("{repo}", str(REPO_ROOT))
    unit = agent.get("timeout_unit", "s")
    ev_map = agent["lifecycle_events"]

    # Preserve master order; bucket by (event, matcher).
    buckets: "dict[tuple[str, str | None], list[dict]]" = {}
    order: list[tuple[str, str | None]] = []

    for hook in master["hooks"]:
        lifecycle = hook["lifecycle"]
        event = ev_map.get(lifecycle)
        if not event:  # this agent doesn't map this lifecycle (e.g. hermes stub)
            continue
        matcher = hook.get("matcher")
        timeout = hook["timeout_s"] * (1000 if unit == "ms" else 1)
        # Guard wrapper => per-dev runtime opt-out via .agents/local.json. The
        # guard execs the real script (stdin passes through) unless the hook id
        # is disabled, in which case it exits 0 silently (no error noise).
        command = f"{base_dir}/lib/hook-guard.sh {hook['id']} {base_dir}/{hook['script']}"
        key = (event, matcher)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(
            {"type": "command", "command": command, "timeout": timeout}
        )

    groups: dict[str, list[dict]] = {}
    for (event, matcher) in order:
        group: dict = {}
        if matcher is not None:
            group["matcher"] = matcher
        group["hooks"] = buckets[(event, matcher)]
        groups.setdefault(event, []).append(group)
    return groups


# --------------------------------------------------------------------------- #
# Claude dialect: own the `hooks` key of the committed .claude/settings.json.
# --------------------------------------------------------------------------- #
def render_claude(master: dict) -> dict:
    target = REPO_ROOT / master["agents"]["claude"]["config_target"]
    settings = {}
    if target.exists():
        try:
            settings = json.loads(target.read_text() or "{}")
        except json.JSONDecodeError:
            warn(f"{target} is not valid JSON; refusing to overwrite")
            return {"target": target, "changed": False, "error": True}
    settings["hooks"] = build_event_groups(master, "claude")
    return {"target": target, "settings": settings, "changed": True}


def claude_serialized(master: dict) -> str | None:
    r = render_claude(master)
    if r.get("error"):
        return None
    return json.dumps(r["settings"], indent=2) + "\n"


def install_claude(master: dict) -> None:
    target = REPO_ROOT / master["agents"]["claude"]["config_target"]
    desired = claude_serialized(master)
    if desired is None:
        return
    current = target.read_text() if target.exists() else None
    if current == desired:
        log(f"claude: up to date ({target.relative_to(REPO_ROOT)})")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(desired)
    log(f"claude: wrote {target.relative_to(REPO_ROOT)}")


# --------------------------------------------------------------------------- #
# Codex dialect: inject/remove absolute-path entries in ~/.codex/hooks.json.
# Our entries are identified by the command containing the repo marker path.
# --------------------------------------------------------------------------- #
def codex_target(master: dict) -> Path:
    return Path(os.path.expanduser(master["agents"]["codex"]["config_target"]))


def codex_marker() -> str:
    return f"{REPO_ROOT}/.agents/hooks/"


def _strip_caf_hooks(hooks_obj: dict, marker: str) -> bool:
    """Remove our hooks from every event; drop emptied groups. Returns changed."""
    changed = False
    for event, groups in list(hooks_obj.items()):
        new_groups = []
        for group in groups:
            kept = [h for h in group.get("hooks", []) if marker not in h.get("command", "")]
            if len(kept) != len(group.get("hooks", [])):
                changed = True
            if kept:
                g = dict(group)
                g["hooks"] = kept
                new_groups.append(g)
            elif not group.get("hooks"):
                new_groups.append(group)  # preserve foreign empty groups untouched
        if new_groups:
            hooks_obj[event] = new_groups
        else:
            del hooks_obj[event]
            changed = True
    return changed


def _codex_load(target: Path) -> dict:
    if target.exists():
        try:
            return json.loads(target.read_text() or "{}")
        except json.JSONDecodeError:
            warn(f"{target} is not valid JSON; skipping codex")
            return {"__error__": True}
    return {"hooks": {}}


def install_codex(master: dict) -> None:
    if os.environ.get("CAF_HOOKS_SKIP_CODEX") == "1":
        log("codex: skipped (CAF_HOOKS_SKIP_CODEX=1)")
        return
    target = codex_target(master)
    if not target.parent.exists():
        log("codex: ~/.codex not present, skipping")
        return
    data = _codex_load(target)
    if data.get("__error__"):
        return
    hooks_obj = data.setdefault("hooks", {})
    marker = codex_marker()

    # Idempotent: remove any prior CAF entries, then append fresh ones.
    _strip_caf_hooks(hooks_obj, marker)
    desired = build_event_groups(master, "codex")
    for event, groups in desired.items():
        hooks_obj.setdefault(event, [])
        hooks_obj[event].extend(groups)

    serialized = json.dumps(data, indent=2) + "\n"
    if target.exists() and target.read_text() == serialized:
        log(f"codex: up to date ({target})")
        return
    backup = target.with_suffix(target.suffix + ".caf-bak")
    if target.exists() and not backup.exists():
        backup.write_text(target.read_text())
        log(f"codex: backed up -> {backup}")
    target.write_text(serialized)
    log(f"codex: injected project hooks into {target}")


def uninstall_codex(master: dict) -> None:
    target = codex_target(master)
    if not target.exists():
        return
    data = _codex_load(target)
    if data.get("__error__"):
        return
    hooks_obj = data.get("hooks", {})
    if _strip_caf_hooks(hooks_obj, codex_marker()):
        data["hooks"] = hooks_obj
        target.write_text(json.dumps(data, indent=2) + "\n")
        log(f"codex: removed project hooks from {target}")
    else:
        log("codex: nothing to remove")


# --------------------------------------------------------------------------- #
# Kimi dialect: a sentinel-bounded [[hooks]] block in ~/.kimi-code/config.toml.
# Kimi runs hooks shell:true with the payload JSON on stdin and uses Claude-
# identical events + payload (incl. .prompt / .tool_input), so it reuses the SAME
# guard-wrapped scripts as claude/codex. Pure-text injection — no TOML library,
# preserves the rest of config.toml byte-for-byte, fully reversible.
# --------------------------------------------------------------------------- #
def kimi_target(master: dict) -> Path:
    agent = master["agents"]["kimi"]
    home = os.environ.get(agent.get("config_home_env") or "")
    if home:
        return Path(home) / "config.toml"
    return Path(os.path.expanduser(agent["config_target"]))


def _kimi_markers(master: dict) -> tuple[str, str]:
    name = REPO_ROOT.name
    return (
        f"# >>> {master['marker']} BEGIN ({name}) — generated by .agents/hooks/sync.py; do not edit",
        f"# <<< {master['marker']} END ({name})",
    )


def kimi_block(master: dict) -> str:
    agent = master["agents"]["kimi"]
    base = agent["base_dir"].replace("{repo}", str(REPO_ROOT))
    unit = agent.get("timeout_unit", "s")
    ev = agent["lifecycle_events"]
    begin, end = _kimi_markers(master)
    lines = [begin]
    for hook in master["hooks"]:
        event = ev.get(hook["lifecycle"])
        if not event:
            continue
        timeout = hook["timeout_s"] * (1000 if unit == "ms" else 1)
        # Guard wrapper => per-dev opt-out; shell:true so the two-path command works.
        cmd = f"{base}/lib/hook-guard.sh {hook['id']} {base}/{hook['script']}"
        lines.append("[[hooks]]")
        lines.append(f'event = "{event}"')
        if hook.get("matcher"):
            lines.append(f'matcher = "{hook["matcher"]}"')
        lines.append(f'command = "{cmd}"')  # paths have no quotes/backslashes -> safe TOML string
        lines.append(f"timeout = {timeout}")
        lines.append("")
    lines.append(end)
    return "\n".join(lines) + "\n"


def _strip_kimi_block(text: str, master: dict) -> tuple[str, bool]:
    # Removes exactly the one "\n" separator install prepends + our block + its
    # trailing newline, leaving the rest of the file byte-for-byte intact.
    begin, end = _kimi_markers(master)
    pattern = re.compile(r"\n" + re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    new, n = pattern.subn("", text)
    return new, n > 0


def install_kimi(master: dict) -> None:
    target = kimi_target(master)
    if not target.parent.exists():
        log("kimi: ~/.kimi-code not present, skipping")
        return
    text = target.read_text() if target.exists() else ""
    body, _ = _strip_kimi_block(text, master)  # work against config minus our block
    # Refuse if a foreign hooks definition exists (would collide with [[hooks]]).
    if re.search(r"(?m)^\s*hooks\s*=\s*\[[^\]]", body) or re.search(r"(?m)^\s*\[\[hooks\]\]", body):
        warn("kimi: existing non-CAF hooks found in config.toml; skipping to avoid a TOML conflict")
        return
    body = re.sub(r"(?m)^\s*hooks\s*=\s*\[\s*\]\s*\n", "", body)  # drop an empty `hooks = []`
    if body and not body.endswith("\n"):
        body += "\n"
    # Append "\n" + block (block ends with "\n"); the lone "\n" is what strip removes,
    # so the body above is preserved verbatim on uninstall.
    new = body + "\n" + kimi_block(master)
    if text == new:
        log(f"kimi: up to date ({target})")
        return
    backup = target.with_suffix(target.suffix + ".caf-bak")
    if target.exists() and not backup.exists():
        backup.write_text(text)
        log(f"kimi: backed up -> {backup}")
    target.write_text(new)
    log(f"kimi: injected project hooks into {target}")


def uninstall_kimi(master: dict) -> None:
    target = kimi_target(master)
    if not target.exists():
        return
    text = target.read_text()
    new, changed = _strip_kimi_block(text, master)
    if changed:
        target.write_text(new if new.endswith("\n") else new + "\n")
        log(f"kimi: removed project hooks from {target}")
    else:
        log("kimi: nothing to remove")


# --------------------------------------------------------------------------- #
# Hermes dialect: merge the adapter into the per-deployment runtime config.yaml
# + shell-hooks-allowlist.json. Hermes runs hooks shell=False with the payload
# on stdin, so it uses the ADAPTER (hermes/hindsight-hook.sh <event>), not the
# Claude-shaped scripts. Our entries are tagged by the repo marker in the command.
# --------------------------------------------------------------------------- #
def hermes_commands(master: dict) -> list[tuple[str, str, int]]:
    h = master["agents"]["hermes"]
    runner = h["runner"].replace("{repo}", str(REPO_ROOT))
    timeout = h.get("timeout_s", 5)
    return [
        (event, f"{runner} {event}", timeout)
        for _lifecycle, event in h["lifecycle_events"].items()
    ]


def _backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".caf-bak")
    if path.exists() and not backup.exists():
        backup.write_text(path.read_text())
        log(f"hermes: backed up -> {backup.name}")


def _load_yaml(path: Path):
    import yaml  # lazy: only hermes needs it
    return yaml.safe_load(path.read_text()) or {}


def install_hermes(master: dict) -> None:
    h = master["agents"]["hermes"]
    cfg = REPO_ROOT / h["config_target"]
    allow = REPO_ROOT / h["allowlist_target"]
    if not cfg.exists():
        log("hermes: runtime config.yaml not present, skipping")
        return
    try:
        import yaml
    except ImportError:
        warn("hermes: pyyaml not available, skipping (pip install pyyaml)")
        return
    marker = codex_marker()
    cmds = hermes_commands(master)

    # --- config.yaml hooks block ---
    try:
        data = _load_yaml(cfg)
    except Exception as exc:  # noqa: BLE001
        warn(f"hermes: could not parse {cfg}: {exc}")
        return
    hooks = data.setdefault("hooks", {})
    cfg_changed = False
    for event, command, timeout in cmds:
        entries = hooks.setdefault(event, [])
        ours = [e for e in entries if marker in e.get("command", "")]
        if not ours:
            entries.append({"command": command, "timeout": timeout})
            cfg_changed = True
        elif ours[0].get("command") != command:  # drifted -> refresh
            ours[0]["command"] = command
            ours[0]["timeout"] = timeout
            cfg_changed = True

    # --- shell-hooks-allowlist.json (pre-approve so Hermes won't prompt) ---
    allow_data = {"approvals": []}
    if allow.exists():
        try:
            allow_data = json.loads(allow.read_text() or '{"approvals": []}')
        except json.JSONDecodeError:
            allow_data = {"approvals": []}
    approvals = allow_data.setdefault("approvals", [])
    allow_changed = False
    for event, command, _timeout in cmds:
        if not any(a.get("command") == command and a.get("event") == event for a in approvals):
            approvals.append({
                "approved_at": _now_iso(),
                "approved_by": master["marker"],
                "command": command,
                "event": event,
            })
            allow_changed = True

    if cfg_changed:
        _backup_once(cfg)
        cfg.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True))
        log(f"hermes: merged adapter into {cfg.relative_to(REPO_ROOT)}")
    else:
        log("hermes: config.yaml up to date")
    if allow_changed:
        _backup_once(allow)
        allow.write_text(json.dumps(allow_data, indent=2) + "\n")
        log(f"hermes: pre-approved adapter in {allow.relative_to(REPO_ROOT)}")


def uninstall_hermes(master: dict) -> None:
    h = master["agents"]["hermes"]
    cfg = REPO_ROOT / h["config_target"]
    allow = REPO_ROOT / h["allowlist_target"]
    marker = codex_marker()
    try:
        import yaml
    except ImportError:
        return
    if cfg.exists():
        try:
            data = _load_yaml(cfg)
        except Exception:  # noqa: BLE001
            data = None
        if data and isinstance(data.get("hooks"), dict):
            changed = False
            for event, entries in list(data["hooks"].items()):
                kept = [e for e in entries if marker not in e.get("command", "")]
                if len(kept) != len(entries):
                    changed = True
                if kept:
                    data["hooks"][event] = kept
                else:
                    del data["hooks"][event]
            if changed:
                cfg.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True))
                log(f"hermes: removed adapter from {cfg.relative_to(REPO_ROOT)}")
    if allow.exists():
        try:
            allow_data = json.loads(allow.read_text() or '{"approvals": []}')
        except json.JSONDecodeError:
            allow_data = None
        if allow_data and isinstance(allow_data.get("approvals"), list):
            kept = [a for a in allow_data["approvals"] if marker not in a.get("command", "")]
            if len(kept) != len(allow_data["approvals"]):
                allow_data["approvals"] = kept
                allow.write_text(json.dumps(allow_data, indent=2) + "\n")
                log(f"hermes: removed adapter approvals from {allow.relative_to(REPO_ROOT)}")


# --------------------------------------------------------------------------- #
# Check (drift gate)
# --------------------------------------------------------------------------- #
def cmd_check(master: dict) -> int:
    rc = 0
    # Claude: committed settings must match the master.
    target = REPO_ROOT / master["agents"]["claude"]["config_target"]
    desired = claude_serialized(master)
    if desired is None:
        rc = 1
    else:
        current = target.read_text() if target.exists() else None
        if current != desired:
            warn(f"DRIFT: {target.relative_to(REPO_ROOT)} differs from hooks.master.json "
                 f"(run `mise run hooks-sync`)")
            rc = 1
        else:
            log(f"claude: in sync ({target.relative_to(REPO_ROOT)})")
    disabled = load_local()["disabled_agents"]

    # Codex: only checked if installed locally (CI has no ~/.codex) and not opted out.
    if "codex" not in disabled:
        ct = codex_target(master)
        if ct.exists():
            data = _codex_load(ct)
            if not data.get("__error__"):
                present = json.dumps(data)
                want = build_event_groups(master, "codex")
                missing = [
                    h["command"]
                    for groups in want.values()
                    for g in groups
                    for h in g["hooks"]
                    if h["command"] not in present
                ]
                if missing:
                    warn(f"DRIFT: codex hooks.json missing {len(missing)} project hook(s) "
                         f"(run `mise run hooks-sync`)")
                    rc = 1
                else:
                    log(f"codex: in sync ({ct})")

    # Kimi: only checked if its per-user config exists and not opted out.
    if "kimi" not in disabled:
        kt = kimi_target(master)
        if kt.exists():
            present = kt.read_text()
            begin, _end = _kimi_markers(master)
            base = master["agents"]["kimi"]["base_dir"].replace("{repo}", str(REPO_ROOT))
            want_cmds = [
                f"{base}/lib/hook-guard.sh {h['id']} {base}/{h['script']}"
                for h in master["hooks"]
                if master["agents"]["kimi"]["lifecycle_events"].get(h["lifecycle"])
            ]
            missing = [c for c in want_cmds if c not in present]
            if begin not in present or missing:
                warn(f"DRIFT: kimi config.toml missing the project hooks block "
                     f"(run `mise run hooks-sync`)")
                rc = 1
            else:
                log(f"kimi: in sync ({kt})")

    # Hermes: only checked if its runtime config exists and not opted out.
    if "hermes" not in disabled:
        hcfg = REPO_ROOT / master["agents"]["hermes"]["config_target"]
        if hcfg.exists():
            try:
                present = json.dumps(_load_yaml(hcfg))
            except Exception:  # noqa: BLE001
                present = ""
            missing = [c for _ev, c, _t in hermes_commands(master) if c not in present]
            if missing:
                warn(f"DRIFT: hermes config.yaml missing {len(missing)} adapter hook(s) "
                     f"(run `mise run hooks-sync`)")
                rc = 1
            else:
                log(f"hermes: in sync ({hcfg.relative_to(REPO_ROOT)})")

    if rc == 0:
        log("hooks: all targets in sync.")
    return rc


def main() -> int:
    global QUIET
    ap = argparse.ArgumentParser(description="CAF project-scoped agent-hooks fan-out")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true", help="generate claude + inject codex")
    mode.add_argument("--uninstall", action="store_true", help="remove codex injection")
    mode.add_argument("--check", action="store_true", help="drift gate (read-only)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    QUIET = args.quiet

    try:
        master = load_master()
    except Exception as exc:  # noqa: BLE001
        warn(f"could not load {MASTER}: {exc}")
        return 0 if not args.check else 1

    if args.check:
        return cmd_check(master)

    disabled = load_local()["disabled_agents"]
    try:
        if args.install:
            if "claude" in disabled:
                log("claude: skipped (disabled in local.json)")
            else:
                install_claude(master)
            # codex/kimi/hermes are per-dev injections, so opting out actively removes them.
            (uninstall_codex if "codex" in disabled else install_codex)(master)
            (uninstall_kimi if "kimi" in disabled else install_kimi)(master)
            (uninstall_hermes if "hermes" in disabled else install_hermes)(master)
        elif args.uninstall:
            uninstall_codex(master)
            uninstall_kimi(master)
            uninstall_hermes(master)
    except Exception as exc:  # noqa: BLE001 — never break the shell on enter/leave
        warn(f"non-fatal error during {'install' if args.install else 'uninstall'}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
