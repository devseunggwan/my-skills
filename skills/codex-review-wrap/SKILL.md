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

### Step 4: Delegate to /codex:review

Change working directory to the selected worktree path, then invoke the Skill:

```
cd {selected_path}
Skill("codex:review", args="{{ARGUMENTS}}")
```

`{{ARGUMENTS}}` passes any flags (e.g. `--model opus`) through unchanged.

If `codex:review` skill is not available (plugin not installed), output:
```
Error: /codex:review skill 을 찾을 수 없습니다.
openai-codex plugin 이 설치되어 있는지 확인하세요.
```
and abort.

## Error Handling

| Situation | Action |
|-----------|--------|
| `git worktree list` fails (not a git repo) | Abort: "git worktree list 실패 — git 저장소인지 확인하세요." |
| All worktrees are bare | Treat as Case A (single effective target) using cwd |
| User selects "취소" | Abort silently with one-line message |
| codex:review skill not found | Abort with install hint |

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

[Step 4] cd /Users/dev/project-wt/windmill-hub-1539 → Skill("codex:review")
```

## Limitations

- Does not modify `/codex:review` itself — users who call it directly still get the old behaviour
- Subshell `cd` does not persist after skill execution — cwd is not mutated in the parent session
