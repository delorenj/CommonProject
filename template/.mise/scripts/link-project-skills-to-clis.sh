#!/bin/bash
# Fan the project's enabled skill set out to every agent CLI that does NOT read
# .agents/ natively, as per-skill symlinks.
#
#   SSOT:    .agents/skills/   (committed inherited skills + on-enter ./skills/* links)
#   Targets: a table of per-CLI skill dirs, each with a SCOPE:
#     global -> a shared per-user dir (e.g. ~/.codex/skills): link ours in, never
#               clobber foreign entries, removed on leave (unlink-*-from-clis.sh).
#     local  -> a project-scoped mirror dir (e.g. ./.kimi-code/skills) that is fully
#               ours: stale real copies / foreign symlinks are replaced, and
#               disabled/deferred skills are pruned. Persists across leave.
#
# Per-dev controls — .agents/local.json (see .agents/local.example.json):
#   skills.disabled[]       never link these
#   skills.defer_to_global  if true, skip any skill that ALSO exists in your global
#                           SSOT (~/.agents/skills) so your global copy wins and you
#                           get zero duplicates. Teammates omit it → inherit all.
#
# Add a CLI: append one "dir|scope" line to SKILL_TARGETS. That's the whole change.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/../.." && pwd)"
agents_skills="${project_root}/.agents/skills"

SKILL_TARGETS=(
  "${CODEX_HOME:-$HOME/.codex}/skills|global"
  "${project_root}/.kimi-code/skills|local"
)

local_config="${project_root}/.agents/hooks/lib/local-config.sh"
if [ -f "$local_config" ]; then
  # shellcheck source=/dev/null
  source "$local_config"
else
  skill_disabled() { return 1; }
  skills_defer_to_global() { return 1; }
  skill_is_global() { return 1; }
fi

if [ ! -d "$agents_skills" ]; then
  echo "No .agents/skills/ found. Nothing to fan out."
  exit 0
fi

defer=0
skills_defer_to_global && defer=1

# Should this skill be skipped (disabled, or deferred to the dev's global system)?
is_skipped() {
  local name="$1"
  skill_disabled "$name" && return 0
  [ "$defer" = "1" ] && skill_is_global "$name" && return 0
  return 1
}

# readlink with any trailing slash stripped (older links were stored with one).
_readlink_norm() {
  local l; l="$(readlink "$1" 2>/dev/null || echo "")"
  printf '%s' "${l%/}"
}

link_into() {
  local dir="$1" scope="$2" linked=0 skipped=0 pruned=0
  mkdir -p "$dir"
  for skill_path in "$agents_skills"/*; do
    [ -d "$skill_path" ] || continue
    local name target
    name="$(basename "$skill_path")"
    [[ "$name" == ".system" ]] && continue
    target="${dir}/${name}"

    if is_skipped "$name"; then
      # Yield the slot: remove a link WE previously made (so the dev's global copy
      # can claim it), and prune stale entries from our fully-managed mirror.
      if [ -L "$target" ] && [ "$(_readlink_norm "$target")" = "$skill_path" ]; then
        rm -f "$target"
        pruned=$((pruned + 1))
      elif [ "$scope" = "local" ] && { [ -L "$target" ] || [ -e "$target" ]; }; then
        rm -rf "$target"
        pruned=$((pruned + 1))
      fi
      skipped=$((skipped + 1))
      continue
    fi

    if [ -L "$target" ] && [ "$(_readlink_norm "$target")" = "$skill_path" ]; then
      linked=$((linked + 1))
      continue
    fi

    if [ -e "$target" ] || [ -L "$target" ]; then
      if [ "$scope" = "local" ]; then
        rm -rf "$target"            # our mirror: replace stale copy / foreign link
      else
        skipped=$((skipped + 1))    # shared dir: leave foreign entries untouched
        continue
      fi
    fi

    ln -s "$skill_path" "$target"
    linked=$((linked + 1))
  done
  echo "  ${dir} (${scope}): ${linked} linked, ${skipped} skipped, ${pruned} pruned"
}

echo "Fanning .agents/skills -> agent CLIs (defer_to_global=${defer})"
for entry in "${SKILL_TARGETS[@]}"; do
  link_into "${entry%%|*}" "${entry##*|}"
done
