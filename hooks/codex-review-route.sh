#!/bin/bash
# codex-review-route.sh — UserPromptSubmit hook
#
# When the user invokes `/codex:review` in a multi-worktree environment, the
# bare command runs through Claude Code's Bash tool whose cwd resets to the
# session root (typically the parent/main worktree). The codex companion
# script then computes its diff from that cwd, often producing an empty or
# wrong-target review when the user actually wanted to review a sibling
# issue worktree.
#
# This hook emits an `additionalContext` warning whenever:
#   1. The user prompt starts with `/codex:review` (or `/codex-review`)
#   2. AND `git worktree list` reports >= 2 active (non-bare) worktrees
#
# The warning instructs Claude to redirect the user to
# `/praxis:codex-review-wrap` (which forces explicit worktree selection
# before delegating). If only one worktree exists, the hook stays silent —
# bare invocation is correct in that case.
#
# Fail-safe: jq missing, malformed JSON, no git repo, or any unexpected
# error all exit 0 silently. The hook never blocks a prompt.

set +e

# jq guard — Claude Code session must keep functioning even without jq
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)

if [ -z "$PROMPT" ]; then
  exit 0
fi

# Match `/codex:review` or `/codex-review`, optionally followed by args.
# Trailing space requirement avoids false positives on `/codex:reviews`
# or `/codex:review-thing` (defensive — none currently exist, but cheap).
if ! [[ "$PROMPT" =~ ^/codex(:|-)review([[:space:]]|$) ]]; then
  exit 0
fi

# Count active non-bare worktrees. `git worktree list --porcelain` emits
# one `worktree <path>` line per entry (bare entries are followed by a
# `bare` line; we count `worktree` lines and let bare entries resolve
# on the consumer side — bare worktrees are rare and the wrapper handles
# them correctly).
WT_COUNT=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /' | wc -l | tr -d ' ')

if ! [[ "$WT_COUNT" =~ ^[0-9]+$ ]]; then
  exit 0
fi

if [ "$WT_COUNT" -lt 2 ] 2>/dev/null; then
  exit 0
fi

read -r -d '' MSG <<EOF
⚠️ Multi-worktree detected (${WT_COUNT} active worktrees) for a /codex:review invocation.

Bare /codex:review uses the Bash tool's session-default cwd, which often differs from the worktree the user actually wants to review — producing an empty or wrong-target diff.

Recommended action: instead of dispatching /codex:review directly, ask the user to run /praxis:codex-review-wrap. The wrapper enumerates worktrees, prompts for explicit selection, and delegates to /codex:review with the correct cwd.

If the user explicitly confirms the target worktree in this turn, you may proceed — but state the resolved cwd in your reply so the choice is visible.
EOF

jq -n --arg ctx "$MSG" \
  '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'

exit 0
