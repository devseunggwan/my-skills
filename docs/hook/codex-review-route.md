# UserPromptSubmit Codex Review Worktree Disambiguation

`hooks/codex-review-route.sh` fires on every `UserPromptSubmit` event and
emits an `additionalContext` warning when the user invokes `/codex:review`
in a multi-worktree repository.

### Why this exists

`/codex:review` (owned by the external `openai-codex` plugin) executes its
companion script through Claude Code's Bash tool, whose cwd resets to the
session root between calls. In a multi-worktree session — common when a
parent worktree holds `main` and a sibling worktree holds an issue branch —
the companion's `git diff` runs from the parent cwd, not the issue
worktree. The result is an empty or wrong-target review.

`praxis:codex-review-wrap` solves this by enumerating worktrees, prompting
for explicit selection, and delegating to `/codex:review` with the correct
cwd. But users routinely forget to use it and reach for `/codex:review`
directly. This hook detects that pattern and primes Claude to redirect.

### What is warned

Hook emits `additionalContext` only when **all** the following hold:

| Gate | Condition |
|------|-----------|
| Prompt prefix | `/codex:review` or `/codex-review` (whitespace-separated args allowed) |
| Worktree count | `git worktree list --porcelain` reports `>= 2` non-bare worktrees |
| jq available | Hook fail-opens silently when `jq` is missing |

False-positive guards:

| Input | Action |
|-------|--------|
| `/codex:reviews` (trailing char) | silent — regex requires whitespace or end-of-line after `review` |
| `/codex:review-thing` (hyphenated suffix) | silent — same guard |
| `please /codex:review later` (mid-sentence) | silent — regex anchored to start-of-prompt |
| `/codex:status` (different command) | silent |
| Single-worktree repo | silent — bare invocation works correctly |
| Bare repo + 1 linked worktree | silent — `bare` blocks excluded from the count, only the linked worktree is active |
| Not a git repo | silent — `git worktree list` returns nothing |
| Empty prompt | silent |

### Response

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "⚠️ Multi-worktree detected ... ask the user to run /praxis:codex-review-wrap ..."
  }
}
```

Claude reads the `additionalContext` alongside the user prompt and is
expected to redirect the user to the wrapper rather than dispatch the
codex companion against the wrong cwd. The hook does **not** block the
prompt — Claude can still proceed if the user has explicitly confirmed
the target worktree in the same turn.

### Why warn instead of block

Blocking would cause false positives in legitimate single-target reviews
where the user has already run `cd <target>` mentally / explicitly. The
warning gives Claude the discretion to redirect or proceed, which matches
how the rest of the praxis hook suite handles similar discretionary
escalations (memory-hint emits hints, side-effect-scan asks rather than
denies).

### Tests

```bash
bash tests/test_codex_review_route.sh
```

Covers 14 cases: 4 warn paths (bare, with flag, with `--model`,
hyphenated form), 8 silent paths (single-worktree, plain text, different
slash command, false-positive trailing chars, empty prompt, hyphenated
suffix, mid-sentence mention, bare-repo + 1 linked worktree), 2 fail-safe
paths (malformed JSON, non-git cwd). Worktree state is fixtured via
temporary `git init` (and `git init --bare` for the bare-repo case) to
keep tests isolated from the running praxis tree.
