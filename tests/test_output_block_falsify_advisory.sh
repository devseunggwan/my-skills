#!/usr/bin/env bash
# test_output_block_falsify_advisory.sh — coverage for output-block-falsify-advisory hook
#
# Synthesizes Claude Code PreToolUse payloads and asserts:
#   advisory → exit 0 + stderr non-empty (contains advisory keyword)
#   pass     → exit 0 + stderr empty
#
# Usage: bash tests/test_output_block_falsify_advisory.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$ROOT_DIR/hooks/output-block-falsify-advisory.sh"

if [ ! -f "$HOOK" ]; then
  echo "FAIL: hook not found: $HOOK" >&2
  exit 1
fi

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAILED_NAMES=()

# run_case name expectation payload
#   expectation:
#     "advisory:<substring>" — exit 0 + stderr contains <substring>
#     "pass"                  — exit 0 + stderr empty
run_case() {
  local name="$1" expectation="$2" payload="$3"

  local err_file
  err_file=$(mktemp)
  printf '%s' "$payload" | "$HOOK" >/dev/null 2>"$err_file"
  local rc=$?
  local err
  err=$(cat "$err_file")
  rm -f "$err_file"

  local ok=1
  case "$expectation" in
    advisory:*)
      local needle="${expectation#advisory:}"
      [ "$rc" -eq 0 ] || ok=0
      case "$err" in
        *"$needle"*) ;;
        *) ok=0 ;;
      esac
      ;;
    pass)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$err" ]   || ok=0
      ;;
    *)
      echo "FAIL  [$name] unknown expectation: $expectation"
      FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name"); return
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    echo "PASS  [$name]"
    PASS=$((PASS + 1))
  else
    echo "FAIL  [$name] expectation=$expectation rc=$rc stderr=${err:-<empty>}"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

make_ask_payload() {
  # $1 = JSON array of option label strings (already JSON-encoded)
  python3 -c "
import json, sys
labels = json.loads(sys.argv[1])
options = [{'label': l} for l in labels]
payload = {
    'session_id': 'test-session',
    'tool_name': 'AskUserQuestion',
    'tool_input': {
        'questions': [
            {
                'question': 'What should we do?',
                'options': options,
            }
        ]
    },
    'cwd': '/tmp',
}
print(json.dumps(payload))
" "$1"
}

make_bash_payload() {
  # $1 = command string
  python3 -c "
import json, sys
payload = {
    'session_id': 'test-session',
    'tool_name': 'Bash',
    'tool_input': {
        'command': sys.argv[1],
    },
    'cwd': '/tmp',
}
print(json.dumps(payload))
" "$1"
}

# ---------------------------------------------------------------------------
# AskUserQuestion positive cases
# ---------------------------------------------------------------------------

run_case "AskUserQuestion: (Recommended) English marker fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_ask_payload '["Option A (Recommended)", "Option B"]')"

run_case "AskUserQuestion: (추천) Korean marker fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_ask_payload '["옵션 A (추천)", "옵션 B"]')"

run_case "AskUserQuestion: (recommended) lowercase also fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_ask_payload '["use existing approach (recommended)"]')"

# ---------------------------------------------------------------------------
# AskUserQuestion negative cases
# ---------------------------------------------------------------------------

run_case "AskUserQuestion: no marker — silent pass" \
  pass \
  "$(make_ask_payload '["Option A", "Option B", "Option C"]')"

run_case "AskUserQuestion: empty options — silent pass" \
  pass \
  "$(make_ask_payload '[]')"

# ---------------------------------------------------------------------------
# Bash positive cases
# ---------------------------------------------------------------------------

run_case "Bash: merge all — English bulk phrase fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload 'gh pr merge --all  # merge all open PRs')"

run_case "Bash: close all — English bulk phrase fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload 'close all open issues via gh cli')"

run_case "Bash: delete all — English bulk phrase fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload 'aws s3 rm s3://bucket/ --recursive # delete all objects')"

run_case "Bash: 모두 삭제 — Korean substring fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload 'gh issue list | xargs gh issue close  # 모두 삭제')"

run_case "Bash: 전부 머지 — Korean substring fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload '# 전부 머지 처리')"

run_case "Bash: 다 머지 — Korean substring fires" \
  "advisory:output-block-falsify-advisory" \
  "$(make_bash_payload 'echo "다 머지 할게요"')"

# ---------------------------------------------------------------------------
# Bash negative cases
# ---------------------------------------------------------------------------

run_case "Bash: git status — silent pass" \
  pass \
  "$(make_bash_payload 'git status')"

run_case "Bash: gh pr list — read-only, no bulk mutation — silent pass" \
  pass \
  "$(make_bash_payload 'gh pr list --state open')"

run_case "Bash: git log --all — --all flag but not a bulk mutation — silent pass" \
  pass \
  "$(make_bash_payload 'git log --all --oneline')"

# Codex #225 P3: word-boundary regression — `disclose all` / `enclose all`
# must NOT match the `close all` substring.
run_case "Bash: disclose all — word-boundary regression — silent pass" \
  pass \
  "$(make_bash_payload 'echo we will disclose all findings')"

run_case "Bash: enclose all — word-boundary regression — silent pass" \
  pass \
  "$(make_bash_payload 'echo enclose all attachments in the email')"

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

run_case "Edge: malformed JSON stdin — silent pass" \
  pass \
  'not valid json at all'

run_case "Edge: empty JSON object — silent pass" \
  pass \
  '{}'

run_case "Edge: unknown tool_name — silent pass" \
  pass \
  "$(python3 -c 'import json; print(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}}))')"

# Codex #225 P2: fail-open on non-string command (number instead of string).
# Hook contract: advisory hooks NEVER break tool execution on malformed payloads.
run_case "Edge: non-string command (int) — fail-open silent pass" \
  pass \
  '{"tool_name":"Bash","tool_input":{"command":123}}'

run_case "Edge: non-string command (null) — fail-open silent pass" \
  pass \
  '{"tool_name":"Bash","tool_input":{"command":null}}'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ ${#FAILED_NAMES[@]} -gt 0 ]; then
  echo "Failed:"
  for n in "${FAILED_NAMES[@]}"; do
    echo "  - $n"
  done
  exit 1
fi
exit 0
