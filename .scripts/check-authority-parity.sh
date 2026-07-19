#!/usr/bin/env bash
# Reject CommonProject lifecycle/policy workflow residue without banning
# unrelated technical uses of lifecycle, transaction, or recovery vocabulary.

set -euo pipefail

TARGET="${1:-}"

if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
    echo "Usage: $0 <source-or-render-root>" >&2
    exit 2
fi

TARGET="$(cd "$TARGET" && pwd)"
checks=0
fail=0

pass() {
    checks=$((checks + 1))
}

reject_hits() {
    local label="$1"
    local hits="$2"

    if [ -n "$hits" ]; then
        echo "✗ $label" >&2
        printf '%s\n' "$hits" >&2
        fail=1
    else
        pass
    fi
}

# 1. Source, installed, command, and backup paths must not be resurrected.
path_hits="$(
    find "$TARGET" -path "$TARGET/.git" -prune -o -print |
        grep -Ei 'ticket[-_ ]?lifecycle' || true
)"
reject_hits "forbidden lifecycle path found under $TARGET" "$path_hits"

# 2. BMAD must not retain a workflow body or an indirect reference to it.
bmad_hits=""
while IFS= read -r -d '' bmad_dir; do
    matches="$(grep -RInEI 'ticket[-_ ]?lifecycle' "$bmad_dir" || true)"
    if [ -n "$matches" ]; then
        bmad_hits="${bmad_hits}${bmad_hits:+$'\n'}${matches}"
    fi
done < <(
    find "$TARGET" -path "$TARGET/.git" -prune -o -type d -name _bmad -print0
)
reject_hits "forbidden lifecycle reference found in BMAD content" "$bmad_hits"

# 3. No supported CLI dialect may expose a command for the removed workflow.
cli_hits=""
while IFS= read -r -d '' cli_dir; do
    matches="$(grep -RInEI 'ticket[-_ ]?lifecycle' "$cli_dir" || true)"
    if [ -n "$matches" ]; then
        cli_hits="${cli_hits}${cli_hits:+$'\n'}${matches}"
    fi
done < <(
    find "$TARGET" -path "$TARGET/.git" -prune -o -type d \
        \( -name .augment -o -name .claude -o -name .gemini -o -name .opencode \) \
        -print0
)
reject_hits "forbidden lifecycle command reference found" "$cli_hits"

# 4. Workflow/file manifests must not register the removed authority surface.
manifest_hits=""
while IFS= read -r -d '' manifest; do
    matches="$(grep -HnEI 'ticket[-_ ]?lifecycle' "$manifest" || true)"
    if [ -n "$matches" ]; then
        manifest_hits="${manifest_hits}${manifest_hits:+$'\n'}${matches}"
    fi
done < <(
    find "$TARGET" -path "$TARGET/.git" -prune -o -type f -iname '*manifest*' -print0
)
reject_hits "forbidden lifecycle manifest registration found" "$manifest_hits"

# 5. Backups must not preserve a hidden copy that can be reintroduced later.
backup_hits=""
while IFS= read -r -d '' backup; do
    if grep -IqE 'ticket[-_ ]?lifecycle' "$backup"; then
        backup_hits="${backup_hits}${backup_hits:+$'\n'}${backup}"
    fi
done < <(
    find "$TARGET" -path "$TARGET/.git" -prune -o -type f \
        \( -name '*.bak' -o -name '*.backup' -o -name '*~' \) -print0
)
reject_hits "backup contains forbidden lifecycle residue" "$backup_hits"

if [ "$fail" -ne 0 ]; then
    exit 1
fi

echo "✓ Authority parity: $checks/$checks checks passed ($TARGET)"
