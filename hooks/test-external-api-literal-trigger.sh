#!/usr/bin/env bash
# test-external-api-literal-trigger.sh — coverage for external-api-literal-trigger hook
#
# Synthesizes Claude Code PreToolUse payloads and asserts:
#   advisory → exit 0 + stderr non-empty
#   pass     → exit 0 + stderr empty
#
# Usage: bash hooks/test-external-api-literal-trigger.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/external-api-literal-trigger.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()

# Run a single test case.
# $1 = name
# $2 = expected: "advisory" (exit 0 + stderr non-empty) | "pass" (exit 0 + stderr empty)
# $3 = JSON payload (string)
run_case() {
  local name="$1" expected="$2" payload="$3"
  local err_file rc
  err_file=$(mktemp)
  echo "$payload" | "$HOOK" >/dev/null 2>"$err_file"
  rc=$?
  local err_content
  err_content=$(cat "$err_file"); rm -f "$err_file"

  local ok=1
  case "$expected" in
    advisory)
      # exit 0 + stderr non-empty
      [ "$rc" -eq 0 ] && [ -n "$err_content" ] || ok=0
      ;;
    pass)
      # exit 0 + stderr empty
      [ "$rc" -eq 0 ] && [ -z "$err_content" ] || ok=0
      ;;
    *)
      echo "FAIL: unknown expected: $expected" >&2
      ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name (rc=$rc, stderr='${err_content:0:80}')"
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# Helper: build a payload for a given tool_name + content field
# ---------------------------------------------------------------------------
make_write_payload() {
  # $1 = content string
  python3 -c "
import json, sys
payload = {
    'session_id': 'test-session',
    'tool_name': 'Write',
    'tool_input': {
        'file_path': '/tmp/test.py',
        'content': sys.argv[1],
    },
    'cwd': '/tmp',
}
print(json.dumps(payload))
" "$1"
}

make_edit_payload() {
  # $1 = new_string value
  python3 -c "
import json, sys
payload = {
    'session_id': 'test-session',
    'tool_name': 'Edit',
    'tool_input': {
        'file_path': '/tmp/test.py',
        'old_string': 'foo',
        'new_string': sys.argv[1],
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

make_other_tool_payload() {
  # $1 = tool_name, $2 = content
  python3 -c "
import json, sys
payload = {
    'session_id': 'test-session',
    'tool_name': sys.argv[1],
    'tool_input': {
        'file_path': '/tmp/test.py',
        'content': sys.argv[2],
    },
    'cwd': '/tmp',
}
print(json.dumps(payload))
" "$1" "$2"
}

# ---------------------------------------------------------------------------
# Fire cases: should emit advisory
# ---------------------------------------------------------------------------

run_case "Write: LAST_365_DAYS enum in content" advisory \
  "$(make_write_payload 'period = "LAST_365_DAYS"')"

run_case "Write: THIS_WEEK_OF_MONTH date literal" advisory \
  "$(make_write_payload 'date_range = "THIS_WEEK_OF_MONTH"')"

run_case "Edit: 3-part SQL identifier mysql.auth.tb_user" advisory \
  "$(make_edit_payload 'SELECT * FROM mysql.auth.tb_user WHERE id = 1')"

run_case "Bash: SHOPBY_AUTH_TOKEN env var usage" advisory \
  "$(make_bash_payload 'curl -H "Authorization: Bearer $SHOPBY_AUTH_TOKEN" https://api.example.com')"

run_case "Write: PAYMENT_STATUS_APPROVED enum" advisory \
  "$(make_write_payload 'status = "PAYMENT_STATUS_APPROVED"')"

run_case "Edit: 3-part SQL hive.warehouse.orders" advisory \
  "$(make_edit_payload 'SELECT * FROM hive.warehouse.orders LIMIT 10')"

# ---------------------------------------------------------------------------
# Pass cases: should NOT emit advisory
# ---------------------------------------------------------------------------

run_case "Pass: TODO stop-word excluded" pass \
  "$(make_write_payload '# TODO: refactor this function')"

run_case "Pass: FIXME stop-word excluded" pass \
  "$(make_write_payload '# FIXME: handle edge case')"

run_case "Pass: README stop-word excluded" pass \
  "$(make_write_payload 'with open("README") as f: pass')"

run_case "Pass: LICENSE stop-word excluded" pass \
  "$(make_write_payload 'license = "LICENSE"')"

run_case "Pass: MIT stop-word excluded" pass \
  "$(make_write_payload 'license = "MIT"')"

run_case "Pass: short ALL_CAPS OS (length < 6)" pass \
  "$(make_write_payload 'import os; os.environ.get("OS")')"

run_case "Pass: short ALL_CAPS URL (length < 6)" pass \
  "$(make_write_payload 'base_url = URL')"

run_case "Pass: plain lowercase text" pass \
  "$(make_write_payload 'def hello_world(): return "hello"')"

run_case "Pass: 2-part SQL identifier (not 3-part)" pass \
  "$(make_write_payload 'SELECT * FROM schema.table_name')"

run_case "Pass: tool_name Read (not in scope)" pass \
  "$(make_other_tool_payload "Read" 'SHOPBY_AUTH_TOKEN is the key')"

run_case "Pass: tool_name NotebookEdit (not in scope)" pass \
  "$(make_other_tool_payload "NotebookEdit" 'LAST_365_DAYS')"

run_case "Pass: pure ALL_CAPS without underscore or digit (SQL keyword SELECT)" pass \
  "$(make_write_payload 'query = "SELECT * FROM users"')"

run_case "Pass: malformed JSON input" pass \
  'not valid json at all'

run_case "Pass: empty content field" pass \
  "$(make_write_payload '')"

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
