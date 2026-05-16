#!/bin/bash
# tests/test_hook_utils.sh — unit coverage for the shared helpers in
# hooks/_hook_utils.py. Currently focused on the compound-cascade advisory
# primitives added for issue #229:
#
#   is_compound_command(command) -> bool
#   has_state_changing_redirect(command) -> bool
#   compound_cascade_hint(command) -> str  (empty unless both above are True)
#
# Each case spawns a python3 subprocess that imports the helper, prints the
# result, and the harness asserts expected==actual.
#
# Usage: bash tests/test_hook_utils.sh
# Exit:  0 = all pass, 1 = at least one fail

set +e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/hooks"
export PYTHONPATH="$HOOKS_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "$HOOKS_DIR/_hook_utils.py" ]; then
  echo "FAIL: _hook_utils.py not found at $HOOKS_DIR" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()

# Generic bool-helper runner.
#   $1 name   $2 helper   $3 expected (true|false)   $4 command
run_bool() {
  local name="$1" helper="$2" expected="$3" command="$4"
  local actual
  actual=$(python3 -c '
import sys
import _hook_utils as h
print(str(getattr(h, sys.argv[1])(sys.argv[2])).lower())
' "$helper" "$command")
  if [ "$actual" = "$expected" ]; then
    echo "PASS [$helper:$expected] $name"; PASS=$((PASS + 1))
  else
    echo "FAIL [$helper:expected=$expected got=$actual] $name"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}

# Hint runner — expect = true (non-empty hint) | false (empty hint).
run_hint() {
  local name="$1" expect="$2" command="$3"
  local actual
  actual=$(python3 -c '
import sys
import _hook_utils as h
print("true" if h.compound_cascade_hint(sys.argv[1]) else "false")
' "$command")
  if [ "$actual" = "$expect" ]; then
    echo "PASS [hint:$expect] $name"; PASS=$((PASS + 1))
  else
    echo "FAIL [hint:expected=$expect got=$actual] $name"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# is_compound_command
# ---------------------------------------------------------------------------

run_bool "single command"               is_compound_command false 'git status'
run_bool "&& separator"                 is_compound_command true  'mkdir /x && cp a b'
run_bool "|| separator"                 is_compound_command true  'test -d /x || mkdir /x'
run_bool "; separator"                  is_compound_command true  'echo a; echo b'
run_bool "| pipe separator"             is_compound_command true  'echo a | grep b'
run_bool "newline separator"            is_compound_command true  $'echo a\necho b'
run_bool "&& inside quotes"             is_compound_command false 'echo "a && b"'
run_bool "; inside quotes"              is_compound_command false 'echo "foo;bar"'
run_bool "empty command"                is_compound_command false ''
run_bool "whitespace only"              is_compound_command false '   '

# ---------------------------------------------------------------------------
# has_state_changing_redirect
# ---------------------------------------------------------------------------

run_bool "single > redirect"            has_state_changing_redirect true  'echo hi > /tmp/x'
run_bool "single >> redirect"           has_state_changing_redirect true  'echo hi >> /tmp/x'
run_bool "attached redirect >/tmp/x"    has_state_changing_redirect true  'echo hi >/tmp/x'
run_bool "embedded foo>/tmp/x"          has_state_changing_redirect true  'cat foo>/tmp/x'
run_bool "heredoc <<EOF"                has_state_changing_redirect true  $'cat <<EOF\nx\nEOF'
run_bool "mkdir as state change"        has_state_changing_redirect true  'mkdir -p /tmp/x'
run_bool "tee writes file"              has_state_changing_redirect true  'echo y | tee /tmp/x'
run_bool "cp mutates fs"                has_state_changing_redirect true  'cp a b'
run_bool "mv mutates fs"                has_state_changing_redirect true  'mv a b'
run_bool "rm mutates fs"                has_state_changing_redirect true  'rm /tmp/x'
run_bool "touch creates file"           has_state_changing_redirect true  'touch /tmp/x'
run_bool "curl -o downloads"            has_state_changing_redirect true  'curl -o /tmp/x https://e.com'
run_bool "curl --output downloads"      has_state_changing_redirect true  'curl --output /tmp/x https://e.com'
run_bool "wget -O downloads"            has_state_changing_redirect true  'wget -O /tmp/x https://e.com'
run_bool "cat file is read-only"        has_state_changing_redirect false 'cat /tmp/x'
run_bool "git status read-only"         has_state_changing_redirect false 'git status'
run_bool "echo > inside quotes"         has_state_changing_redirect false 'echo "a > b"'
run_bool "grep arrow in pattern"        has_state_changing_redirect false 'grep "a => b" /tmp/x'
run_bool "curl without -o"              has_state_changing_redirect false 'curl https://e.com'
# Reviewer-flagged false-positive regressions (review #229)
run_bool "echo quoted heredoc literal"  has_state_changing_redirect false 'echo "<<EOF something"'
run_bool "wget -o is log file"          has_state_changing_redirect false 'wget -o log.txt https://e.com'

# ---------------------------------------------------------------------------
# compound_cascade_hint — both detectors must be true
# ---------------------------------------------------------------------------

# Positives: compound + state-change
run_hint "heredoc redirect then pr create" true \
  $'cat <<EOF > /tmp/body.md\nbody\nEOF\ngh pr create --body-file /tmp/body.md'
run_hint "mkdir && cp"                     true 'mkdir -p /x && cp a /x/'
run_hint "curl -o && bash"                 true 'curl -o /tmp/run.sh https://e.com && bash /tmp/run.sh'
run_hint "rm && git push"                  true 'rm /tmp/x && git push'
run_hint "echo > file && cmd"              true 'echo new > /tmp/x && cat /tmp/x'

# Negatives: missing one of the two conditions
run_hint "single mkdir no hint"            false 'mkdir -p /tmp/x'
run_hint "single redirect no hint"         false 'echo hi > /tmp/x'
run_hint "compound no state change"        false 'git status && git log -3'
run_hint "compound cat | grep no hint"     false 'cat /tmp/x | grep foo'
run_hint "single gh pr create no hint"     false 'gh pr create --body "no marker"'
run_hint "empty command no hint"           false ''
# Reviewer-flagged: quoted "<<EOF" in compound command must NOT trigger hint
run_hint "quoted heredoc-like in compound" false 'echo "<<EOF foo" && git push'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
echo "=========================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=========================================="
if [ "$FAIL" -gt 0 ]; then
  printf '  failed: %s\n' "${FAILED_NAMES[@]}"
  exit 1
fi
exit 0
