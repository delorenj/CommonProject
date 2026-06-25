#!/usr/bin/env bash
# Per-dev runtime opt-out wrapper for a single hook.
#
#   hook-guard.sh <hook-id> <command> [args...]
#
# If <hook-id> is listed in .agents/local.json `.hooks.disabled[]`, exits 0
# WITHOUT running the command (silent success — no "hook failed" noise in the
# agent). Otherwise execs the command, passing stdin straight through so the
# real hook still receives its JSON payload.
#
# This is how a dev disables an individual hook even for Claude, whose hook
# config is committed (and therefore the same for everyone): the committed
# command is the guarded form, and the guard consults each dev's local.json at
# runtime.
set -uo pipefail

HOOK_ID="${1:-}"
shift || true

# shellcheck source=local-config.sh
source "$(dirname "${BASH_SOURCE[0]}")/local-config.sh"

if [[ -n "$HOOK_ID" ]] && hook_disabled "$HOOK_ID"; then
  exit 0
fi

# Nothing to run (defensive) — succeed quietly.
[[ $# -eq 0 ]] && exit 0

exec "$@"
