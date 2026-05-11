#!/bin/bash
# test_external_write_falsify_check.sh — coverage for hooks/external-write-falsify-check.py
#
# Synthesizes Claude Code PreToolUse hook payloads and asserts:
#   warn   → exit 0 + stderr contains "REMINDER"
#   silent → exit 0 + stderr empty
#   block  → exit 2 + stderr contains "REMINDER" (when PRAXIS_EXTERNAL_WRITE_STRICT=1)
#
# Usage: bash tests/test_external_write_falsify_check.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$ROOT_DIR/hooks/external-write-falsify-check.py"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAILED_NAMES=()

# run_case name expectation strict_env payload_json
#   expectation:
#     "warn"   — stderr contains REMINDER, rc=0
#     "silent" — stderr empty, rc=0
#     "block"  — stderr contains REMINDER, rc=2
run_case() {
  local name="$1" expectation="$2" strict="$3" payload="$4"

  local err_file
  err_file=$(mktemp)
  if [ "$strict" = "strict" ]; then
    echo "$payload" | PRAXIS_EXTERNAL_WRITE_STRICT=1 python3 "$HOOK" >/dev/null 2>"$err_file"
  else
    echo "$payload" | env -u PRAXIS_EXTERNAL_WRITE_STRICT python3 "$HOOK" >/dev/null 2>"$err_file"
  fi
  local rc=$?
  local err
  err=$(cat "$err_file")
  rm -f "$err_file"

  local ok=1
  case "$expectation" in
    silent)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$err" ]   || ok=0
      ;;
    warn)
      [ "$rc" -eq 0 ] || ok=0
      echo "$err" | grep -q "REMINDER" || ok=0
      ;;
    block)
      [ "$rc" -eq 2 ] || ok=0
      echo "$err" | grep -q "REMINDER" || ok=0
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
    [ -n "$err" ] && echo "        stderr: $err" | head -c 400
  fi
}

echo "test_external_write_falsify_check"

# --- Bash gh detection
run_case "gh issue comment + hypothesis marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 100 --body \"This might fail because the regex appears to mismatch.\""}}'

run_case "gh issue comment + verified claim (silent)" \
  "silent" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 100 --body \"Confirmed: 819 rows verified.\""}}'

run_case "gh pr comment + marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh pr comment 50 --body \"This is potentially broken under concurrent writes.\""}}'

run_case "gh issue create + marker via -b (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue create --title foo -b \"hypothesis: the cache could be stale\""}}'

run_case "gh issue create with --body=value (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue create --title foo --body=\"the loader might be failing\""}}'

# --- non-write gh subcommands → silent
run_case "gh issue list (not a write)" \
  "silent" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue list --search foo"}}'

run_case "gh search issues (not a write)" \
  "silent" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh search issues might-fail"}}'

# --- non-Bash, non-MCP → silent
run_case "Read tool (no body) silent" \
  "silent" "advisory" \
  '{"tool_name":"Read","tool_input":{"file_path":"/tmp/foo"}}'

# --- MCP detection
run_case "MCP slack send + KO marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"mcp__laplace-slack__slack_send_message","tool_input":{"text":"이건 가설인데 prod 적재가 실패했을 가능성이 있습니다."}}'

run_case "MCP slack send + verified content (silent)" \
  "silent" "advisory" \
  '{"tool_name":"mcp__laplace-slack__slack_send_message","tool_input":{"text":"검증 완료: 819 rows."}}'

run_case "MCP notion update_page + marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"mcp__notion__notion_update_page","tool_input":{"content":"This appears to be the cause."}}'

# --- strict mode → block
run_case "strict mode + marker (block)" \
  "block" "strict" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 100 --body \"This might fail.\""}}'

run_case "strict mode + no marker (silent)" \
  "silent" "strict" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 100 --body \"Verified.\""}}'

# --- gh pr review (codex P2 round 3): catches body in pr review subcommand
run_case "gh pr review --body + marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh pr review --comment --body \"This might break under concurrency.\""}}'

run_case "gh pr review --approve + verified body (silent)" \
  "silent" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh pr review --approve --body \"Tests pass, logic verified.\""}}'

# --- chained Bash commands: scan beyond the first body
run_case "chained gh writes — marker in 2nd write (warn)" \
  "warn" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 1 --body \"Verified by tests.\" && gh issue comment 2 --body \"This might fail.\""}}'

run_case "chained gh writes — all bodies verified (silent)" \
  "silent" "advisory" \
  '{"tool_name":"Bash","tool_input":{"command":"gh issue comment 1 --body \"Verified.\"; gh issue comment 2 --body \"Confirmed by query.\""}}'

# --- P2: MCP nested-body recursive extraction (issue #174)
run_case "MCP notion_append_blocks nested rich_text + marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"mcp__notion__notion_append_blocks","tool_input":{"block_id":"abc","children":[{"paragraph":{"rich_text":[{"text":{"content":"This might fail under load."}}]}}]}}'

run_case "MCP notion_append_blocks nested verified content (silent)" \
  "silent" "advisory" \
  '{"tool_name":"mcp__notion__notion_append_blocks","tool_input":{"block_id":"abc","children":[{"paragraph":{"rich_text":[{"text":{"content":"Confirmed: 819 rows."}}]}}]}}'

run_case "MCP slack send_message blocks nested text + marker (warn)" \
  "warn" "advisory" \
  '{"tool_name":"mcp__laplace-slack__slack_send_message","tool_input":{"channel":"C123","blocks":[{"type":"section","text":{"type":"mrkdwn","text":"이건 가설인데 prod 지연 가능성."}}]}}'

run_case "MCP slack blocks nested verified text (silent)" \
  "silent" "advisory" \
  '{"tool_name":"mcp__laplace-slack__slack_send_message","tool_input":{"channel":"C123","blocks":[{"type":"section","text":{"type":"mrkdwn","text":"Verified 100 percent."}}]}}'

run_case "MCP notion non-body top-level fields ignored (silent)" \
  "silent" "advisory" \
  '{"tool_name":"mcp__notion__notion_create_page","tool_input":{"parent_id":"likely-channel-id","title":"Potential customers list"}}'

# Codex F2 regression: Notion page property titles live under
# `properties.{name}.title[].text.content` (NOT body content). A naive
# recursive walker would collect the title text and trip "potential " marker.
run_case "MCP notion property title not collected as body (silent)" \
  "silent" "advisory" \
  '{"tool_name":"mcp__notion__notion_create_page","tool_input":{"parent":{"database_id":"abc"},"properties":{"Name":{"title":[{"text":{"content":"Potential customers list"}}]}}}}'

# Notion page with property title (marker-ish string) AND children body (real
# marker) → only children body should be collected → warn.
run_case "MCP notion property title silent + children body warn" \
  "warn" "advisory" \
  '{"tool_name":"mcp__notion__notion_create_page","tool_input":{"properties":{"Name":{"title":[{"text":{"content":"safe title"}}]}},"children":[{"paragraph":{"rich_text":[{"text":{"content":"This might fail."}}]}}]}}'

# --- malformed input → fail-open silent
run_case "malformed JSON → silent" \
  "silent" "advisory" \
  'not-json'

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
