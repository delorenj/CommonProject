#!/usr/bin/env bash
# Shared bank resolver for Hindsight hooks.
# Source this file, then call: BANK=$(resolve_bank)
#
# Resolution order (first non-empty wins):
#   1. .hindsight/bank file in repo root (explicit override; written by Dream agent or by hand)
#   2. HINDSIGHT_BANK env var (per-shell override; useful for ad-hoc routing)
#   3. GitHub remote repo name (origin) e.g. "delorenj/claude-runtime" -> "claude-runtime"
#   4. Local repo root basename (fallback when no remote configured)
#   5. "general" (when not in a git repo at all)
#
# The override file format is a single line containing the bank name. Whitespace
# and a trailing newline are stripped. Lines starting with '#' are treated as
# comments and ignored.

resolve_bank() {
  local url name root override

  root=$(git rev-parse --show-toplevel 2>/dev/null || true)

  # 1. Repo-local override file
  if [[ -n "$root" && -f "$root/.hindsight/bank" ]]; then
    override=$(grep -v '^[[:space:]]*#' "$root/.hindsight/bank" 2>/dev/null \
                 | head -n1 \
                 | tr -d '[:space:]')
    if [[ -n "$override" ]]; then
      echo "$override"
      return
    fi
  fi

  # 2. Env var override
  if [[ -n "${HINDSIGHT_BANK:-}" ]]; then
    echo "$HINDSIGHT_BANK"
    return
  fi

  # 3. GitHub remote name
  url=$(git remote get-url origin 2>/dev/null || true)
  if [[ -n "$url" ]]; then
    url="${url%.git}"
    name="${url##*/}"
    if [[ -n "$name" ]]; then
      echo "$name"
      return
    fi
  fi

  # 4. Repo root basename
  if [[ -n "$root" ]]; then
    basename "$root"
    return
  fi

  # 5. Final fallback
  echo "general"
}
