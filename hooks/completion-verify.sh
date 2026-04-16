#!/bin/bash
# Stop hook: block assistant completion claims without verification evidence
# Contract: reads JSON from stdin, emits {"decision":"block"} or exit 0 pass

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0
[ ! -f "$TRANSCRIPT_PATH" ] && exit 0

LAST_TEXT=$(tail -n 400 "$TRANSCRIPT_PATH" \
  | jq -sr '[.[] | select(.message.role == "assistant" and (.isSidechain // false) == false)] | last | .message.content // [] | map(select(.type == "text") | .text) | join("\n")' \
  2>/dev/null)

[ -z "$LAST_TEXT" ] && exit 0

CLAIM_PATTERNS='(모두 완료(했)?|완료했습니다[.!。?…]?\s*$|작업 완료[.!。?…]?\s*$|완료[.!。?…]?\s*$|\bdone\b[.!?]?\s*$|\bfinished\b[.!?]?\s*$|cleanup (is |was )?finished|implementation complete|all done)'
EVIDENCE_PATTERNS='(tests? passed|\bPASS\b|exit code 0|\b[1-9][0-9]* tests? (ran|passed)|0 errors|build successful|lint clean|성공적으로|테스트.*통과|✅)'

# Check last 10 lines only — avoids false positives from mid-message 완료 mentions
LAST_LINES=$(echo "$LAST_TEXT" | tail -10)
if echo "$LAST_LINES" | grep -qiE "$CLAIM_PATTERNS"; then
  if ! echo "$LAST_TEXT" | grep -E "$EVIDENCE_PATTERNS" >/dev/null; then
    mkdir -p ~/.claude/scope-confirm
    echo "$(date -Iseconds) session=$SESSION_ID blocked_completion_without_evidence" >> ~/.claude/scope-confirm/stop-triggered.log

    cat <<EOF
{
  "decision": "block",
  "reason": "Completion claim detected without verification evidence in the same turn. Paste the command + output (tests/lint/grep/build result) BEFORE declaring done. See AGENTS.md Verification section."
}
EOF
    exit 0
  fi
fi

exit 0
