#!/usr/bin/env bash
# Claude Code PostToolUse hook: retain file edits in Hindsight.
# Reads JSON from stdin (Claude hook contract), fire-and-forget.
# Gracefully exits if hindsight CLI is not installed.
set -euo pipefail

HS_BIN="${HOME}/.local/bin/hindsight"
if [[ ! -x "$HS_BIN" ]]; then
  exit 0
fi

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || echo "")

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty' 2>/dev/null || echo "")
CONTENT_LEN=${#CONTENT}

if [[ $CONTENT_LEN -lt 50 ]]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [[ -n "$REPO_ROOT" ]]; then
  REL_PATH="${FILE_PATH#$REPO_ROOT/}"
else
  REL_PATH="$FILE_PATH"
fi

EXT="${FILE_PATH##*.}"
SNIPPET=$(echo "$CONTENT" | head -5 | tr '\n' ' ' | cut -c1-200)

# Detect bank via shared resolver (GitHub remote name → repo basename → "general")
# shellcheck source=lib/hindsight-bank.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-bank.sh"
BANK=$(resolve_bank)

# Load journal telemetry helper
# shellcheck source=lib/hindsight-journal.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-journal.sh"
SESSION_ID=$(journal_session_id_from "$INPUT")

RETAIN_TEXT="Edited ${REL_PATH} (${EXT}): ${SNIPPET}"

# Fire-and-forget retain
"$HS_BIN" memory retain "$BANK" "$RETAIN_TEXT" \
  --context "code-edit" &>/dev/null &

# Journal telemetry: record what we retained
journal_log "$SESSION_ID" "$(jq -nc \
  --arg bank "$BANK" \
  --arg file "$REL_PATH" \
  --arg ext "$EXT" \
  --arg ctx "code-edit" \
  --arg text "$RETAIN_TEXT" \
  --arg snippet "$SNIPPET" \
  --argjson len $CONTENT_LEN \
  --argjson auto true \
  '{
     event: "retain",
     bank: $bank,
     context: $ctx,
     file: $file,
     ext: $ext,
     content_len: $len,
     snippet: $snippet,
     retained_text: $text,
     source: "auto_posttooluse"
   }')"

exit 0
