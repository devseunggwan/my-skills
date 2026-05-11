#!/bin/bash
# test_trino_describe_first.sh — coverage for hooks/trino-describe-first.py
#
# Synthesizes Claude Code PreToolUse / PostToolUse hook payloads against a
# private history file (via PRAXIS_DESCRIBE_HISTORY_FILE) and asserts:
#
#   silent     → rc=0, stdout empty, stderr empty
#   warn       → rc=0, stdout empty, stderr contains the warning prefix
#   deny       → rc=0, stdout JSON has permissionDecision "deny"
#   recorded   → after a `post` invocation, history JSON contains the table
#
# Usage: bash tests/test_trino_describe_first.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$ROOT_DIR/hooks/trino-describe-first.py"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAILED_NAMES=()

# Each case gets a fresh state file so cases don't pollute each other.
new_state_file() {
  mktemp -t praxis-describe-history-XXXXXX
}

WARN_TAG="[trino:describe-first]"

# run_case name mode expectation env_assignments payload_json
#   mode: "pre" or "post"
#   expectation:
#     "silent"     — rc=0, stdout empty, stderr empty
#     "warn"       — rc=0, stdout empty, stderr contains WARN_TAG
#     "deny"       — rc=0, stdout JSON permissionDecision == "deny"
#   env_assignments: space-separated KEY=VALUE pairs (e.g. "PRAXIS_DESCRIBE_FIRST_MODE=block")
run_case() {
  local name="$1" mode="$2" expectation="$3" envs="$4" payload="$5"

  local state_file
  state_file=$(new_state_file)

  local stdout_file stderr_file
  stdout_file=$(mktemp)
  stderr_file=$(mktemp)

  # Build env prefix.
  local env_prefix=""
  if [ -n "$envs" ]; then
    env_prefix="$envs"
  fi

  echo "$payload" | env -i PATH="$PATH" HOME="$HOME" \
    PRAXIS_DESCRIBE_HISTORY_FILE="$state_file" \
    $env_prefix \
    python3 "$HOOK" "$mode" >"$stdout_file" 2>"$stderr_file"
  local rc=$?
  local out err
  out=$(cat "$stdout_file")
  err=$(cat "$stderr_file")
  rm -f "$stdout_file" "$stderr_file" "$state_file" "$state_file.tmp" 2>/dev/null

  local ok=1
  case "$expectation" in
    silent)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$out" ] || ok=0
      [ -z "$err" ] || ok=0
      ;;
    warn)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$out" ] || ok=0
      echo "$err" | grep -F -q "$WARN_TAG" || ok=0
      ;;
    deny)
      [ "$rc" -eq 0 ] || ok=0
      echo "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    sys.exit(0 if d.get('hookSpecificOutput', {}).get('permissionDecision', '') == 'deny' else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null || ok=0
      ;;
    *)
      echo "  internal: unknown expectation '$expectation'" >&2
      ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    PASS=$((PASS + 1))
    echo "  PASS  $name"
  else
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
    echo "  FAIL  $name (rc=$rc, expected=$expectation)"
    [ -n "$out" ] && echo "        stdout: $(echo "$out" | head -c 400)"
    [ -n "$err" ] && echo "        stderr: $(echo "$err" | head -c 400)"
  fi
}

