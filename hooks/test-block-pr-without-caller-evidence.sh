#!/usr/bin/env bash
# test-block-pr-without-caller-evidence.sh — coverage for the caller-chain gate
#
# Synthesizes Claude Code PreToolUse(Bash) payloads and asserts:
#   block → exit 2 + stderr non-empty
#   pass  → exit 0 + stderr empty
#
# Usage: bash hooks/test-block-pr-without-caller-evidence.sh
# Exit:  0 = all pass; 1 = at least one fail

set +e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/block-pr-without-caller-evidence.sh"

if [ ! -x "$HOOK" ]; then
  echo "FAIL: hook not executable: $HOOK" >&2
  exit 1
fi

PASS=0; FAIL=0; FAILED_NAMES=()

run_case() {
  local name="$1" expected="$2" tool_name="$3" command="$4"
  local payload err_file rc
  payload=$(python3 -c '
import json, sys
print(json.dumps({
    "tool_name": sys.argv[1],
    "tool_input": {"command": sys.argv[2]},
}))' "$tool_name" "$command")
  err_file=$(mktemp)
  echo "$payload" | "$HOOK" >/dev/null 2>"$err_file"
  rc=$?
  local err_content
  err_content=$(cat "$err_file"); rm -f "$err_file"

  local ok=1
  if [ "$expected" = "block" ]; then
    [ "$rc" -eq 2 ] && [ -n "$err_content" ] || ok=0
  else
    [ "$rc" -eq 0 ] && [ -z "$err_content" ] || ok=0
  fi

  if [ "$ok" -eq 1 ]; then
    echo "PASS [$expected] $name"; ((PASS++))
  else
    echo "FAIL [$expected→rc=$rc,stderr=$([ -n "$err_content" ] && echo non-empty || echo empty)] $name"
    ((FAIL++)); FAILED_NAMES+=("$name")
  fi
}

# ---------------------------------------------------------------------------
# BLOCK cases — no Caller chain verified: line
# ---------------------------------------------------------------------------

run_case "no caller line" block Bash \
  'gh pr create --title "fix: something" --body "## Summary\nsome fix\n\nCloses #10"'

run_case "empty body" block Bash \
  'gh pr create --title "feat: add thing" --body ""'

run_case "caller line value empty" block Bash \
  'gh pr create --body "Caller chain verified:   "'

run_case "marker inside closed fence" block Bash \
  'BODY=$(cat <<'"'"'EOF'"'"'
```
Caller chain verified: inside fence
```
some content
EOF
)
gh pr create --body "$BODY"'

run_case "marker inside unclosed fence" block Bash \
  'BODY=$(cat <<'"'"'EOF'"'"'
```
Caller chain verified: unclosed fence
EOF
)
gh pr create --body "$BODY"'

run_case "non-bash tool ignored but gh still blocked" block Bash \
  'gh pr create --title "fix: x" --body "no marker here"'

# ---------------------------------------------------------------------------
# PASS cases — Caller chain verified: line present
# ---------------------------------------------------------------------------

run_case "grep summary" pass Bash \
  'gh pr create --body "Caller chain verified: grep found 3 callers in src/ -- Closes #10"'

run_case "new symbol whitelist" pass Bash \
  'gh pr create --body "Caller chain verified: new symbol, no caller expected"'

run_case "planned caller whitelist" pass Bash \
  'gh pr create --body "Caller chain verified: planned caller in #200"'

run_case "NA docs-only" pass Bash \
  'gh pr create --body "Caller chain verified: N/A -- docs-only change"'

run_case "case insensitive" pass Bash \
  'gh pr create --body "caller chain verified: grep found 0 external callers"'

run_case "short -b flag" pass Bash \
  'gh pr create -b "Caller chain verified: new symbol, no caller expected"'

run_case "VAR assignment heredoc" pass Bash \
  'BODY=$(cat <<'"'"'EOF'"'"'
Caller chain verified: grep found 2 callers
EOF
)
gh pr create --body "$BODY"'

# ---------------------------------------------------------------------------
# PASS cases — allow conditions
# ---------------------------------------------------------------------------

run_case "cross-project --repo" pass Bash \
  'gh pr create --repo other-org/other-repo --body "no marker needed"'

run_case "cross-project -R" pass Bash \
  'gh pr create -R other-org/repo --body "no marker"'

run_case "--help passthrough" pass Bash \
  'gh pr create --help'

run_case "-h passthrough" pass Bash \
  'gh pr create -h'

run_case "template without body" pass Bash \
  'gh pr create --template pull_request_template.md'

run_case "not a pr create" pass Bash \
  'gh pr list --state open'

run_case "not gh at all" pass Bash \
  'git push origin main'

run_case "non-Bash tool" pass Edit \
  'gh pr create --body "no marker"'

run_case "env wrapper transparent" pass Bash \
  'env GH_TOKEN=xyz gh pr create --body "Caller chain verified: new symbol, no caller expected"'

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
