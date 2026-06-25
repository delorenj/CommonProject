#!/usr/bin/env bash
# Sourceable helpers for per-dev `.agents/local.json` overrides.
#
# Source this, then call:
#   hook_disabled  <hook-id>     # true if .hooks.disabled[] contains the id
#   agent_disabled <agent>       # true if .hooks.disabled_agents[] contains the agent
#   skill_disabled <skill-name>  # true if .skills.disabled[] contains the name
#
# All FAIL OPEN (return 1 = "not disabled") when `.agents/local.json` or `jq` is
# absent, so a missing/garbled local config can never silently kill hooks/skills.
#
# `.agents/local.json` is gitignored — each dev owns their own. See
# `.agents/local.example.json` for the schema.

# Repo root, resolved from this lib's location (.agents/hooks/lib/ -> ../../..).
_caf_local_json() {
  local d
  d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)" || return 1
  printf '%s/.agents/local.json' "$d"
}

# _caf_listed <jq-array-path> <value>  -> 0 if value is in the array.
_caf_listed() {
  local jq_path="$1" val="$2" f
  f="$(_caf_local_json)" || return 1
  [[ -f "$f" ]] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e --arg v "$val" "((${jq_path} // []) | index(\$v)) != null" "$f" >/dev/null 2>&1
}

hook_disabled()  { _caf_listed '.hooks.disabled' "$1"; }
agent_disabled() { _caf_listed '.hooks.disabled_agents' "$1"; }
skill_disabled() { _caf_listed '.skills.disabled' "$1"; }

# True if the dev opted to let their GLOBAL agent system (~/.agents/skills) provide
# any overlapping skill, so the project linker should skip it (no duplicates).
# Teammates with no global layer omit this and inherit the full project set.
skills_defer_to_global() {
  local f
  f="$(_caf_local_json)" || return 1
  [[ -f "$f" ]] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e '.skills.defer_to_global == true' "$f" >/dev/null 2>&1
}

# True if <skill-name> is provided by the global agent SSOT. `-e` follows the
# ~/.agents/skills symlink (-> skillex/skill-sets/global) and its entries.
skill_is_global() {
  local name="$1" gdir="${AGENTS_GLOBAL_SKILLS_DIR:-$HOME/.agents/skills}"
  [[ -e "${gdir}/${name}" ]]
}
