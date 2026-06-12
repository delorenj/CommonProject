#!/usr/bin/env bash
# Shared telemetry-logging helpers for the Hindsight journal pipeline.
#
# Usage:
#   source "~/.agents/hooks/lib/hindsight-journal.sh"
#   journal_log "$SESSION_ID" '{"event":"recall","bank":"foo",...}'
#
# Each session's events are appended to a per-session JSONL file:
#   ~/.agents/journal/sessions/<session_id>.jsonl
#
# The Stop hook reads this file at session-end to synthesize the journal entry,
# then the file is left in place (for forensics) or pruned by a separate sweeper.

HS_JOURNAL_DIR="${HS_JOURNAL_DIR:-${HOME}/.agents/journal}"
HS_JOURNAL_SESSIONS_DIR="${HS_JOURNAL_DIR}/sessions"

# Append one event (a JSON object string) to the current session's log.
# Silently no-ops if session_id is empty or jq is unavailable.
journal_log() {
  local session_id="$1"
  local event_json="$2"

  [[ -z "$session_id" ]] && return 0
  [[ -z "$event_json" ]] && return 0
  command -v jq >/dev/null 2>&1 || return 0

  mkdir -p "$HS_JOURNAL_SESSIONS_DIR" 2>/dev/null || return 0

  local log_file="${HS_JOURNAL_SESSIONS_DIR}/${session_id}.jsonl"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # Validate + inject timestamp; drop the event silently if it isn't valid JSON.
  printf '%s' "$event_json" |
    jq -c --arg ts "$ts" '. + {ts: $ts}' >>"$log_file" 2>/dev/null ||
    true
}

# Extract session_id from Claude Code hook JSON on stdin.
# Echoes the id (or empty string). The caller is expected to have already cat'd stdin.
journal_session_id_from() {
  local input="$1"
  command -v jq >/dev/null 2>&1 || {
    echo ""
    return 0
  }
  echo "$input" | jq -r '.session_id // empty' 2>/dev/null || echo ""
}
