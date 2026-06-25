#!/usr/bin/env bash
# Hindsight Journal writer — invoked at session-end (Stop hook).
#
# Reads ~/.agents/journal/sessions/<session_id>.jsonl, synthesizes
# a plain-English journal entry covering the 6-section spec, and writes it to
# ~/.agents/journal/YYYY-mm-dd-h-m-s.md.
#
# Sections:
#   1. Search terms elicited & how they were selected
#   2. Why hindsight was skipped (if it was)
#   3. Bank resolved (incl. linked-bank fanout)
#   4. Effectiveness of returned data (LLM-reflected)
#   5. What could have been done differently (LLM-reflected)
#   6. What was retained — both telemetry + LLM-reflected rationale
#
# Inputs:
#   - stdin: Claude Code Stop hook JSON ({session_id, transcript_path, ...})
#
# Env knobs:
#   HS_JOURNAL_DIR              Override journal root (default: ~/.agents/journal)
#   HS_JOURNAL_REFLECT          0 to skip the LLM-reflection step (default: 1)
#   HS_JOURNAL_REFLECT_BUDGET   low|mid|high (default: low)
#   HS_JOURNAL_REFLECT_BANK     Bank to reflect into; default: bank of cwd
#   HS_JOURNAL_REFLECT_DEBOUNCE_SECONDS  Min seconds between reflect calls per session (default: 240).
#                                        Claude Code's Stop hook fires on every turn, not just session-close,
#                                        so without this we'd burn an LLM call per response.
#   HS_JOURNAL_KEEP_TELEMETRY   1 to keep per-session JSONL after write; default: 1
#
# Exit codes: always 0 (fire-and-forget; hook failures must not break Stop).

set -uo pipefail

HS_BIN="${HOME}/.local/bin/hindsight"
HS_JOURNAL_DIR="${HS_JOURNAL_DIR:-${HOME}/.agents/journal}"
HS_JOURNAL_SESSIONS_DIR="${HS_JOURNAL_DIR}/sessions"
HS_JOURNAL_REFLECT="${HS_JOURNAL_REFLECT:-1}"
HS_JOURNAL_REFLECT_BUDGET="${HS_JOURNAL_REFLECT_BUDGET:-low}"
HS_JOURNAL_REFLECT_DEBOUNCE_SECONDS="${HS_JOURNAL_REFLECT_DEBOUNCE_SECONDS:-240}"
HS_JOURNAL_KEEP_TELEMETRY="${HS_JOURNAL_KEEP_TELEMETRY:-1}"

# Required tooling
command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat 2>/dev/null || echo "{}")
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[[ -z "$CWD" ]] && CWD=$(pwd)

if [[ -z "$SESSION_ID" ]]; then
  exit 0
fi

LOG_FILE="${HS_JOURNAL_SESSIONS_DIR}/${SESSION_ID}.jsonl"
if [[ ! -f "$LOG_FILE" ]]; then
  # No telemetry captured — nothing to journal.
  exit 0
fi

# Resolve the primary bank (cwd-based, matching the recall hook's logic).
BANK_LIB="$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-bank.sh"
if [[ -f "$BANK_LIB" ]]; then
  # shellcheck source=lib/hindsight-bank.sh
  source "$BANK_LIB"
  PRIMARY_BANK=$( (cd "$CWD" 2>/dev/null && resolve_bank) || echo "general")
else
  PRIMARY_BANK="general"
fi
REFLECT_BANK="${HS_JOURNAL_REFLECT_BANK:-$PRIMARY_BANK}"

mkdir -p "$HS_JOURNAL_DIR" 2>/dev/null || exit 0

