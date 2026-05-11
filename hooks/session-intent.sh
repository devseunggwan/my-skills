#!/bin/bash
# session-intent.sh — multi-event hook entry (UserPromptSubmit + PreToolUse).
#
# Delegates to the Python implementation. Event type is auto-detected from
# the JSON payload's `hookEventName` field (with implicit fallback). Fail-
# safe: if python3 is unavailable, exit 0 (pass) rather than break the
# Claude Code session.

set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

exec python3 "$(dirname "$0")/session-intent.py"
