#!/bin/bash
# PreToolUse hook entry — delegates to the Python implementation.
#
# Fail-safe: if python3 is unavailable, exit 0 (pass) rather than break the
# Claude Code session for opt-in users on systems without python3.

set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

exec python3 "$(dirname "$0")/external-write-falsify-check.py" "$@"
