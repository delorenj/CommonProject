#!/bin/bash
# UserPromptSubmit hook (PROJECT-SCOPED).
#
# Nudges the agent to check this project's skills and resume BMAD context.
# Portable across developers: the project's skills directory is resolved
# RELATIVE to this script's location, not a hardcoded home path — so the same
# committed copy works for every dev who clones the repo.
#
# stdout from a UserPromptSubmit hook is injected into the prompt as context.
set -uo pipefail

# This script lives at <repo>/.agents/hooks/reminder-for-skill-check.sh
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HOOK_DIR}/../.." && pwd)"
SKILLS_DIR="${PROJECT_ROOT}/.agents/skills"

echo "⚡ REMINDER: Before starting, check if any skills in ${SKILLS_DIR}/ are relevant to this request."
echo " - If this project uses the BMAD method (a ./_bmad* folder exists) start the session with a brief recap of where the last session left off and suggest the next logical step. If there are options, lay them out, think it through, then offer your recommendation. ⚡"
echo "> NOTE: Treat docs with a grain of salt — this is a fast-moving solo project, so stale data is likely. Gauge confidence with recency: run 'llr' (alias for 'fdfind --type f --hidden --exclude .git -X ls -lt --time=ctime -r --color=auto') and use mtime as a compass correlating mutation-recency with local relevance."
exit 0
