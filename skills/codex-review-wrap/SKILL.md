---
name: codex-review-wrap
description: >
  Worktree-aware wrapper for /codex:review. When multiple active worktrees exist,
  forces explicit selection before delegating to Codex. Prevents silent cwd mismatch
  between the current shell location and the intended review target.
  Triggers on "codex review", "review codex", "safe review", "/codex-review-wrap".
---

# codex-review-wrap

## Overview

`/codex:review` selects the working tree based on cwd. When multiple worktrees
are active — the common case mid-session after a merge or context switch — cwd
drifts away from the intended target without warning.

This wrapper intercepts before Codex runs:

1. Lists all active worktrees via `git worktree list`
2. If **≥ 2 worktrees** are active → `AskUserQuestion` forces explicit selection
3. If **exactly 1** → proceeds automatically (same as current `/codex:review` behaviour)
4. Delegates to `/codex:review` with the confirmed worktree as cwd

## When to Use

- Before calling `/codex:review` from any multi-worktree project
- When the session cwd differs from the worktree you just finished working in
- Triggers: "codex review", "review codex", "safe review", "/codex-review-wrap"

## Inputs

```
/codex-review-wrap
/codex-review-wrap --model opus
```

Optional `--model` is forwarded to `/codex:review` unchanged.

## Process

### Step 1: Enumerate Active Worktrees

```bash
git worktree list --porcelain
```

Parse output into a list of `{path, branch, HEAD, detached}` entries.
Filter out entries with the explicit `bare` marker — they have no working tree.
Keep detached worktrees (no `branch` line but no `bare` marker) as valid review targets.

Expected output shape per entry:
```
worktree /path/to/repo
HEAD <sha>
branch refs/heads/<branch-name>

worktree /path/to/repo-wt/feature-xyz
HEAD <sha>
branch refs/heads/feature-xyz

worktree /path/to/repo-wt/detached-xyz
HEAD <sha>
detached
```

### Step 2: Disambiguation Gate

**Case A — exactly 1 non-bare worktree:**

Skip selection. Proceed directly to Step 3 using cwd.

**Case B — 2 or more non-bare worktrees:**

Call `AskUserQuestion` with:

```
title: "어느 worktree 를 review 할까요?"
question: "현재 활성 worktrees:\n{numbered list}\n\n번호를 입력하거나 경로를 직접 입력하세요."
options: [{path}: ({branch}) for each worktree] + ["취소"]
```

Wait for user response. If "취소" or no selection → abort with message:
"Review 취소됨. 대상을 선택하지 않았습니다."

### Step 3: Confirm Selected Target

Show a one-line summary before delegating:

```
Review target: {selected_path} (branch: {branch})
```

If the selected path differs from cwd, note it explicitly:
```
⚠ cwd ({cwd}) ≠ review target ({selected_path}) — codex:review 를 선택된 경로에서 실행합니다.
```

### Step 4: Run codex-companion against the selected worktree

`/codex:review` declares `disable-model-invocation: true`, so it cannot be
called via `Skill(...)` from inside another skill. Invoke the underlying
companion script directly instead — this mirrors what `/codex:review` does
in its own foreground flow.

#### 4a. Resolve the codex-companion.mjs path

Read the install path from the canonical Claude Code plugin manifest:

```bash
manifest="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/installed_plugins.json"
install_path=$(jq -r '.plugins["codex@openai-codex"][0].installPath // empty' "$manifest")
companion="$install_path/scripts/codex-companion.mjs"
```

If `$companion` is empty or the file does not exist:

1. Output: `"⚠ codex-companion.mjs not found — openai-codex plugin may not be installed."`
2. Offer alternatives via `AskUserQuestion`:
   - **`oh-my-claudecode:code-reviewer`** — Claude-based code review (equivalent quality)
   - **`Manual`** — output the diff for direct inspection; skip automated review
   - **`Cancel`** — abort the review
3. Act on the selection:
   - `oh-my-claudecode:code-reviewer` → `Skill("oh-my-claudecode:code-reviewer")` with cwd set to `{selected_path}`
   - `Manual` → run `git diff origin/<base-branch>..HEAD` in `{selected_path}` and exit
   - `Cancel` → abort silently with one-line message

The script derives its own ROOT_DIR via `import.meta.url`, so passing the
absolute script path to `node` is sufficient — `CLAUDE_PLUGIN_ROOT` does
not need to be set.

#### 4b. Run the review

Change working directory to the selected worktree, then invoke the
companion. `{{ARGUMENTS}}` passes any flags (e.g. `--model opus`,
`--wait`, `--background`) through unchanged.

```bash
cd {selected_path}
node "{resolved_companion_path}" review "{{ARGUMENTS}}"
```

Return the script's stdout **verbatim** — do not paraphrase, summarize, or
add commentary. This matches `/codex:review`'s contract.

If `{{ARGUMENTS}}` includes `--background`, run via `Bash(..., run_in_background: true)`
and tell the user: "Codex review started in the background. Check `/codex:status` for progress."

## Error Handling

| Situation | Action |
|-----------|--------|
| `git worktree list` fails (not a git repo) | Abort: "git worktree list 실패 — git 저장소인지 확인하세요." |
| All worktrees are bare | Treat as Case A (single effective target) using cwd |
| User selects "취소" | Abort silently with one-line message |
| `installed_plugins.json` missing or codex entry absent | Offer alternatives via `AskUserQuestion` (Step 4a) |
| Resolved `codex-companion.mjs` path does not exist | Offer alternatives via `AskUserQuestion` (Step 4a) |

## Example Flow

```
user: /codex-review-wrap

[Step 1] git worktree list result:
  0: /Users/dev/project/laplace-dev-hub       (main)
  1: /Users/dev/project-wt/windmill-hub-1539  (issue-1539-windmill-runner)

[Step 2] AskUserQuestion →
  "어느 worktree 를 review 할까요?"
  0: /Users/dev/project/laplace-dev-hub (main)
  1: /Users/dev/project-wt/windmill-hub-1539 (issue-1539-windmill-runner)

user selects: 1

[Step 3] Review target: /Users/dev/project-wt/windmill-hub-1539 (branch: issue-1539-windmill-runner)
  ⚠ cwd (/Users/dev/project/laplace-dev-hub) ≠ review target

[Step 4] cd /Users/dev/project-wt/windmill-hub-1539
         → node {install_path}/scripts/codex-companion.mjs review
```

## Limitations

- Does not modify `/codex:review` itself — users who call it directly still get the old behaviour
- Subshell `cd` does not persist after skill execution — cwd is not mutated in the parent session
