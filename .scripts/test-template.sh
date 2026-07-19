#!/usr/bin/env bash
# Smoke test for the Copier template.
# Renders a project, runs the built-in _tasks, asserts structural invariants.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"
AUTHORITY_CHECK="$SCRIPT_DIR/check-authority-parity.sh"
OUT_ROOT="${OUT_ROOT:-/tmp/copier-template-test}"
OUT="$OUT_ROOT/render"
VCS_REF="${TEMPLATE_VCS_REF:-HEAD}"

if ! command -v copier &>/dev/null; then
    echo "Copier not found. Install with: uv tool install copier"
    exit 1
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

bash "$AUTHORITY_CHECK" "$TEMPLATE_DIR"

echo "Rendering template (vcs-ref=$VCS_REF) → $OUT"
copier copy \
    --trust \
    --defaults \
    --vcs-ref="$VCS_REF" \
    --data project_name="Smoke Test" \
    --data project_description="Automated template smoke test" \
    "$TEMPLATE_DIR" "$OUT" >/dev/null

fail=0
assertions=0
assert_file()    { assertions=$((assertions + 1)); [ -f "$1" ] || { echo "✗ missing file: $1"; fail=1; }; }
assert_exec()    { assertions=$((assertions + 1)); [ -x "$1" ] || { echo "✗ not executable: $1"; fail=1; }; }
assert_symlink() { assertions=$((assertions + 1)); [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] || { echo "✗ $1 should symlink to $2"; fail=1; }; }
assert_dir()     { assertions=$((assertions + 1)); [ -d "$1" ] || { echo "✗ missing dir: $1"; fail=1; }; }
assert_grep()    { assertions=$((assertions + 1)); grep -q "$2" "$1" || { echo "✗ $1 should contain: $2"; fail=1; }; }

assert_exec "$AUTHORITY_CHECK"

# Rendered files
assert_file    "$OUT/AGENTS.md"
assert_file    "$OUT/mise.toml"
assert_file    "$OUT/.project.json"

# Post-gen tasks (copier _tasks)
assert_file    "$OUT/.gitignore"
assert_symlink "$OUT/CLAUDE.md" "AGENTS.md"
assert_symlink "$OUT/GEMINI.md" "AGENTS.md"

# .project.json is the single source of truth: project identity + board binding.
assert_grep    "$OUT/.project.json" '"project_name": "Smoke Test"'
# ticket_provider block (board binding lives here, not in a separate .plane.json)
assert_grep    "$OUT/.project.json" '"type": "plane"'
assert_grep    "$OUT/.project.json" '"identifier": "SMOK"'
# repo_path stamped by the post-gen task
assert_grep    "$OUT/.project.json" "\"repo_path\": \"$OUT\""
# .plane.json must NOT be produced — it has been folded into .project.json
assertions=$((assertions + 1))
[ ! -f "$OUT/.plane.json" ] || { echo "✗ .plane.json should no longer be created (folded into .project.json)"; fail=1; }

bash "$AUTHORITY_CHECK" "$OUT"

# Prove the guard rejects a manifest-only resurrection even when no workflow
# body or generated command path exists.
negative_root="$OUT_ROOT/authority-negative"
mkdir -p "$negative_root/_bmad/_config"
printf 'ticket-lifecycle\n' > "$negative_root/_bmad/_config/workflow-manifest.csv"
assertions=$((assertions + 1))
if bash "$AUTHORITY_CHECK" "$negative_root" >/dev/null 2>&1; then
    echo "✗ authority checker accepted a forbidden manifest registration"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "✓ All $assertions structural assertions passed"
    echo "  Rendered at: $OUT"
else
    echo "✗ Test failed"
    exit 1
fi
