#!/usr/bin/env bash
# Claude Code UserPromptSubmit hook: recall Hindsight memories.
# Reads JSON from stdin (Claude hook contract), outputs context to stdout.
# Gracefully exits if hindsight CLI is not installed.
set -euo pipefail

HS_BIN="${HOME}/.local/bin/hindsight"

# Parse Claude's JSON stdin
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // .message // empty' 2>/dev/null || echo "")

# Load journal telemetry helper (no-ops gracefully on its own)
# shellcheck source=lib/hindsight-journal.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-journal.sh"
SESSION_ID=$(journal_session_id_from "$INPUT")
PROMPT_FIRST120=$(printf '%s' "$PROMPT" | head -c 120)

# Skip if hindsight CLI is missing — but still log the skip for the journal.
if [[ ! -x "$HS_BIN" ]]; then
  journal_log "$SESSION_ID" "$(jq -nc \
    --arg p "$PROMPT_FIRST120" \
    --argjson plen ${#PROMPT} \
    '{event:"recall_skipped", reason:"hindsight_binary_missing", prompt_len:$plen, prompt_first120:$p}')"
  exit 0
fi

# Skip empty or noisy prompts — but still log the skip.
if [[ -z "$PROMPT" ]] || [[ ${#PROMPT} -lt 24 ]]; then
  journal_log "$SESSION_ID" "$(jq -nc \
    --arg p "$PROMPT_FIRST120" \
    --argjson plen ${#PROMPT} \
    '{event:"recall_skipped", reason:(if $plen==0 then "empty_prompt" else "prompt_under_min_length" end), min_length:24, prompt_len:$plen, prompt_first120:$p}')"
  exit 0
fi

# Detect bank via shared resolver (GitHub remote name → repo basename → "general")
# shellcheck source=lib/hindsight-bank.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-bank.sh"
BANK=$(resolve_bank)

# Per-source line caps keep total bounded without starving later layers.
PRIMARY_LINES="${HINDSIGHT_PRIMARY_LINES:-30}"
FALLBACK_LINES="${HINDSIGHT_FALLBACK_LINES:-15}"
LINKED_LINES_PER_BANK="${HINDSIGHT_LINKED_LINES:-12}"

recall_cli() {
  NO_COLOR=1 \
  CLICOLOR=0 \
  CLICOLOR_FORCE=0 \
  FORCE_COLOR=0 \
  TERM=dumb \
  COLORTERM= \
  RICH_NO_COLOR=1 \
  HINDSIGHT_NO_COLOR=1 \
  HINDSIGHT_NO_SPINNER=1 \
  HINDSIGHT_DISABLE_SPINNER=1 \
    "$HS_BIN" memory recall "$@"
}

sanitize_recall_output() {
  if command -v perl >/dev/null 2>&1; then
    perl -pe 's/\e\][^\a]*(?:\a|\e\\)//g; s/\e\[[0-?]*[ -\/]*[@-~]//g; s/[^\r\n]*\r//g; s/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]//g'
  else
    sed -E $'s|\x1B\\[[0-?]*[ -/]*[@-~]||g; s|\x1B\\][^\a]*(\a|\x1B\\\\)||g' | tr '\r' '\n'
  fi
}

cap() { sanitize_recall_output | sed '/^[[:space:]]*$/d' | head -n "$1"; }

# Primary bank recall
MEMORIES=$(recall_cli "$BANK" "$PROMPT" 2>/dev/null | cap "$PRIMARY_LINES" || echo "")

# Fallback to general if primary bank is different
FALLBACK=""
if [[ "$BANK" != "general" ]]; then
  FALLBACK=$(recall_cli "general" "$PROMPT" 2>/dev/null | cap "$FALLBACK_LINES" || echo "")
fi

# Always-on global banks — cross-project knowledge that should surface
# regardless of which repo we're in (homelab routing, infra conventions, etc).
# Override via HINDSIGHT_GLOBAL_BANKS="infra dotfiles ..." (space-separated).
GLOBAL_BANKS="${HINDSIGHT_GLOBAL_BANKS:-infra}"
GLOBAL=""
for gb in $GLOBAL_BANKS; do
  [[ "$gb" == "$BANK" || "$gb" == "general" ]] && continue
  gout=$(recall_cli "$gb" "$PROMPT" --budget low 2>/dev/null | cap "$FALLBACK_LINES" || echo "")
  if [[ -n "$gout" ]]; then
    GLOBAL="${GLOBAL}
<!-- global-bank: $gb -->
${gout}"
  fi
done

# Linked-bank fanout via Dream's graph cache.
# Cache path/threshold/fanout cap are env-tunable; set HINDSIGHT_FANOUT=0 to disable.
LINKED=""
GRAPH_CACHE="${HINDSIGHT_DREAM_GRAPH:-${HOME}/.hindsight/dream/bank-graph.json}"
FANOUT_ENABLED="${HINDSIGHT_FANOUT:-1}"
FANOUT_MAX="${HINDSIGHT_FANOUT_MAX:-2}"
FANOUT_MIN_SCORE="${HINDSIGHT_FANOUT_MIN_SCORE:-0.1}"

LINKED_BANKS_USED=()
if [[ "$FANOUT_ENABLED" != "0" ]] && [[ -f "$GRAPH_CACHE" ]] && command -v jq &>/dev/null; then
  LINKED_BANKS=$(jq -r --arg b "$BANK" --argjson min "$FANOUT_MIN_SCORE" --argjson n "$FANOUT_MAX" \
    '(.graph[$b] // []) | map(select(.score >= $min)) | .[:$n] | .[].bank' \
    "$GRAPH_CACHE" 2>/dev/null || true)
  for linked in $LINKED_BANKS; do
    [[ -z "$linked" || "$linked" == "$BANK" || "$linked" == "general" ]] && continue
    out=$(recall_cli "$linked" "$PROMPT" --budget low --max-tokens 1024 2>/dev/null | cap "$LINKED_LINES_PER_BANK" || echo "")
    if [[ -n "$out" ]]; then
      LINKED="${LINKED}
<!-- linked-bank: $linked -->
${out}"
      LINKED_BANKS_USED+=("$linked")
    fi
  done
fi

ALL=""
[[ -n "$MEMORIES" ]] && ALL="${MEMORIES}"
[[ -n "$FALLBACK" ]] && ALL="${ALL}
${FALLBACK}"
[[ -n "$GLOBAL" ]] && ALL="${ALL}
${GLOBAL}"
[[ -n "$LINKED" ]] && ALL="${ALL}
${LINKED}"

# Final overall guard so we never dump unbounded recall output.
ALL=$({ printf '%s\n' "$ALL" | sanitize_recall_output | sed '/^[[:space:]]*$/d' | head -100; } || true)

if [[ -n "$ALL" ]]; then
  printf '\n'
  printf '<!-- hindsight:recall bank=%s -->\n' "$BANK"
  printf '%s\n' "$ALL"
  printf '<!-- /hindsight:recall -->\n'
fi

# --- Journal telemetry: record what we asked and what we got back ---
count_nonempty() { printf '%s\n' "$1" | awk 'NF{c++} END{print c+0}'; }
primary_lines=$(count_nonempty "$MEMORIES")
fallback_lines=$(count_nonempty "$FALLBACK")
global_lines=$(count_nonempty "$GLOBAL")
linked_lines=$(count_nonempty "$LINKED")
total_lines=$(count_nonempty "$ALL")
total_chars=${#ALL}
# Empty array if no linked banks; otherwise JSON array of names.
if [[ ${#LINKED_BANKS_USED[@]} -eq 0 ]]; then
  linked_json='[]'
else
  linked_json=$(printf '%s\n' "${LINKED_BANKS_USED[@]}" | jq -R . | jq -sc .)
fi

journal_log "$SESSION_ID" "$(jq -nc \
  --arg bank "$BANK" \
  --arg p "$PROMPT_FIRST120" \
  --argjson plen ${#PROMPT} \
  --argjson pl "$primary_lines" \
  --argjson fl "$fallback_lines" \
  --argjson gl "$global_lines" \
  --argjson ll "$linked_lines" \
  --argjson tl "$total_lines" \
  --argjson tc "$total_chars" \
  --argjson linked "$linked_json" \
  --arg global "$GLOBAL_BANKS" \
  '{
     event: "recall",
     bank: $bank,
     prompt_len: $plen,
     prompt_first120: $p,
     primary_lines: $pl,
     fallback_lines: $fl,
     global_lines: $gl,
     linked_lines: $ll,
     total_lines: $tl,
     total_chars: $tc,
     linked_banks: $linked,
     global_banks: $global,
     returned_anything: ($tl > 0)
   }')"
