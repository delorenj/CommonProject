#!/usr/bin/env bash
# Render the current tracked template and exercise the installed, pinned CLI.
# Set SKILLEX_TEST_TARBALL to a prebuilt tarball when testing before publication.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(dirname "$SCRIPT_DIR")"
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest -q "$TEMPLATE_DIR/tests"
