#!/bin/bash
# PreToolUse(Edit/Write/NotebookEdit) hook entry — delegates to Python.
#
# Fail-safe: if python3 is unavailable, exit 0 (pass-through) rather than
# breaking the Claude Code session.

set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

exec python3 "$(dirname "$0")/pre-edit-protected-branch-guard.py"