# run_post_then_pre tests the multi-invocation flow: record a DESCRIBE,
# then query the same table — the pre hook should pass silently.
run_post_then_pre() {
  local name="$1" pre_expectation="$2" post_payload="$3" pre_payload="$4"

  local state_file
  state_file=$(new_state_file)

  echo "$post_payload" | env -i PATH="$PATH" HOME="$HOME" \
    PRAXIS_DESCRIBE_HISTORY_FILE="$state_file" \
    python3 "$HOOK" post >/dev/null 2>&1
  local post_rc=$?

  local stdout_file stderr_file
  stdout_file=$(mktemp)
  stderr_file=$(mktemp)

  echo "$pre_payload" | env -i PATH="$PATH" HOME="$HOME" \
    PRAXIS_DESCRIBE_HISTORY_FILE="$state_file" \
    python3 "$HOOK" pre >"$stdout_file" 2>"$stderr_file"
  local pre_rc=$?
  local out err
  out=$(cat "$stdout_file")
  err=$(cat "$stderr_file")
  rm -f "$stdout_file" "$stderr_file" "$state_file" "$state_file.tmp" 2>/dev/null

  local ok=1
  [ "$post_rc" -eq 0 ] || ok=0
  case "$pre_expectation" in
    silent)
      [ "$pre_rc" -eq 0 ] || ok=0
      [ -z "$out" ] || ok=0
      [ -z "$err" ] || ok=0
      ;;
    warn)
      [ "$pre_rc" -eq 0 ] || ok=0
      echo "$err" | grep -F -q "$WARN_TAG" || ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    PASS=$((PASS + 1))
    echo "  PASS  $name"
  else
    FAIL=$((FAIL + 1))
    FAILED_NAMES+=("$name")
    echo "  FAIL  $name (post_rc=$post_rc pre_rc=$pre_rc expected=$pre_expectation)"
    [ -n "$out" ] && echo "        stdout: $(echo "$out" | head -c 400)"
    [ -n "$err" ] && echo "        stderr: $(echo "$err" | head -c 400)"
  fi
}

echo "test_trino_describe_first"

# --- 1. Query references undescribed table → warn

run_case "undescribed table → warn" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 2. Query references table with alias → resolves to base name, warn

run_case "FROM with alias → warn on base name" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT t.col FROM hive.default.events t WHERE x=1"}}'

# --- 3. JOIN multiple tables → each independently checked, warn

run_case "JOIN multiple undescribed tables → warn" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT a.x, b.y FROM tbl_a a JOIN tbl_b b ON a.id=b.id"}}'

# --- 4. CTE → outer FROM <cte_name> is NOT treated as real table, but CTE body's FROM is checked

run_case "CTE outer reference → warn on CTE body table only" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"WITH foo AS (SELECT * FROM real_tbl) SELECT * FROM foo"}}'

# --- 5. DESCRIBE call itself → not subject to gate (silent)

run_case "DESCRIBE query → silent (not subject to gate)" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE hive.default.events"}}'

# --- 6. SHOW COLUMNS call itself → not subject to gate (silent)

run_case "SHOW COLUMNS query → silent (not subject to gate)" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SHOW COLUMNS FROM hive.default.events"}}'

# --- 7. Non-Trino tool → silent

run_case "non-Trino tool (Read) → silent" "pre" "silent" "" \
  '{"tool_name":"Read","tool_input":{"file_path":"/tmp/foo"}}'

run_case "non-Trino tool (slack send) → silent" "pre" "silent" "" \
  '{"tool_name":"mcp__slack__send","tool_input":{"channel":"x","text":"y"}}'

run_case "non-query Trino tool (lock) → silent" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__query_lock","tool_input":{"query":"SELECT 1"}}'

# --- 8. Malformed JSON → fail-open silent

run_case "malformed JSON → silent (fail-open)" "pre" "silent" "" \
  'not-valid-json'

# --- 9. Empty query → silent

run_case "empty query → silent" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":""}}'

# --- 10. Empty / missing tool_input → silent

run_case "missing tool_input → silent" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query"}'

# --- 11. Block mode env → permissionDecision deny

run_case "block mode env → deny" "pre" "deny" \
  "PRAXIS_DESCRIBE_FIRST_MODE=block" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

run_case "block mode env case-insensitive (BLOCK) → deny" "pre" "deny" \
  "PRAXIS_DESCRIBE_FIRST_MODE=BLOCK" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

run_case "warn mode explicit env → warn" "pre" "warn" \
  "PRAXIS_DESCRIBE_FIRST_MODE=warn" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 12. PostToolUse records DESCRIBE → subsequent query passes silent

run_post_then_pre "DESCRIBE recorded then queried → silent" \
  "silent" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE hive.default.events"}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 13. PostToolUse records SHOW COLUMNS → subsequent query passes silent

