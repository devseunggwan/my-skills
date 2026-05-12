#!/bin/bash
# tests/test_cross_boundary_preflight.sh
#
# Coverage for hooks/cross-boundary-preflight.sh
#
# Three outcomes:
#   ask   — stdout contains permissionDecision "ask", exit 0
#   block — exit 2, stderr non-empty
#   pass  — exit 0, stdout empty, stderr empty
#
# Usage: bash tests/test_cross_boundary_preflight.sh
# Exit:  0 = all pass, 1 = at least one failure

set +e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO_ROOT/hooks/cross-boundary-preflight.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()

mk_payload() {
  python3 -c '
import json, sys
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}}))
' "$1"
}

run_case() {
  local name="$1" expected="$2" command="$3"
  local out err_file err rc ok=1
  err_file=$(mktemp)
  out=$(mk_payload "$command" | "$HOOK" 2>"$err_file")
  rc=$?; err=$(cat "$err_file"); rm -f "$err_file"

  case "$expected" in
    ask)
      [ "$rc" -eq 0 ] || ok=0
      echo "$out" | grep -q '"permissionDecision": "ask"' || ok=0
      ;;
    block)
      [ "$rc" -eq 2 ] || ok=0
      [ -n "$err" ]   || ok=0
      ;;
    pass)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$out" ]   || ok=0
      [ -z "$err" ]   || ok=0
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    echo "PASS  [$expected] $name"; PASS=$((PASS+1))
  else
    echo "FAIL  [$expected→rc=$rc,stdout=$([ -n "$out" ] && echo non-empty || echo empty),stderr=$([ -n "$err" ] && echo non-empty || echo empty)] $name"
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# BLOCK cases — heredoc in same gh write command segment
# ---------------------------------------------------------------------------

run_case "heredoc in gh issue create" block \
  'gh issue create --title "foo" <<EOF'

run_case "heredoc single-quoted in gh issue create" block \
  "gh issue create --title \"foo\" <<'EOF'"

run_case "heredoc dash strip in gh pr create" block \
  'gh pr create --title "t" <<-EOF'

run_case "heredoc via global --repo before subcommand" block \
  'gh --repo owner/repo issue create --title "t" <<EOF'

# ---------------------------------------------------------------------------
# ASK cases — --repo flag in gh write command
# ---------------------------------------------------------------------------

run_case "gh pr create --repo" ask \
  'gh pr create --repo devseunggwan/praxis --title "feat: x" --body-file /tmp/b.md'

run_case "gh issue create --repo" ask \
  'gh issue create --repo owner/repo --title "bug report"'

run_case "gh issue comment --repo" ask \
  'gh issue comment 42 --repo owner/repo --body "hello"'

run_case "gh issue edit --repo" ask \
  'gh issue edit 7 --repo owner/repo --title "updated"'

run_case "gh pr edit --repo" ask \
  'gh pr edit 5 --repo devseunggwan/praxis --title "updated"'

run_case "gh -R shorthand" ask \
  'gh -R devseunggwan/praxis pr create --title "fix" --body-file /tmp/b.md'

run_case "--repo= equals form" ask \
  'gh issue create --repo=owner/repo --title "test"'

run_case "global --repo before pr create" ask \
  'gh --repo owner/repo pr create --title "t" --body-file /tmp/b.md'

run_case "gh pr new --repo" ask \
  'gh pr new --repo owner/repo --title "t" --body-file /tmp/b.md'

run_case "chained: safe cmd && gh pr create --repo" ask \
  'git fetch origin && gh pr create --repo devseunggwan/praxis --title "t" --body-file /tmp/b.md'

# ---------------------------------------------------------------------------
# ASK: checklist includes Caller chain item for pr create
# ---------------------------------------------------------------------------

run_case_detail() {
  local name="$1" command="$2" needle="$3"
  local out err_file rc ok=1
  err_file=$(mktemp)
  out=$(mk_payload "$command" | "$HOOK" 2>"$err_file")
  rc=$?; rm -f "$err_file"
  [ "$rc" -eq 0 ] || ok=0
  echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('hookSpecificOutput',{}).get('permissionDecisionReason',''); sys.exit(0 if '$needle' in r else 1)" 2>/dev/null || ok=0
  if [ "$ok" -eq 1 ]; then
    echo "PASS  [ask-detail] $name"; PASS=$((PASS+1))
  else
    echo "FAIL  [ask-detail: missing '$needle'] $name"; FAIL=$((FAIL+1)); FAILED_NAMES+=("$name")
  fi
}

run_case_detail "pr create checklist has Caller chain item" \
  'gh pr create --repo owner/repo --title "t" --body-file /tmp/b.md' \
  "Caller chain verified"

run_case_detail "issue create checklist no Caller chain item" \
  'gh issue create --repo owner/repo --title "t"' \
  "body-file"

# ---------------------------------------------------------------------------
# PASS cases — no --repo, no heredoc in gh write segment
# ---------------------------------------------------------------------------

run_case "gh pr create without --repo" pass \
  'gh pr create --title "fix" --body "Caller chain verified: ok"'

run_case "gh issue create without --repo" pass \
  'gh issue create --title "bug" --body-file /tmp/b.md'

run_case "gh issue list --repo (read-only subcommand)" pass \
  'gh issue list --repo owner/repo --state open'

run_case "gh pr list --repo (read-only subcommand)" pass \
  'gh pr list --repo owner/repo'

run_case "gh search issues (handled by block-gh-state-all)" pass \
  'gh search issues --repo owner/repo --state open'

run_case "non-gh command with <<" pass \
  'cat <<EOF > /tmp/file.txt'

run_case "git command" pass \
  'git push origin main'

run_case "opt-out marker" pass \
  'gh pr create --repo devseunggwan/praxis --title "t" --body-file /tmp/b.md  # cross-boundary:ack'

# Variable-assigned heredoc followed by gh pr create — heredoc in different segment
run_case "var-heredoc then gh pr create passes" pass \
  'gh pr create --title "t" --body "$BODY"'

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

non_bash_out=$(echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' | "$HOOK" 2>/dev/null)
if [ -z "$non_bash_out" ]; then
  echo "PASS  [non-Bash passthrough]"; PASS=$((PASS+1))
else
  echo "FAIL  [non-Bash passthrough] got: $non_bash_out"; FAIL=$((FAIL+1)); FAILED_NAMES+=("non-Bash passthrough")
fi

bad_out=$(echo 'not-json' | "$HOOK" 2>/dev/null)
bad_rc=$?
if [ "$bad_rc" -eq 0 ] && [ -z "$bad_out" ]; then
  echo "PASS  [malformed JSON fail-open]"; PASS=$((PASS+1))
else
  echo "FAIL  [malformed JSON fail-open] rc=$bad_rc out=$bad_out"; FAIL=$((FAIL+1)); FAILED_NAMES+=("malformed JSON")
fi

# ---------------------------------------------------------------------------
echo
echo "=================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=================================="
if [ "$FAIL" -gt 0 ]; then
  printf '  failed: %s\n' "${FAILED_NAMES[@]}"
  exit 1
fi
exit 0
