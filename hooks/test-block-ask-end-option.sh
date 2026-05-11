#!/usr/bin/env bash
# test-block-ask-end-option.sh — coverage for the AskUserQuestion end-option gate
#
# Synthesizes Claude Code PreToolUse(AskUserQuestion) payloads and asserts:
#   advisory → exit 0 + stderr non-empty
#   block    → exit 2 + stderr non-empty (PRAXIS_ASK_END_STRICT=1)
#   pass     → exit 0 + stderr empty
#
# Usage: bash hooks/test-block-ask-end-option.sh
# Exit:  0 = all pass; 1 = at least one fail
#
# Hook is advisory by default — most "end-marker present + no stop signal"
# cases expect exit 0 + non-empty stderr. Strict cases (with
# PRAXIS_ASK_END_STRICT=1) expect exit 2.

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/block-ask-end-option.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Build a transcript JSONL file from a single user message.
# $1 = user message text (empty string → no user entries written)
build_transcript() {
  local msg="$1"
  local path="$WORK/transcript-$$-$RANDOM.jsonl"
  if [ -n "$msg" ]; then
    python3 -c '
import json, sys
print(json.dumps({"type": "user", "message": {"role": "user", "content": sys.argv[1]}}))
' "$msg" > "$path"
  else
    : > "$path"
  fi
  echo "$path"
}

# Build a JSON payload for AskUserQuestion tool call.
# $1 = transcript_path
# $2 = options JSON array (e.g., '["Plan A", "End here"]')
build_payload() {
  local transcript="$1" options_json="$2"
  python3 - <<PY
import json, sys
options = json.loads('''$options_json''')
payload = {
    "session_id": "test-session",
    "transcript_path": "$transcript",
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Next step?",
                "header": "Next",
                "multiSelect": False,
                "options": [{"label": opt, "description": "test desc"} for opt in options],
            }
        ]
    },
    "cwd": "/tmp",
}
print(json.dumps(payload))
PY
}

run_case() {
  local name="$1" expected="$2" strict="$3" payload="$4"
  local err_file rc

  err_file=$(mktemp)
  if [ "$strict" = "strict" ]; then
    echo "$payload" | PRAXIS_ASK_END_STRICT=1 "$HOOK" >/dev/null 2>"$err_file"
  else
    echo "$payload" | "$HOOK" >/dev/null 2>"$err_file"
  fi
  rc=$?
  local err_content
  err_content=$(cat "$err_file"); rm -f "$err_file"

  local ok=1
  case "$expected" in
    advisory)
      [ "$rc" -eq 0 ] && [ -n "$err_content" ] || ok=0
      ;;
    block)
      [ "$rc" -eq 2 ] && [ -n "$err_content" ] || ok=0
      ;;
    pass)
      [ "$rc" -eq 0 ] && [ -z "$err_content" ] || ok=0
      ;;
    *)
      echo "INTERNAL: unknown expected '$expected'" >&2
      ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    echo "PASS [$expected] $name"; PASS=$((PASS+1))
  else
    echo "FAIL [$expected→rc=$rc,stderr=$([ -n "$err_content" ] && echo non-empty || echo empty)] $name"
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# (a) ADVISORY cases — default mode, end marker present, no stop signal
# ---------------------------------------------------------------------------

T1=$(build_transcript "Continue with the next step")
P1=$(build_payload "$T1" '["Plan A", "Plan B", "여기서 종료"]')
run_case "korean end marker, neutral user message" advisory default "$P1"

T2=$(build_transcript "What about option B?")
P2=$(build_payload "$T2" '["Implement", "Review", "End here"]')
run_case "english end marker, neutral user message" advisory default "$P2"

T3=$(build_transcript "다음 단계 진행해주세요")
P3=$(build_payload "$T3" '["Step 1", "Step 2", "세션 종료"]')
run_case "korean continuation, korean end marker" advisory default "$P3"

