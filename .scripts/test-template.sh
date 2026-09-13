#!/usr/bin/env bash
# Smoke test for the Copier template.
# Renders a project, runs the built-in _tasks, asserts structural invariants.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"
OUT_ROOT="${OUT_ROOT:-/tmp/copier-template-test}"
OUT="$OUT_ROOT/render"
FAKE_HOME="$OUT_ROOT/home"
VCS_REF="${TEMPLATE_VCS_REF:-HEAD}"

if ! command -v copier &>/dev/null; then
    echo "Copier not found. Install with: uv tool install copier"
    exit 1
fi

rm -rf "$OUT_ROOT"
mkdir -p "$FAKE_HOME/.config/git"
printf '%s\n' 'THIS-MACHINE-GLOBAL-RULE-MUST-NOT-BE-COPIED' > "$FAKE_HOME/.config/git/ignore"
mkdir -p "$OUT"
printf '%s\n' '# Existing project rule' 'project-cache/' > "$OUT/.gitignore"

echo "Rendering template (vcs-ref=$VCS_REF) → $OUT"
HOME="$FAKE_HOME" copier copy \
    --trust \
    --defaults \
    --vcs-ref="$VCS_REF" \
    --data project_name="Smoke Test" \
    --data project_description="Automated template smoke test" \
    "$TEMPLATE_DIR" "$OUT" >/dev/null

fail=0
assert_file()    { [ -f "$1" ] || { echo "✗ missing file: $1"; fail=1; }; }
assert_exec()    { [ -x "$1" ] || { echo "✗ not executable: $1"; fail=1; }; }
assert_symlink() { [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ] || { echo "✗ $1 should symlink to $2"; fail=1; }; }
assert_dir()     { [ -d "$1" ] || { echo "✗ missing dir: $1"; fail=1; }; }
assert_grep()    { grep -q "$2" "$1" || { echo "✗ $1 should contain: $2"; fail=1; }; }
assert_not_grep(){ ! grep -q "$2" "$1" || { echo "✗ $1 should not contain: $2"; fail=1; }; }

# Rendered files
assert_file    "$OUT/AGENTS.md"
assert_file    "$OUT/mise.toml"
assert_file    "$OUT/.project.json"

# Post-gen tasks (copier _tasks)
assert_file    "$OUT/.gitignore"
assert_grep    "$OUT/.gitignore" '^project-cache/$'
assert_grep    "$OUT/.gitignore" '^# CommonProject repository contract$'
assert_grep    "$OUT/.gitignore" '^/.agents/skills$'
assert_grep    "$OUT/.gitignore" '^!.env.op$'
assert_not_grep "$OUT/.gitignore" 'THIS-MACHINE-GLOBAL-RULE-MUST-NOT-BE-COPIED'
assert_not_grep "$OUT/.gitignore" '^!.claude/'
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
[ ! -f "$OUT/.plane.json" ] || { echo "✗ .plane.json should no longer be created (folded into .project.json)"; fail=1; }

if [ "$fail" -eq 0 ]; then
    echo "✓ All assertions passed"
    echo "  Rendered at: $OUT"
else
    echo "✗ Test failed"
    exit 1
fi
