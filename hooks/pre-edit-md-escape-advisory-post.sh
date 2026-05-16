#!/bin/bash
# PostToolUse(Read) entry — record markdown file Reads into history.
#
# Delegates to the Python implementation with subcommand `post`. Fail-safe:
# if python3 is unavailable, exit 0 (pass) rather than break the session.

set +e

if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

exec python3 "$(dirname "$0")/pre-edit-md-escape-advisory.py" post
