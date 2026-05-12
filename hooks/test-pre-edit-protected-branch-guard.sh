#!/usr/bin/env bash
# test-pre-edit-protected-branch-guard.sh — coverage for pre-edit-protected-branch-guard
#
# Uses PRAXIS_PBGUARD_TEST_* env vars to mock git state without a real repo.
# Hook outputs JSON with permissionDecision "deny" on stdout when blocking.
# Fail-open paths emit nothing and exit 0.
#
# Usage: bash hooks/test-pre-edit-protected-branch-guard.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/pre-edit-protected-branch-guard.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()

# Shared fake repo root — no real git repo needed (test overrides mock git).
# Must NOT start with /tmp/ to avoid the /tmp/ planning-artifact skip rule.
FAKE_ROOT="/Users/test/fake-guard-repo"
EXISTING_FILE="$FAKE_ROOT/src/existing.py"
NEW_FILE="$FAKE_ROOT/src/new-file.py"
DIRTY_STATUS=" M src/existing.py"

# build_payload <tool_name> <file_path>
build_payload() {
  local tool="$1" path="$2"
  python3 -c '
import json, sys
tool, path = sys.argv[1], sys.argv[2]
key = "notebook_path" if tool == "NotebookEdit" else "file_path"
print(json.dumps({"tool_name": tool, "tool_input": {key: path}}))
' "$tool" "$path"
}

# pipe_hook <payload> [KEY=VALUE ...]
# Run the hook with the given payload and optional env overrides (subshell).
pipe_hook() {
  local payload="$1"; shift
  (
    for kv in "$@"; do
      export "$kv"
    done
    printf '%s' "$payload" | "$HOOK"
  )
}

# check_deny <stdout_content>
# Returns 0 if stdout contains a valid deny JSON, 1 otherwise.
check_deny() {
  local out="$1"
  [ -n "$out" ] || return 1
  python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
    o = d.get("hookSpecificOutput", {})
    assert o.get("permissionDecision") == "deny"
except Exception:
    sys.exit(1)
' "$out" 2>/dev/null
}

