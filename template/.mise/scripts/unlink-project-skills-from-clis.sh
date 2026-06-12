#!/bin/bash
# Remove this project's skill symlinks from shared (global-scope) per-CLI dirs on
# leave, so other projects / your global setup aren't polluted. Project-scoped
# (local-scope) mirrors like ./.kimi-code/skills are left in place — they belong
# to the repo and cost nothing to keep.
#
# Mirrors the SKILL_TARGETS table in link-project-skills-to-clis.sh.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/../.." && pwd)"
agents_skills="${project_root}/.agents/skills"

SKILL_TARGETS=(
  "${CODEX_HOME:-$HOME/.codex}/skills|global"
  "${project_root}/.kimi-code/skills|local"
)

[ -d "$agents_skills" ] || exit 0

_readlink_norm() {
  local l; l="$(readlink "$1" 2>/dev/null || echo "")"
  printf '%s' "${l%/}"
}

for entry in "${SKILL_TARGETS[@]}"; do
  dir="${entry%%|*}"
  scope="${entry##*|}"
  [ "$scope" = "global" ] || continue
  [ -d "$dir" ] || continue

  unlinked=0
  for skill_path in "$agents_skills"/*; do
    [ -e "$skill_path" ] || continue
    name="$(basename "$skill_path")"
    [[ "$name" == ".system" ]] && continue
    target="${dir}/${name}"
    if [ -L "$target" ] && [ "$(_readlink_norm "$target")" = "$skill_path" ]; then
      rm "$target"
      unlinked=$((unlinked + 1))
    fi
  done
  [ "$unlinked" -gt 0 ] && echo "Unlinked ${unlinked} project skill(s) from ${dir}"
done
exit 0
