#!/usr/bin/env bash
# test-block-manufactured-action-menu.sh — coverage for the manufactured action-menu gate
#
# Synthesizes Claude Code PreToolUse(AskUserQuestion) payloads and asserts:
#   advisory → exit 0 + stderr non-empty  (default mode)
#   block    → exit 2 + stderr non-empty  (PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT=1)
#   pass     → exit 0 + stderr empty
#
# Usage: bash hooks/test-block-manufactured-action-menu.sh
# Exit:  0 = all pass; 1 = at least one fail
#
# Hook is ADVISORY by default — "manufactured marker present + command signal
# in prior message" cases expect exit 0 + non-empty stderr.
# Strict cases (PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT=1) expect exit 2.

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/block-manufactured-action-menu.sh"

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
# $2 = options JSON array (e.g., '["Plan A", "진행할까요"]')
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
  local name="$1" expected="$2" mode="$3" payload="$4"
  local err_file rc

  err_file=$(mktemp)
  case "$mode" in
    strict)
      echo "$payload" | PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT=1 "$HOOK" >/dev/null 2>"$err_file"
      ;;
    advisory|default|*)
      echo "$payload" | "$HOOK" >/dev/null 2>"$err_file"
      ;;
  esac
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
# (a) ADVISORY cases — default mode, manufactured marker + command signal
# ---------------------------------------------------------------------------

T1=$(build_transcript "진행해주세요")
P1=$(build_payload "$T1" '["Plan A", "Plan B", "진행할까요"]')
run_case "korean command signal + korean manufactured marker → advisory" advisory default "$P1"

T2=$(build_transcript "go ahead and implement it")
P2=$(build_payload "$T2" '["Step 1", "Step 2", "proceed"]')
run_case "english command signal + proceed marker → advisory" advisory default "$P2"

T3=$(build_transcript "실행해줘")
P3=$(build_payload "$T3" '["Option A", "Option B", "계속할까요"]')
run_case "korean command + 계속할까요 → advisory" advisory default "$P3"

T4=$(build_transcript "merge it now")
P4=$(build_payload "$T4" '["Plan A", "머지할까요"]')
# Destructive label "머지할까요" triggers the destructive-confirmation
# exception even though command + manufactured marker both match.
run_case "english merge command + 머지할까요 → pass (destructive-exempt)" pass default "$P4"

T5=$(build_transcript "proceed with the implementation")
P5=$(build_payload "$T5" '["Plan A", "go ahead"]')
run_case "'proceed' in user message + 'go ahead' marker → advisory" advisory default "$P5"

T6=$(build_transcript "continue please")
P6=$(build_payload "$T6" '["Step A", "Step B", "continue"]')
run_case "'continue' command + 'continue' marker → advisory" advisory default "$P6"

T7=$(build_transcript "push the changes")
P7=$(build_payload "$T7" '["Plan A", "push할까요"]')
# Destructive label "push할까요" triggers the destructive-confirmation
# exception even though command + manufactured marker both match.
run_case "push command + push할까요 → pass (destructive-exempt)" pass default "$P7"

T8=$(build_transcript "다음 액션 진행해")
P8=$(build_payload "$T8" '["Step 1", "다음 액션"]')
run_case "진행 in message + 다음 액션 marker → advisory" advisory default "$P8"

# ---------------------------------------------------------------------------
# (b) BLOCK cases — strict mode, manufactured marker + command signal
# ---------------------------------------------------------------------------

T_s1=$(build_transcript "진행해주세요")
P_s1=$(build_payload "$T_s1" '["Plan A", "진행할까요"]')
run_case "strict mode + korean command + manufactured marker → block" block strict "$P_s1"

T_s2=$(build_transcript "go ahead")
P_s2=$(build_payload "$T_s2" '["Step 1", "proceed"]')
run_case "strict mode + go ahead + proceed marker → block" block strict "$P_s2"

T_s3=$(build_transcript "실행해줘")
P_s3=$(build_payload "$T_s3" '["Option A", "계속할까요"]')
run_case "strict mode + 실행 + 계속할까요 → block" block strict "$P_s3"