# Filename: YYYY-mm-dd-h-m-s.md based on the SESSION START timestamp (earliest event
# in the JSONL), so every Stop event during the session overwrites the same file
# instead of spawning one journal per turn.
SESSION_START_UTC=$(jq -rs '
  [.[] | .ts // empty] | sort | .[0] // empty
' "$LOG_FILE" 2>/dev/null)

if [[ -n "$SESSION_START_UTC" ]]; then
  # Convert UTC ISO-8601 to local time stamp like 2026-05-11-06-32-36
  STAMP=$(date -d "$SESSION_START_UTC" +%Y-%m-%d-%H-%M-%S 2>/dev/null || date +%Y-%m-%d-%H-%M-%S)
else
  STAMP=$(date +%Y-%m-%d-%H-%M-%S)
fi
OUT_FILE="${HS_JOURNAL_DIR}/${STAMP}.md"
REFLECT_CACHE="${HS_JOURNAL_SESSIONS_DIR}/${SESSION_ID}.reflect.txt"

# --- Compute factual summary from the telemetry log ---

# Each helper below either echoes a value, a JSON blob, or an empty string.

recall_count=$(jq -cs '[.[] | select(.event=="recall")] | length' "$LOG_FILE" 2>/dev/null || echo 0)
recall_skipped_count=$(jq -cs '[.[] | select(.event=="recall_skipped")] | length' "$LOG_FILE" 2>/dev/null || echo 0)
retain_count=$(jq -cs '[.[] | select(.event=="retain")] | length' "$LOG_FILE" 2>/dev/null || echo 0)

# Sum of result lines returned across all recall events (proxy for surfacing volume)
total_recall_lines=$(jq -cs '[.[] | select(.event=="recall") | .total_lines] | add // 0' "$LOG_FILE" 2>/dev/null || echo 0)
total_recall_chars=$(jq -cs '[.[] | select(.event=="recall") | .total_chars] | add // 0' "$LOG_FILE" 2>/dev/null || echo 0)
empty_recall_count=$(jq -cs '[.[] | select(.event=="recall" and .returned_anything==false)] | length' "$LOG_FILE" 2>/dev/null || echo 0)

# Sets of banks touched + skip reasons
banks_primary=$(jq -rs '[.[] | select(.event=="recall") | .bank] | unique | join(", ")' "$LOG_FILE" 2>/dev/null || echo "")
banks_linked=$(jq -rs '[.[] | select(.event=="recall") | .linked_banks // [] | .[]] | unique | join(", ")' "$LOG_FILE" 2>/dev/null || echo "")
skip_reasons=$(jq -rs '[.[] | select(.event=="recall_skipped") | .reason] | unique | join(", ")' "$LOG_FILE" 2>/dev/null || echo "")

# Build section-1 prompts list (the actual user prompts that elicited recalls)
prompts_list=$(jq -rs '
  [.[] | select(.event=="recall" or .event=="recall_skipped")]
  | to_entries
  | map("- **Turn \(.key+1)** (`\(.value.event)`, len=\(.value.prompt_len)): \(.value.prompt_first120 | gsub("\n";" ") | gsub("`";"′"))")
  | join("\n")
' "$LOG_FILE" 2>/dev/null || echo "")

# Build section-3 bank breakdown
bank_breakdown=$(jq -rs '
  [.[] | select(.event=="recall")]
  | group_by(.bank)
  | map({
      bank: .[0].bank,
      calls: length,
      lines: (map(.total_lines) | add),
      linked: (map(.linked_banks // []) | add | unique)
    })
  | map("- `\(.bank)` — \(.calls) call(s), \(.lines) total lines back, linked: \(if (.linked|length)==0 then "(none)" else (.linked | join(", ")) end)")
  | join("\n")
' "$LOG_FILE" 2>/dev/null || echo "")

# Build section-6a retained-fact list
retained_list=$(jq -rs '
  [.[] | select(.event=="retain")]
  | to_entries
  | map("- `\(.value.context)` → bank `\(.value.bank)` — `\(.value.file)` (\(.value.content_len) chars edited)\n  > \(.value.snippet | gsub("\n";" ") | .[0:160])")
  | join("\n")
' "$LOG_FILE" 2>/dev/null || echo "")

# --- LLM reflection for subjective sections (4, 5, 6b) ---

reflect_section=""
reflect_error=""
reflect_from_cache=0

# Reuse cached reflect output if it's fresher than the debounce window.
if [[ -f "$REFLECT_CACHE" ]]; then
  cache_age=$(($(date +%s) - $(stat -c %Y "$REFLECT_CACHE" 2>/dev/null || echo 0)))
  if [[ "$cache_age" -lt "$HS_JOURNAL_REFLECT_DEBOUNCE_SECONDS" ]]; then
    reflect_section=$(cat "$REFLECT_CACHE" 2>/dev/null || echo "")
    [[ -n "$reflect_section" ]] && reflect_from_cache=1
  fi
fi

if [[ "$reflect_from_cache" -eq 0 ]] && [[ "$HS_JOURNAL_REFLECT" == "1" ]] && [[ -x "$HS_BIN" ]]; then
  # Build a compact context payload describing the session.
  ctx_payload=$(jq -cs --arg cwd "$CWD" --arg primary "$PRIMARY_BANK" '
    {
      cwd: $cwd,
      primary_bank: $primary,
      recall_events: [.[] | select(.event=="recall")],
      recall_skipped: [.[] | select(.event=="recall_skipped")],
      retain_events: [.[] | select(.event=="retain")]
    }
  ' "$LOG_FILE" 2>/dev/null || echo "{}")

  reflect_query='Reflect on this Claude Code session, given the structured telemetry payload provided as context. Produce three short markdown subsections, each 2-4 sentences, plain English, no preamble:

### 4. Effectiveness of returned data
Given the recall results (total_lines, returned_anything flags) and what was retained vs. what was likely needed, assess whether the recalled context plausibly saved tokens / reduced wasted exploration. Be concrete: cite line counts and the specific banks consulted. If recall returned nothing useful, say so plainly.

### 5. What could have been done differently in past sessions
Speculate on prior-session habits — e.g. broader retains, better tagging, smaller recall budgets — that would have made *this* recall yield more relevant hits. Tie each suggestion to a concrete observation in the telemetry.

### 6b. Why those exact words / why not references
For each retain event in the telemetry, evaluate whether the retained text reads as a self-contained fact future Claude could act on, OR whether it leans on session-local references (file paths, snippets without rationale) that will go stale. If there are no retains, write a single sentence acknowledging that.

Return ONLY the three subsections in the order shown. No top-level heading.'

  reflect_raw=$("$HS_BIN" memory reflect "$REFLECT_BANK" "$reflect_query" \
    --budget "$HS_JOURNAL_REFLECT_BUDGET" \
    --context "$(printf '%s' "$ctx_payload" | head -c 8000)" \
    --max-tokens 1500 \
    --output json 2>/tmp/hs-journal-reflect.err) ||
    reflect_error="reflect command failed (see /tmp/hs-journal-reflect.err)"

  if [[ -n "$reflect_raw" ]]; then
    reflect_section=$(printf '%s' "$reflect_raw" | jq -r '.text // empty' 2>/dev/null)
    # Strip ANSI escapes defensively (hindsight pretty mode would emit them).
    reflect_section=$(printf '%s' "$reflect_section" | sed -r 's/\x1b\[[0-9;]*[a-zA-Z]//g')

    # Sanity-check: backend models sometimes emit tool-call stubs instead of an
    # answer. If we see that pattern, drop the content and surface a clear note.
    if [[ -z "$reflect_section" ]]; then
      reflect_error="reflect returned empty text"
      printf '%s' "$reflect_raw" >/tmp/hs-journal-reflect.out
    elif printf '%s' "$reflect_section" | grep -qE '<(minimax|antml|tool):tool_call|<invoke name='; then
      reflect_error="reflect backend returned a malformed tool-call stub instead of prose (raw saved to /tmp/hs-journal-reflect.out — likely a hindsight server prompt/template issue)"
      printf '%s' "$reflect_section" >/tmp/hs-journal-reflect.out
      reflect_section=""
    elif [[ ${#reflect_section} -lt 80 ]]; then
      reflect_error="reflect returned suspiciously short response (${#reflect_section} chars)"
      printf '%s' "$reflect_section" >/tmp/hs-journal-reflect.out
      reflect_section=""
    fi
  fi

  # Cache a successful reflect so subsequent turns reuse it.
  if [[ -n "$reflect_section" ]]; then
    printf '%s' "$reflect_section" >"$REFLECT_CACHE" 2>/dev/null || true
  fi
fi

# --- Compose the journal markdown ---

# Heredoc the file out. Sections with no data emit a "(none)" placeholder.
{
  cat <<HEADER
---
session_id: ${SESSION_ID}
written_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
cwd: ${CWD}
primary_bank: ${PRIMARY_BANK}
reflect_bank: ${REFLECT_BANK}
reflect_mode: $([[ "$HS_JOURNAL_REFLECT" == "1" ]] && echo "auto" || echo "off")
reflect_source: $([[ "$reflect_from_cache" -eq 1 ]] && echo "cache" || ([[ -n "$reflect_section" ]] && echo "fresh") || echo "none")
recall_events: ${recall_count}
recall_skipped: ${recall_skipped_count}
retain_events: ${retain_count}
total_recall_lines: ${total_recall_lines}
total_recall_chars: ${total_recall_chars}
---

# Hindsight Journal — ${STAMP}

## 1. Search terms elicited & how they were selected

The current pipeline does **not** extract discrete keywords. The full user prompt is passed verbatim to \`hindsight memory recall <bank> "<prompt>"\`, where the server-side embedding model handles semantic matching against the bank's stored chunks. Below is each prompt that *did* trigger (or was *evaluated for*) a recall this session:

HEADER

  if [[ -n "$prompts_list" ]]; then
    printf '%s\n\n' "$prompts_list"
  else
    printf '_(no prompts captured)_\n\n'
  fi

  cat <<SEC2
## 2. Why hindsight was skipped (if it was)

SEC2

  if [[ "$recall_skipped_count" -gt 0 ]]; then
    printf 'Skipped **%s** prompt(s) this session. Reasons observed: `%s`.\n\n' \
      "$recall_skipped_count" "${skip_reasons:-unknown}"
    printf '%s\n' 'Skip rules currently enforced by `hindsight-recall.sh`:'
    printf '%s\n' '- Prompt under 24 characters (`prompt_under_min_length`)'
    printf '%s\n' '- Empty prompt body (`empty_prompt`)'
    printf '%s\n\n' '- `hindsight` CLI not on PATH (`hindsight_binary_missing`)'
  else
    printf 'Recall was attempted on every eligible prompt — no skips this session.\n\n'
  fi

  cat <<SEC3
## 3. Bank resolved

- **Primary bank** (cwd-resolved): \`${PRIMARY_BANK}\`
- **Banks touched by recall**: ${banks_primary:-_(none)_}
- **Linked banks reached via Dream fanout**: ${banks_linked:-_(none)_}

Per-bank breakdown:

SEC3

  if [[ -n "$bank_breakdown" ]]; then
    printf '%s\n\n' "$bank_breakdown"
  else
    printf '_(no recall events to break down)_\n\n'
  fi

  cat <<SEC6A
## 6a. What was retained this session

SEC6A

  if [[ "$retain_count" -gt 0 ]]; then
    printf '%s\n\n' "$retained_list"
  else
    printf '_(no retain events captured — either nothing was saved, or retains were issued via paths the hooks do not observe)_\n\n'
  fi

  # Subjective sections
  cat <<SUBJ_HEADER
## Reflective sections (LLM-synthesized)

SUBJ_HEADER

  if [[ -n "$reflect_section" ]]; then
    printf '%s\n\n' "$reflect_section"
  else
    if [[ "$HS_JOURNAL_REFLECT" != "1" ]]; then
      printf '_Reflection disabled (`HS_JOURNAL_REFLECT=0`). Run later with:_ `HS_JOURNAL_REFLECT=1 HS_JOURNAL_REFLECT_BANK=%s bash %s < <(echo %s)`\n\n' \
        "$REFLECT_BANK" "$(realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "$0")" \
        "$(printf '%s' "$INPUT" | jq -c .)"
    elif [[ -n "$reflect_error" ]]; then
      printf '_Reflection failed: %s_\n\n' "$reflect_error"
    else
      printf '_Reflection returned no content._\n\n'
    fi
  fi

  cat <<FOOTER
---

### Raw telemetry

\`\`\`
$(cat "$LOG_FILE")
\`\`\`

_Telemetry log: \`${LOG_FILE}\`_
FOOTER
} >"$OUT_FILE" 2>/dev/null

# Optionally prune the telemetry file (default: keep it).
if [[ "$HS_JOURNAL_KEEP_TELEMETRY" != "1" ]]; then
  rm -f "$LOG_FILE" 2>/dev/null || true
fi

exit 0
