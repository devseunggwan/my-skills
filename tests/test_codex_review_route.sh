#!/bin/bash
# test_codex_review_route.sh — coverage for hooks/codex-review-route.sh
#
# Synthesizes Claude Code UserPromptSubmit hook payloads and asserts:
#   warn   → exit 0 + stdout contains JSON additionalContext substring
#   silent → exit 0 + stdout empty
#
# Multi-worktree state is simulated by running the hook from inside a
# temporary repo with N synthesized worktrees, NOT against the real
# praxis tree (test isolation).
#
# Usage: bash tests/test_codex_review_route.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$ROOT_DIR/hooks/codex-review-route.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0
FAIL=0
FAILED_NAMES=()

# --- multi-worktree fixture --------------------------------------------------
make_multi_wt_repo() {
  local base="$1"
  mkdir -p "$base"
  cd "$base" || return 1
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test"
  echo "x" > a.txt
  git add a.txt
  git commit -qm "init"
  # add a second worktree (counts as 2 total: base + sibling)
  git worktree add -q -b feat-side "$base/../feat-side" >/dev/null 2>&1
  cd - >/dev/null || true
}

# --- single-worktree fixture -------------------------------------------------
make_single_wt_repo() {
  local base="$1"
  mkdir -p "$base"
  cd "$base" || return 1
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test"
  echo "y" > b.txt
  git add b.txt
  git commit -qm "init"
  cd - >/dev/null || true
}

# --- bare + 1 linked worktree fixture ---------------------------------------
# Reproduces the false-positive case: `git worktree list --porcelain` shows
# 2 `worktree <path>` lines (bare repo + 1 linked), but only the linked one
# is an active non-bare worktree. The hook must count it as 1 and stay
# silent on /codex:review invocations.
make_bare_plus_linked_repo() {
  local base="$1"
  mkdir -p "$base"
  local seed="$base/_seed"
  mkdir -p "$seed"
  ( cd "$seed" \
      && git init -q -b main \
      && git config user.email "test@example.com" \
      && git config user.name "Test" \
      && echo "x" > a.txt \
      && git add a.txt \
      && git commit -qm "init" )
  git clone -q --bare "$seed" "$base/bare" 2>/dev/null
  ( cd "$base/bare" && git worktree add -q "$base/linked" main 2>/dev/null )
}

run_case() {
  local name="$1" expectation="$2" cwd="$3" prompt="$4"

  local payload
  payload=$(python3 -c '
import json, sys
print(json.dumps({"prompt": sys.argv[1], "session_id": "test-sid"}))' "$prompt")

  local out_file
  out_file=$(mktemp)
  ( cd "$cwd" && echo "$payload" | "$HOOK" ) > "$out_file" 2>/dev/null
  local rc=$?
  local out
  out=$(cat "$out_file")
  rm -f "$out_file"

  local ok=1
  case "$expectation" in
    silent)
      [ "$rc" -eq 0 ] || ok=0
      [ -z "$out" ]   || ok=0
      ;;
    warn)
      [ "$rc" -eq 0 ] || ok=0
      case "$out" in
        *"codex-review-wrap"*"additionalContext"*) ;;
        *"additionalContext"*"codex-review-wrap"*) ;;
        *) ok=0 ;;
      esac
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
    echo "FAIL  [$name] expectation=$expectation rc=$rc stdout=${out:-<empty>}"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}

# --- setup fixture repos -----------------------------------------------------
TMPROOT=$(mktemp -d)
MULTI="$TMPROOT/multi"
SINGLE="$TMPROOT/single"
BARE_LINKED="$TMPROOT/bare-plus-linked"

make_multi_wt_repo "$MULTI"
make_single_wt_repo "$SINGLE"
make_bare_plus_linked_repo "$BARE_LINKED"

# Sanity check: verify raw worktree-line counts (NOT the hook's filtered count)
multi_count=$(cd "$MULTI" && git worktree list --porcelain 2>/dev/null | awk '/^worktree /' | wc -l | tr -d ' ')
single_count=$(cd "$SINGLE" && git worktree list --porcelain 2>/dev/null | awk '/^worktree /' | wc -l | tr -d ' ')
bare_raw_count=$(cd "$BARE_LINKED/linked" && git worktree list --porcelain 2>/dev/null | awk '/^worktree /' | wc -l | tr -d ' ')
echo "fixture: multi=$multi_count, single=$single_count, bare-plus-linked raw=$bare_raw_count (hook should filter to 1)"

# --- /codex:review trigger paths --------------------------------------------
run_case "1 warn: bare /codex:review in multi-worktree"          warn   "$MULTI"  "/codex:review"
run_case "2 warn: /codex:review with --background flag"           warn   "$MULTI"  "/codex:review --background"
run_case "3 warn: /codex:review --model opus"                     warn   "$MULTI"  "/codex:review --model opus"
run_case "4 warn: /codex-review (hyphenated)"                     warn   "$MULTI"  "/codex-review"

# --- silent paths ------------------------------------------------------------
run_case "5 silent: single-worktree repo"                          silent "$SINGLE" "/codex:review"
run_case "6 silent: prompt is plain text, not slash command"       silent "$MULTI"  "please review the changes"
run_case "7 silent: different slash command"                       silent "$MULTI"  "/codex:status"
run_case "8 silent: /codex:reviews (false-positive guard)"         silent "$MULTI"  "/codex:reviews"
run_case "9 silent: empty prompt"                                  silent "$MULTI"  ""
run_case "10 silent: /codex:review-thing trailing chars"           silent "$MULTI"  "/codex:review-thing"
run_case "11 silent: prompt mentions /codex:review mid-sentence"   silent "$MULTI"  "use /codex:review later"

# --- bare-repo + linked worktree (false-positive guard) ---------------------
run_case "11b silent: bare repo + 1 linked worktree counts as 1"   silent "$BARE_LINKED/linked" "/codex:review"

# --- malformed input fail-safe ----------------------------------------------
malformed_json_test() {
  local name="12 silent: malformed JSON stdin"
  local out_file
  out_file=$(mktemp)
  ( cd "$MULTI" && echo "not-valid-json" | "$HOOK" ) > "$out_file" 2>/dev/null
  local rc=$?
  local out
  out=$(cat "$out_file")
  rm -f "$out_file"
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
    echo "PASS  [$name]"
    PASS=$((PASS + 1))
  else
    echo "FAIL  [$name] rc=$rc stdout=${out:-<empty>}"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}
malformed_json_test

not_in_repo_test() {
  local name="13 silent: cwd not a git repo"
  local nogit
  nogit=$(mktemp -d)
  local payload
  payload=$(python3 -c '
import json, sys
print(json.dumps({"prompt": "/codex:review", "session_id": "test-sid"}))')
  local out_file
  out_file=$(mktemp)
  ( cd "$nogit" && echo "$payload" | "$HOOK" ) > "$out_file" 2>/dev/null
  local rc=$?
  local out
  out=$(cat "$out_file")
  rm -f "$out_file"
  rm -rf "$nogit"
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
    echo "PASS  [$name]"
    PASS=$((PASS + 1))
  else
    echo "FAIL  [$name] rc=$rc stdout=${out:-<empty>}"
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name")
  fi
}
not_in_repo_test

# --- cleanup ---------------------------------------------------------------
rm -rf "$TMPROOT"

# --- summary -----------------------------------------------------------------
echo ""
echo "Passed: $PASS  Failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed tests:"
  for t in "${FAILED_NAMES[@]}"; do
    echo "  - $t"
  done
  exit 1
fi
exit 0