run_post_then_pre "SHOW COLUMNS recorded then queried → silent" \
  "silent" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SHOW COLUMNS FROM hive.default.events"}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 14. PostToolUse records ONE table but query references TWO → warn on the un-described one

run_post_then_pre "JOIN with one described one not → warn" \
  "warn" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE tbl_a"}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT a.x, b.y FROM tbl_a a JOIN tbl_b b ON a.id=b.id"}}'

# --- 15. Empty state file (first-ever query) → warn (fail-open is for parse errors, not empty state)
#
# Note: a previously-undescribed table SHOULD warn. The fail-open path is
# only triggered when SQL parsing itself fails (e.g., extract_tables returns
# nothing) — not when parsing succeeds but state is empty.

run_case "first-ever query, empty state → warn" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT * FROM hive.default.events"}}'

# --- 16. SQL with comments → comments stripped, real reference detected, warn

run_case "SQL with -- line comment → warn" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"-- pre comment\nSELECT col FROM hive.default.events"}}'

run_case "SQL with /* block */ comment → warn" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"/* note */ SELECT col FROM hive.default.events"}}'

# --- 17. Custom tool pattern env override

run_case "custom tool pattern matches → warn" "pre" "warn" \
  "PRAXIS_TRINO_TOOL_PATTERN=^mcp__custom__query$" \
  '{"tool_name":"mcp__custom__query","tool_input":{"query":"SELECT col FROM tbl"}}'

run_case "custom tool pattern does not match standard trino → silent" "pre" "silent" \
  "PRAXIS_TRINO_TOOL_PATTERN=^mcp__custom__query$" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 18. Subquery FROM → inner table detected

run_case "subquery FROM → warn on inner table" "pre" "warn" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT * FROM (SELECT col FROM hive.default.nested) sub"}}'

# --- 19. Post-then-pre with catalog.schema.table identifier

run_post_then_pre "qualified name DESCRIBE then qualified query → silent" \
  "silent" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE iceberg.lake.events"}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM iceberg.lake.events"}}'

# --- 20. Failed DESCRIBE (tool_response.isError=true) → NOT recorded; later
#         query still warns. Regression for the "any DESCRIBE marks verified"
#         bug — DESCRIBE on a nonexistent table must not bypass the gate.

run_post_then_pre "failed DESCRIBE (isError) → not recorded, query warns" \
  "warn" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE hive.default.nonexistent"},"tool_response":{"isError":true,"content":[{"type":"text","text":"TABLE_NOT_FOUND"}]}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.nonexistent"}}'

# --- 21. Successful DESCRIBE without tool_response field (back-compat) →
#         still recorded. Older PostToolUse payloads / non-MCP sources may
#         omit the response field entirely — fail-open and record.

run_post_then_pre "DESCRIBE without tool_response field → recorded (back-compat)" \
  "silent" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"DESCRIBE hive.default.events"}}' \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT col FROM hive.default.events"}}'

# --- 22. TVF: UNNEST in FROM → silent (no table to describe)

run_case "FROM UNNEST(ARRAY[...]) → silent (TVF, not a table)" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT x FROM UNNEST(ARRAY[1,2,3]) AS t(x)"}}'

# --- 23. TVF: JSON_TABLE in FROM → silent

run_case "FROM JSON_TABLE(...) → silent (TVF)" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"SELECT * FROM JSON_TABLE(json_col, '\''$.path'\'' COLUMNS(a VARCHAR)) AS t"}}'

# --- 24. CTE with explicit column list `WITH foo(x, y) AS (...)` → foo
#         registered as CTE alias, outer FROM foo is silent.

run_case "CTE with column list (foo(x,y) AS) → silent on outer FROM foo" "pre" "silent" "" \
  '{"tool_name":"mcp__laplace-trino__trino_query","tool_input":{"query":"WITH foo(x, y) AS (SELECT 1, 2) SELECT * FROM foo"}}'

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
