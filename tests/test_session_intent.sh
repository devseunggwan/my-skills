#!/bin/bash
# test_session_intent.sh — coverage for hooks/session-intent.py
#
# Synthesizes Claude Code UserPromptSubmit + PreToolUse payloads and asserts:
#   ask    → stdout JSON permissionDecision "ask", rc=0
#   deny   → stdout JSON permissionDecision "deny", rc=0
#   silent → stdout empty, rc=0
#
# Each case gets a fresh state file via $PRAXIS_SESSION_INTENT_FILE so cases
# do not pollute each other.
#
# Usage: bash tests/test_session_intent.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$ROOT_DIR/hooks/session-intent.py"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAILED_NAMES=()

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

# run_hook state_file mode_env payload
#   mode_env: "" or "block"
run_hook() {
  local state_file="$1" mode="$2" payload="$3"
  if [ -n "$mode" ]; then
    echo "$payload" \
      | env -u PRAXIS_INTENT_PIVOT_MODE \
            PRAXIS_SESSION_INTENT_FILE="$state_file" \
            PRAXIS_INTENT_PIVOT_MODE="$mode" \
        python3 "$HOOK" 2>/dev/null
  else
    echo "$payload" \
      | env -u PRAXIS_INTENT_PIVOT_MODE \
            PRAXIS_SESSION_INTENT_FILE="$state_file" \
        python3 "$HOOK" 2>/dev/null
  fi
}

# expect_decision out expected_decision
expect_decision() {
  local out="$1" expected="$2"
  echo "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    decision = d.get('hookSpecificOutput', {}).get('permissionDecision', '')
    sys.exit(0 if decision == '$expected' else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

# case name script
#   The script does the full multi-step session and ends by setting:
#     FINAL_OUT  — the last command's stdout
#     FINAL_RC   — the last command's exit code
#     EXPECT     — one of: ask, deny, silent
case_run() {
  local name="$1" expect="$2" actual_out="$3" actual_rc="$4"

  local ok=1
  case "$expect" in
    ask)
      [ "$actual_rc" -eq 0 ] || ok=0
      expect_decision "$actual_out" "ask" || ok=0
      ;;
    deny)
      [ "$actual_rc" -eq 0 ] || ok=0
      expect_decision "$actual_out" "deny" || ok=0
      ;;
    silent)
      [ "$actual_rc" -eq 0 ] || ok=0
      [ -z "$actual_out" ] || ok=0
      ;;
    *)
      echo "  internal: unknown expectation '$expect'" >&2
      ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    PASS=$((PASS + 1))
    echo "  PASS  $name"
  else
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
    echo "  FAIL  $name (rc=$actual_rc, expected=$expect)"
    [ -n "$actual_out" ] && echo "        stdout: $(echo "$actual_out" | head -c 400)"
  fi
}

new_state() {
  local f="$WORK_DIR/state-$RANDOM-$$.json"
  rm -f "$f"
  echo "$f"
}

echo "test_session_intent"

# -----------------------------------------------------------------------
# Case 1: Read-intent opener → state file written, read_intent_anchored=true
# -----------------------------------------------------------------------
SF=$(new_state)
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"compare pros/cons of issue 178"}')
RC=$?
# Verify state file
if [ "$RC" -eq 0 ] && [ -f "$SF" ] && python3 -c "
import json, sys
d = json.load(open('$SF'))
sys.exit(0 if d.get('read_intent_anchored') is True and d.get('read_intent_marker') == 'compare' else 1)
" 2>/dev/null; then
  case_run "1. read-intent opener writes anchored state" "silent" "$OUT" "$RC"
else
  case_run "1. read-intent opener writes anchored state" "silent" "BAD-STATE" "$RC"
fi

# -----------------------------------------------------------------------
# Case 2: Mutation verb from user → mutation_verb_seen flagged
# -----------------------------------------------------------------------
SF=$(new_state)
# First prompt: read-intent
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"review this design"}' >/dev/null
# Second prompt: mutation verb
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"go ahead and merge it"}')
RC=$?
if python3 -c "
import json, sys
d = json.load(open('$SF'))
sys.exit(0 if d.get('mutation_verb_seen') is True else 1)
" 2>/dev/null; then
  case_run "2. mutation verb in later prompt flags mutation_verb_seen" "silent" "$OUT" "$RC"
else
  case_run "2. mutation verb in later prompt flags mutation_verb_seen" "silent" "BAD-STATE" "$RC"
fi

