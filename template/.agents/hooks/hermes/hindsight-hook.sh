#!/usr/bin/env bash
# Hermes -> Hindsight adapter.
#
# Hermes fires shell hooks with the payload piped as JSON on stdin:
#   {"hook_event_name","tool_name","tool_input","session_id","cwd","extra"}
# and runs the command shell=False (argv), so this is invoked as:
#   hindsight-hook.sh <on_session_end|post_tool_call>
#
# Why an adapter (not the Claude hindsight scripts verbatim):
#   - Hermes has NO user-prompt event, so recall has no attach point here.
#   - Hermes tool_input keys differ from Claude's (.file_path/.new_string).
#   - resolve_bank() from the Hermes runtime cwd would resolve to the PM
#     SUBMODULE, not this repo — so we PIN the CoachingAgentFramework bank.
#
# Fire-and-forget; never blocks Hermes. No-ops gracefully without the CLI.
set -uo pipefail

EVENT="${1:-}"
HERMES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .agents/hooks/hermes
REPO_ROOT="$(cd "${HERMES_DIR}/../../.." && pwd)"            # the project repo (NOT the PM submodule)

# Per-dev opt-out: reuse the SAME hook ids as the other agents so one
# local.json entry disables a hook everywhere.
# shellcheck source=../lib/local-config.sh
source "${HERMES_DIR}/../lib/local-config.sh"

HS_BIN="${HOME}/.local/bin/hindsight"
[[ -x "$HS_BIN" ]] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

INPUT="$(cat 2>/dev/null || echo '{}')"
# Pin the project bank = repo basename (resolve_bank from the hermes runtime cwd
# would resolve to the PM submodule). Generic across projects; HINDSIGHT_BANK overrides.
BANK="${HINDSIGHT_BANK:-$(basename "$REPO_ROOT")}"

retain_detached() {  # retain_detached <context> <text>
  setsid nohup timeout 20 "$HS_BIN" memory retain "$BANK" "$2" --context "$1" \
    < /dev/null > /dev/null 2>&1 &
  disown 2>/dev/null || true
}

case "$EVENT" in
  post_tool_call)
    hook_disabled "hindsight-retain" && exit 0
    tool=$(jq -r '.tool_name // "tool"' <<<"$INPUT" 2>/dev/null || echo tool)
    path=$(jq -r '.tool_input.file_path // .tool_input.path // .tool_input.filename // .tool_input.file // empty' <<<"$INPUT" 2>/dev/null || echo "")
    content=$(jq -r '.tool_input.new_string // .tool_input.content // .tool_input.text // empty' <<<"$INPUT" 2>/dev/null || echo "")
    # Only retain file-ish edits; skip pure reads/terminal noise.
    [[ -z "$path" && -z "$content" ]] && exit 0
    snippet=$(printf '%s' "$content" | head -3 | tr '\n' ' ' | cut -c1-200)
    retain_detached "code-edit" "Hermes ${tool} edited ${path:-<no-path>}: ${snippet}"
    ;;
  on_session_end)
    hook_disabled "hindsight-session-end" && exit 0
    sid=$(jq -r '.session_id // "unknown"' <<<"$INPUT" 2>/dev/null || echo unknown)
    retain_detached "session-summary" "Hermes PM session ${sid} ended at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    ;;
  *)
    : # unknown / unmapped event -> no-op
    ;;
esac

exit 0