# ---------------------------------------------------------------------------
# (b) BLOCK cases — strict mode, end marker present, no stop signal
# ---------------------------------------------------------------------------

T4=$(build_transcript "Continue please")
P4=$(build_payload "$T4" '["Plan A", "여기서 종료"]')
run_case "strict mode + end marker + no signal → block" block strict "$P4"

T5=$(build_transcript "")
P5=$(build_payload "$T5" '["Plan A", "End here"]')
run_case "strict mode + empty transcript → block (no signal found)" block strict "$P5"

# ---------------------------------------------------------------------------
# (c) PASS cases — no end marker
# ---------------------------------------------------------------------------

T6=$(build_transcript "Continue")
P6=$(build_payload "$T6" '["Plan A", "Plan B", "Plan C"]')
run_case "no end marker present" pass default "$P6"

T7=$(build_transcript "Continue")
P7=$(build_payload "$T7" '["Plan A", "Plan B", "Plan C"]')
run_case "no end marker present (strict mode also passes)" pass strict "$P7"

# ---------------------------------------------------------------------------
# (d) PASS cases — end marker present BUT user signaled stop
# ---------------------------------------------------------------------------

T8=$(build_transcript "그만 하고 여기서 마무리하자")
P8=$(build_payload "$T8" '["Plan A", "여기서 종료"]')
run_case "korean stop signal in user message" pass default "$P8"

T9=$(build_transcript "Stop here, we're done")
P9=$(build_payload "$T9" '["Plan A", "End here"]')
run_case "english stop signal in user message" pass default "$P9"

T10=$(build_transcript "그만")
P10=$(build_payload "$T10" '["Plan A", "여기서 종료"]')
run_case "minimal korean stop signal (strict mode also passes)" pass strict "$P10"

# ---------------------------------------------------------------------------
# (e) PASS cases — not AskUserQuestion tool
# ---------------------------------------------------------------------------

P11=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "Bash",
    "tool_input": {"command": "echo end here"},
}))')
run_case "non-AskUserQuestion tool passes through" pass default "$P11"

P12=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "Edit",
    "tool_input": {"old_string": "여기서 종료", "new_string": "stop"},
}))')
run_case "Edit tool with end-marker in args passes through" pass default "$P12"

# ---------------------------------------------------------------------------
# (f) Graceful degrade — malformed / missing payload pieces
# ---------------------------------------------------------------------------

P13='not even json'
run_case "malformed JSON payload → graceful exit 0" pass default "$P13"

P14=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "AskUserQuestion",
    "tool_input": {},
}))')
run_case "AskUserQuestion with no questions → pass" pass default "$P14"

P15=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "AskUserQuestion",
    "tool_input": {"questions": [{"options": "not-a-list"}]},
}))')
run_case "questions with non-list options → pass" pass default "$P15"

# missing transcript_path: end marker present, no signal → advisory still fires
# (transcript silently empty, stop signal absent → advisory)
T16=$(build_transcript "")
P16=$(build_payload "/nonexistent/path-$$.jsonl" '["Plan A", "End here"]')
run_case "missing transcript file + end marker → advisory" advisory default "$P16"

# ---------------------------------------------------------------------------
# (g) Multi-question payload — marker in any question triggers advisory
# ---------------------------------------------------------------------------

T17=$(build_transcript "Just continue")
P17=$(python3 - <<'PY'
import json
print(json.dumps({
    "session_id": "test-session",
    "transcript_path": "/tmp/nonexistent.jsonl",
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "A?",
                "options": [{"label": "yes"}, {"label": "no"}],
            },
            {
                "question": "B?",
                "options": [{"label": "Plan A"}, {"label": "End here"}],
            },
        ]
    },
}))
PY
)
run_case "multi-question payload, marker in second question" advisory default "$P17"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=========================================="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failed cases:"
  for n in "${FAILED_NAMES[@]}"; do
    echo "  - $n"
  done
fi

[ "$FAIL" -eq 0 ]
