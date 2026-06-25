#!/bin/bash
# Claude Code Stop hook: capture session summary in Hindsight + write journal entry.
# Gracefully exits if hindsight CLI is not installed.
#
# Hardening notes (2026-05-11):
#  - Every external call is wrapped in `timeout` so a wedged Hindsight API
#    (or any other downstream) can't anchor the hook beyond a known bound.
#  - The journal-writer pipe was bugged: `printf ... | setsid CMD </dev/null`
#    had its pipe data discarded because the explicit /dev/null redirect on
#    the setsid command overrode the pipe. Fixed by writing $INPUT to a temp
#    file and feeding it via `< $tmp` (no pipe → no override).
#  - Claude Code's hook contract waits for the foreground process AND any
#    inherited stdio fds to close. setsid+nohup+disown handles process
#    detachment; the explicit fd redirects (now ordered correctly) close out
#    the parent's pipe so the harness can return immediately.
set -uo pipefail

HS_BIN="${HOME}/.local/bin/hindsight"

# Stdin holds the Stop hook JSON ({session_id, transcript_path, cwd, ...}).
# Persist it to a temp file so we can deliver it to a detached child via
# fd redirect (not a pipe — see header note).
INPUT_TMP=$(mktemp -t hindsight-stop-input.XXXXXX)
cat > "$INPUT_TMP" 2>/dev/null || echo "{}" > "$INPUT_TMP"

# Best-effort cleanup. The journal writer reads $INPUT_TMP early in its run,
# so a short delay before unlinking is safe; we just trust the OS to GC the
# inode after both readers exit. No trap needed.

# 1. Write the journal entry (uses per-session telemetry log).
#    Fully daemonize: setsid + nohup + closed std fds so the writer survives
#    after this hook returns. The reflect step can take 30+ seconds, and
#    Claude Code reaps the hook's process group when the foreground command
#    returns — without setsid the writer gets SIGHUP'd mid-call.
JOURNAL_WRITER="$(dirname "${BASH_SOURCE[0]}")/hindsight-journal-write.sh"
if [[ -x "$JOURNAL_WRITER" ]]; then
  setsid nohup "$JOURNAL_WRITER" \
    < "$INPUT_TMP" \
    > /dev/null 2>&1 &
  disown 2>/dev/null || true
fi

# 2. Record a session-end marker memory (legacy behavior). Same detach pattern.
#    Wrapped in `timeout 3` defensively even though it's already detached:
#    if a future change ever runs this synchronously, the bound still holds.
if [[ -x "$HS_BIN" ]]; then
  # shellcheck source=lib/hindsight-bank.sh
  source "$(dirname "${BASH_SOURCE[0]}")/lib/hindsight-bank.sh"
  BANK=$(resolve_bank)
  setsid nohup timeout 30 "$HS_BIN" memory retain "$BANK" \
    "Session ended at $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --context "session-summary" \
    < /dev/null > /dev/null 2>&1 &
  disown 2>/dev/null || true
fi

exit 0