# -----------------------------------------------------------------------
# Case 3: Mutation tool call after read-intent open, no mutation verb → ask
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"analyze the codebase"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue comment 178 --body foo"}}')
RC=$?
case_run "3. gh issue comment after read-intent open → ask" "ask" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 4: Mutation tool call after read-intent open WITH later mutation
# verb → silent pass
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"review this PR"}' >/dev/null
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"now merge it"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh pr merge 5 --squash"}}')
RC=$?
case_run "4. mutation tool after explicit mutation verb → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 5: Mutation tool call without read-intent open → silent pass
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"close issue 99 please"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue close 99"}}')
RC=$?
case_run "5. session opened with mutation intent → no gate → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 6: Block mode env → deny instead of ask
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"compare two approaches"}' >/dev/null
OUT=$(run_hook "$SF" "block" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh pr create --title foo --body bar"}}')
RC=$?
case_run "6. PRAXIS_INTENT_PIVOT_MODE=block → deny" "deny" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 7: Non-mutation gh tool call → silent pass (read-only)
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"analyze the issues"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue list --state open"}}')
RC=$?
case_run "7. gh issue list (read) after read-intent → silent" "silent" "$OUT" "$RC"

SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"review the PRs"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh pr view 42"}}')
RC=$?
case_run "7b. gh pr view (read) after read-intent → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 8: Korean read-intent + Korean mutation verbs both detected
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"이슈 178의 장단점을 비교해줘"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue comment 178 --body test"}}')
RC=$?
case_run "8a. Korean read-intent (비교/장단점) → ask on mutation" "ask" "$OUT" "$RC"

# Korean mutation verb releases the gate
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"PR을 검토해줘"}' >/dev/null
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"이제 머지해도 좋아"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh pr merge 5 --squash"}}')
RC=$?
case_run "8b. Korean mutation verb (머지) releases gate → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 9: Malformed JSON → fail-open (silent)
# -----------------------------------------------------------------------
SF=$(new_state)
OUT=$(run_hook "$SF" "" 'not-json-at-all')
RC=$?
case_run "9. malformed JSON → silent fail-open" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 10: Non-recognized event → silent pass
# -----------------------------------------------------------------------
SF=$(new_state)
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"SessionStart"}')
RC=$?
case_run "10. unknown hookEventName → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 11: Bash command tokenization respects quoted strings
# A quoted body containing "gh pr merge" text must NOT trigger the gate.
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"analyze this"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo \"note: gh pr merge later\""}}')
RC=$?
case_run "11a. quoted gh pr merge inside echo → silent (not a real cmd)" "silent" "$OUT" "$RC"

# But a chained mutation should still be caught
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"analyze this"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo prep && gh issue create --title foo --body bar"}}')
RC=$?
case_run "11b. chained gh issue create after && → ask" "ask" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 12: First-call state-file-empty → silent (don't ask on session opener)
# Mutation tool fires BEFORE any UserPromptSubmit → state file empty.
# -----------------------------------------------------------------------
SF=$(new_state)
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue close 99"}}')
RC=$?
case_run "12. PreToolUse before any UserPromptSubmit → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 13: Same-utterance read + mutation verb both recorded simultaneously
# "review this PR and merge if good" — gate must NOT fire.
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"review this PR and merge if good"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh pr merge 5 --squash"}}')
RC=$?
case_run "13. same-utterance read + mutation verb → silent on later merge" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 14: gh api --method POST after read-intent → ask
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"check the API behavior"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh api repos/foo/bar/issues --method POST --field title=test"}}')
RC=$?
case_run "14a. gh api --method POST after read-intent → ask" "ask" "$OUT" "$RC"

# gh api default (GET) → silent
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"check the API behavior"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh api repos/foo/bar"}}')
RC=$?
case_run "14b. gh api (default GET) after read-intent → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 15: Non-Bash tool → silent pass
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"analyze"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}')
RC=$?
case_run "15. non-Bash tool → silent" "silent" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 16: Anchor sticks — second prompt without read intent does NOT
# overwrite the original anchor.
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"compare two options"}' >/dev/null
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"1"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh issue create --title foo --body bar"}}')
RC=$?
case_run "16. anchor sticks across non-mutation follow-ups → ask" "ask" "$OUT" "$RC"

# -----------------------------------------------------------------------
# Case 17: gh -R owner/repo issue create (global flag) → ask
# -----------------------------------------------------------------------
SF=$(new_state)
run_hook "$SF" "" \
  '{"hookEventName":"UserPromptSubmit","prompt":"review existing labels"}' >/dev/null
OUT=$(run_hook "$SF" "" \
  '{"hookEventName":"PreToolUse","tool_name":"Bash","tool_input":{"command":"gh -R owner/repo issue create --title foo --body bar"}}')
RC=$?
case_run "17. gh -R owner/repo issue create after read-intent → ask" "ask" "$OUT" "$RC"

echo ""
echo "Result: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed:"
  for name in "${FAILED_NAMES[@]}"; do
    echo "  - $name"
  done
  exit 1
fi
exit 0