# run_case <name> <expected:deny|pass> <tool_name> <file_path> [KEY=VALUE ...]
run_case() {
  local name="$1" expected="$2" tool="$3" path="$4"; shift 4
  local env_overrides=("$@")

  local payload
  payload=$(build_payload "$tool" "$path")

  local out_file err_file
  out_file=$(mktemp); err_file=$(mktemp)
  pipe_hook "$payload" "${env_overrides[@]}" >"$out_file" 2>"$err_file"
  local rc=$?
  local out err
  out=$(cat "$out_file"); err=$(cat "$err_file")
  rm -f "$out_file" "$err_file"

  local ok=1
  case "$expected" in
    deny)
      [ "$rc" -eq 0 ] || ok=0
      check_deny "$out"  || ok=0
      ;;
    pass)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$out" ]    || ok=0
      ;;
    *)
      echo "FAIL [$name] unknown expected: $expected"
      ((FAIL++)); FAILED_NAMES+=("$name"); return
      ;;
  esac

  if [ "$ok" -eq 1 ]; then
    echo "PASS [$expected] $name"; ((PASS++))
  else
    echo "FAIL [$expected] $name (rc=$rc, stdout=$([ -n "$out" ] && echo non-empty || echo empty), stderr=$([ -n "$err" ] && echo non-empty || echo empty))"
    ((FAIL++)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# DENY: dirty + protected + edit target NOT in dirty diff → block
# ---------------------------------------------------------------------------

run_case "dirty+protected+new-target → deny (Edit)" deny \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+new-target → deny (Write)" deny \
  Write "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+new-target → deny (NotebookEdit)" deny \
  NotebookEdit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+new-target → deny (dev branch)" deny \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=dev" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+new-target → deny (prod branch)" deny \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=prod" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+new-target → deny (master branch)" deny \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=master" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+README.md+BLOCK_DOCS=1 → deny" deny \
  Edit "$FAKE_ROOT/README.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS" \
  "PRAXIS_PBGUARD_BLOCK_DOCS=1"

run_case "dirty+protected+custom-protected-branches → deny" deny \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=release" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS" \
  "PRAXIS_PROTECTED_BRANCHES=release,stable"

# ---------------------------------------------------------------------------
# PASS: clean working tree → no block
# ---------------------------------------------------------------------------

run_case "clean+protected → pass (no dirty)" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS="

# ---------------------------------------------------------------------------
# PASS: non-protected branch → no block
# ---------------------------------------------------------------------------

run_case "dirty+non-protected → pass" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=feature/my-feature" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+non-protected (issue branch) → pass" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=issue-198-guard-hook" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: edit target already in dirty diff → allow in-flight work
# ---------------------------------------------------------------------------

run_case "dirty+protected+target-in-diff → pass (in-flight Edit)" pass \
  Edit "$EXISTING_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+target-in-diff → pass (in-flight Write)" pass \
  Write "$EXISTING_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# Untracked file also counts as dirty (the file was created this session)
run_case "dirty+protected+untracked-target-in-status → pass" pass \
  Edit "$FAKE_ROOT/src/new-untracked.py" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=?? src/new-untracked.py"

# ---------------------------------------------------------------------------
# PASS: planning / retrospect artifact paths
# ---------------------------------------------------------------------------

# /tmp/ scratch files are not inside a git repo → fail-open at get_repo_root.
run_case "dirty+protected+/tmp/ target → pass (fail-open: not in repo)" pass \
  Edit "/tmp/planning-draft.py" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=NONE" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+.omc/plans/ target → pass" pass \
  Write "$FAKE_ROOT/.omc/plans/draft.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+.claude/projects/ target → pass" pass \
  Write "$HOME/.claude/projects/some-project/memory/note.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: docs-only files (default skip rule)
# ---------------------------------------------------------------------------

run_case "dirty+protected+README.md → pass (docs skip)" pass \
  Edit "$FAKE_ROOT/README.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+CHANGELOG.md → pass (docs skip)" pass \
  Edit "$FAKE_ROOT/CHANGELOG.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "dirty+protected+docs/guide.md → pass (docs dir skip)" pass \
  Edit "$FAKE_ROOT/docs/guide.md" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: PRAXIS_PBGUARD_SKIP=1 opt-out
# ---------------------------------------------------------------------------

run_case "dirty+protected+SKIP=1 → pass" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS" \
  "PRAXIS_PBGUARD_SKIP=1"

# ---------------------------------------------------------------------------
# PASS: non-Edit/Write/NotebookEdit tools → not in scope
# ---------------------------------------------------------------------------

run_case "tool_name=Bash → pass" pass \
  Bash "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

run_case "tool_name=Read → pass" pass \
  Read "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: not in a git repo → fail-open
# ---------------------------------------------------------------------------

run_case "not-a-git-repo → pass (fail-open)" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=NONE" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: detached HEAD → fail-open
# ---------------------------------------------------------------------------

run_case "detached-HEAD → pass (fail-open)" pass \
  Edit "$NEW_FILE" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=HEAD" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# PASS: malformed stdin → fail-open
# ---------------------------------------------------------------------------

malformed_test() {
  local name="malformed stdin → pass (fail-open)"
  local out_file err_file
  out_file=$(mktemp); err_file=$(mktemp)
  echo "not-valid-json" | "$HOOK" >"$out_file" 2>"$err_file"
  local rc=$?
  local out
  out=$(cat "$out_file"); rm -f "$out_file" "$err_file"
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
    echo "PASS [pass] $name"; ((PASS++))
  else
    echo "FAIL [pass] $name (rc=$rc, stdout=$([ -n "$out" ] && echo non-empty || echo empty))"
    ((FAIL++)); FAILED_NAMES+=("$name")
  fi
}
malformed_test

# Empty command (no file_path) → fail-open
run_case "empty file_path → pass (fail-open)" pass \
  Edit "" \
  "PRAXIS_PBGUARD_TEST_REPO_ROOT=$FAKE_ROOT" \
  "PRAXIS_PBGUARD_TEST_BRANCH=main" \
  "PRAXIS_PBGUARD_TEST_STATUS=$DIRTY_STATUS"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "${#FAILED_NAMES[@]}" -gt 0 ]; then
  echo "Failed cases:"
  for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
exit 0
