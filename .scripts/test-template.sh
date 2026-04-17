#!/usr/bin/env bash
# Smoke test for the Copier template.
# Renders a project, runs the built-in _tasks, asserts structural invariants.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"
OUT_ROOT="${OUT_ROOT:-/tmp/copier-template-test}"
OUT="$OUT_ROOT/render"
VCS_REF="${TEMPLATE_VCS_REF:-HEAD}"

if ! command -v copier &>/dev/null; then
    echo "Copier not found. Install with: uv tool install copier"
    exit 1
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

echo "Rendering template (vcs-ref=$VCS_REF) → $OUT"
copier copy \
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

# Rendered files
assert_file    "$OUT/AGENTS.md"
assert_file    "$OUT/mise.toml"
assert_file    "$OUT/.project.json"
assert_file    "$OUT/.mise/scripts/setup-plane.py"
assert_file    "$OUT/.mise/tasks/setup"

# Post-gen tasks (copier _tasks)
assert_file    "$OUT/.gitignore"
assert_symlink "$OUT/CLAUDE.md" "AGENTS.md"
assert_symlink "$OUT/GEMINI.md" "AGENTS.md"
assert_exec    "$OUT/.mise/scripts/setup-plane.py"
assert_exec    "$OUT/.mise/tasks/setup"
assert_dir     "$OUT/.git"

# Renamed data file wired correctly
assert_grep    "$OUT/.project.json" '"project_name": "Smoke Test"'
assert_grep    "$OUT/.mise/scripts/setup-plane.py" 'DATA_FILE = ".project.json"'

# Confirm setup-plane.py can actually read .project.json end-to-end
(cd "$OUT" && PLANE_33GOD_API_KEY="" python3 .mise/scripts/setup-plane.py >/dev/null 2>&1)
assert_file    "$OUT/.plane.json"
assert_grep    "$OUT/.plane.json" '"project_identifier": "SMOK"'

# Initial commit landed
(cd "$OUT" && git log -1 --format=%s | grep -qi "initial commit") \
    || { echo "✗ initial commit missing"; fail=1; }

if [ "$fail" -eq 0 ]; then
    echo "✓ All assertions passed"
    echo "  Rendered at: $OUT"
else
    echo "✗ Test failed"
    exit 1
fi