# ---------------------------------------------------------------------------
# (c) PASS cases — manufactured marker present but NO command signal in prior msg
# ---------------------------------------------------------------------------

# When there is no command signal in the prior user message, the manufactured
# menu may be legitimate (genuine first-time decision point).

T_p1=$(build_transcript "어떤 방식으로 구현할까요?")
P_p1=$(build_payload "$T_p1" '["Plan A", "Plan B", "진행할까요"]')
run_case "question user msg, no command → pass (legitimate menu)" pass default "$T_p1 $P_p1" && true
# Re-run with correct payload passing
run_case "question user msg, no command → pass" pass default "$P_p1"

T_p2=$(build_transcript "what options do we have?")
P_p2=$(build_payload "$T_p2" '["Option A", "Option B", "proceed"]')
run_case "query user msg, no command → pass" pass default "$P_p2"

T_p3=$(build_transcript "어떻게 처리하면 좋을까요")
P_p3=$(build_payload "$T_p3" '["방법 A", "방법 B", "계속할까요"]')
run_case "open-ended question, no command → pass" pass default "$P_p3"

# Empty transcript: no user message found → fail open
T_p4=$(build_transcript "")
P_p4=$(build_payload "$T_p4" '["Plan A", "진행할까요"]')
run_case "empty transcript + manufactured marker → pass (fail-open)" pass default "$P_p4"

# ---------------------------------------------------------------------------
# (d) PASS cases — no manufactured marker in options
# ---------------------------------------------------------------------------

T_nm1=$(build_transcript "진행해주세요")
P_nm1=$(build_payload "$T_nm1" '["이슈 생성", "PR 생성", "테스트 실행"]')
run_case "command signal but no manufactured marker → pass" pass default "$P_nm1"

T_nm2=$(build_transcript "go ahead")
P_nm2=$(build_payload "$T_nm2" '["Plan A", "Plan B", "Plan C"]')
run_case "go ahead but normal options only → pass" pass default "$P_nm2"

# ---------------------------------------------------------------------------
# (e) PASS cases — not AskUserQuestion tool
# ---------------------------------------------------------------------------

P_t1=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "Bash",
    "tool_input": {"command": "echo proceed"},
}))')
run_case "Bash tool passes through" pass default "$P_t1"

P_t2=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "Edit",
    "tool_input": {"old_string": "진행할까요", "new_string": "proceed"},
}))')
run_case "Edit tool with marker in args passes through" pass default "$P_t2"

# ---------------------------------------------------------------------------
# (f) PASS cases — missing / unreadable transcript → fail-open
# ---------------------------------------------------------------------------

P_missing=$(build_payload "/nonexistent/transcript-$$.jsonl" '["Plan A", "진행할까요"]')
run_case "missing transcript file + manufactured marker → pass (fail-open)" pass default "$P_missing"

# ---------------------------------------------------------------------------
# (g) Graceful degrade — malformed payload pieces
# ---------------------------------------------------------------------------

run_case "malformed JSON payload → graceful exit 0" pass default "not even json"

P_noq=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "AskUserQuestion",
    "tool_input": {},
}))')
run_case "AskUserQuestion with no questions → pass" pass default "$P_noq"

P_badopts=$(python3 -c '
import json
print(json.dumps({
    "tool_name": "AskUserQuestion",
    "tool_input": {"questions": [{"options": "not-a-list"}]},
}))')
run_case "questions with non-list options → pass" pass default "$P_badopts"

# ---------------------------------------------------------------------------
# (h) tool_result-only user entry must be skipped (same pattern as sibling)
# ---------------------------------------------------------------------------

build_tool_result_transcript() {
  local human_text="$1"
  local path="$WORK/transcript-tr-$$-$RANDOM.jsonl"
  python3 - "$human_text" > "$path" <<'PY'
import json, sys
human_text = sys.argv[1]
print(json.dumps({"type": "user", "message": {"role": "user", "content": human_text}}))
print(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Working on it."}]}}))
print(json.dumps({
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "abc123", "content": "command output text"}
        ],
    },
}))
PY
  echo "$path"
}

