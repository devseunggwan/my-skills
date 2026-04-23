#!/bin/bash

# expansion-guard.sh
# Pre-response guard to suppress option-set expansion for simple imperatives
# Triggers when user's message matches single-action pattern

set -euo pipefail

USER_MESSAGE="${1:-}"

check_guard() {
  local msg="$1"

  if [ "$(echo "$msg" | wc -w | tr -d ' ')" -le 8 ]; then
    return 0
  fi

  if echo "$msg" | grep -qiE '^(refresh|refresh |print |print |show |show |纯 )' 2>/dev/null; then
    return 0
  fi

  if echo "$msg" | grep -qiE '(^|\s)(만|simply|，纯)(\s|$)' 2>/dev/null; then
    return 0
  fi

  return 1
}

if check_guard "$USER_MESSAGE"; then
  echo ""
  echo "⚠️  [expansion-guard] Simple imperative detected."
  echo "Before responding, verify this is NOT an option-set expansion case:"
  echo "  - Avoid (1)/(2)/(3) or A./B./C. enumerated options"
  echo "  - Avoid multi-choice questions (which/다음 중/선택)"
  echo "  - If user wants one thing, give ONE thing. Do not expand."
  echo ""
  echo "Respond literally or ask one clarifying question only."
  exit 1
fi

exit 0