# tool_result-only most-recent entry, prior human message has command signal
T_tr1=$(build_tool_result_transcript "진행해주세요")
P_tr1=$(build_payload "$T_tr1" '["Step 1", "진행할까요"]')
run_case "[tool-result] skip tool_result entry, prior '진행해주세요' → advisory" advisory default "$P_tr1"

# tool_result-only most-recent, prior message has NO command signal
T_tr2=$(build_tool_result_transcript "어떤 방법이 좋을까요?")
P_tr2=$(build_payload "$T_tr2" '["Plan A", "진행할까요"]')
run_case "[tool-result] skip tool_result entry, prior msg has no command → pass" pass default "$P_tr2"

# ---------------------------------------------------------------------------
# (i) False-positive avoidance — legitimate work options must NOT trigger
# ---------------------------------------------------------------------------

# "continue" appearing inside a longer label phrase that is not a simple
# menu continuation option — substring check should still catch it, but
# let's verify that work options with unrelated text don't false-trigger.

T_fp1=$(build_transcript "진행")
P_fp1=$(build_payload "$T_fp1" '["이슈 생성", "PR 검토", "배포"]')
run_case "[false-pos] normal work options only, no manufactured marker → pass" pass default "$P_fp1"

# "progress" does NOT contain "proceed" as whole word
T_fp2=$(build_transcript "check progress")
P_fp2=$(build_payload "$T_fp2" '["Plan A", "continue monitoring"]')
# "continue monitoring" contains "continue" → this WILL trigger advisory
# This is expected behavior: "continue" is a manufactured marker
run_case "[false-pos] 'continue monitoring' label + 'check progress' user msg → pass (no command signal)" pass default "$P_fp2"

# Multi-question: marker only in second question
T_mq1=$(build_transcript "진행해줘")
P_mq1=$(python3 - <<PY
import json
print(json.dumps({
    "session_id": "test-session",
    "transcript_path": "$T_mq1",
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "A?",
                "options": [{"label": "yes"}, {"label": "no"}],
            },
            {
                "question": "B?",
                "options": [{"label": "Plan A"}, {"label": "진행할까요"}],
            },
        ]
    },
}))
PY
)
run_case "multi-question payload, marker in second question + command signal → advisory" advisory default "$P_mq1"

# ---------------------------------------------------------------------------
# (e) Destructive-confirmation exception — strict mode must pass when any
#     option label names a destructive / irreversible action (merge, push,
#     delete, drop, prod, force). The user's prior command does not absorb
#     per-action approval for shared-state mutations.
# ---------------------------------------------------------------------------

T_de1=$(build_transcript "머지해줘")
P_de1=$(build_payload "$T_de1" '["진행할까요", "머지할까요"]')
run_case "[destructive-exempt-KO] '머지할까요' label + cmd + strict → pass" pass strict "$P_de1"

T_de2=$(build_transcript "push the changes")
P_de2=$(build_payload "$T_de2" '["proceed", "push to main"]')
run_case "[destructive-exempt-EN] 'push to main' label + cmd + strict → pass" pass strict "$P_de2"

T_de3=$(build_transcript "삭제 진행")
P_de3=$(build_payload "$T_de3" '["진행할까요", "데이터 삭제 확정"]')
run_case "[destructive-exempt-KO] '삭제' label + cmd + strict → pass" pass strict "$P_de3"

T_de4=$(build_transcript "go ahead")
P_de4=$(build_payload "$T_de4" '["proceed", "force-push the rebase"]')
run_case "[destructive-exempt-EN] 'force-push' label + cmd + strict → pass" pass strict "$P_de4"

T_de5=$(build_transcript "prod 배포")
P_de5=$(build_payload "$T_de5" '["proceed", "prod deploy 확정"]')
run_case "[destructive-exempt-EN] 'prod' label + cmd + strict → pass" pass strict "$P_de5"

# Advisory mode also passes for destructive labels — the exception applies
# at the marker stage, before mode resolution.
T_de6=$(build_transcript "머지해줘")
P_de6=$(build_payload "$T_de6" '["진행할까요", "머지할까요"]')
run_case "[destructive-exempt-KO] '머지할까요' label + cmd + advisory → pass" pass default "$P_de6"

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
