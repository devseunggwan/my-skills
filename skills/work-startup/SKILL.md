---
name: work-startup
description: >
  New-work startup discipline. Issue-Driven Worktree Workflow (mandatory phases),
  Pre-Implementation Checklist, Branch Base Rules, Pre-merge Worktree Precondition,
  Worktree Recovery rules, and GitHub Issue Hygiene (duplicate search, config-file
  backing repo check, personal/external repo content isolation, authorization gate).
  Auto-loads when starting new work, creating issues, or setting up worktrees.
  Triggers on "새 이슈", "새 작업", "이슈 만들", "이슈 생성", "issue create",
  "create issue", "gh issue create", "워크트리", "worktree", "새 브랜치",
  "branch create", "git worktree", "scratchs", "hotfix", "external repo",
  "third-party repo", "open-source", "upstream PR", "config file repo",
  "backing repo", "session resume", "session restore".
---

# Work Startup

> **Single source of truth for new-work setup discipline. Auto-loads on issue/branch/worktree creation triggers; CLAUDE.md retains the 1-line entry point.**

## Issue-Driven Worktree Workflow (MANDATORY)

> **ALL work MUST follow this workflow. NO EXCEPTIONS.**

**BLOCKING REQUIREMENT: Do NOT write any code until this workflow is complete.**

### Required Workflow

| Phase | Steps | Skill |
|-------|-------|-------|
| **Setup** | 1. Create GitHub Issue | project-specific issue skill (e.g., `laplace-dev-hub:create-hub-issue`) |
| | 2. Plan implementation | project-specific planning skill (e.g., `laplace-dev-hub:planning-hub-issue`) |
| | 3-5. Create branch + worktree + cd | `oh-my-claudecode:project-session-manager` |
| | 6. Install dependencies | manual (`npm install` / `pip install`) |
| **Execute** | 7-8. Implement (pick one) | `oh-my-claudecode:ralph` or `oh-my-claudecode:executor` |
| **Verify** | 9. Run tests and lint | manual (project test + lint commands, paste output) |
| | 10. Code review | project-specific review skill (e.g., `laplace-dev-hub:code-review`) |
| **Complete** | 11. Compounding | (add inline PR reference commit — see `pr-workflow` skill) |
| | 12-13. PR -> Merge | project-specific PR skill (e.g., `laplace-dev-hub:create-hub-pr`) |
| | 14. Cleanup | manual (`gh pr merge --squash --delete-branch`, `git worktree remove`, `git branch -D`) |

### Pre-Implementation Checklist

Before writing ANY code, verify:

- [ ] GitHub Issue exists for this task
- [ ] Branch created from latest base branch (`dev`, `main`, or `prod` for hotfix — see Branch Base Rules)
- [ ] Worktree created and currently working inside it
- [ ] Dependencies installed in worktree

**If ANY checkbox is unchecked → STOP and complete the workflow first.**

### Branch Base Rules

| Branch Type | Base | Merge Target | Post-Merge |
|---|---|---|---|
| Feature / Refactor / Docs | `dev` (or `main`) | `dev` | Release via `dev → prod` PR |
| Hotfix | `prod` (or `main`) | `prod` | Reverse-merge `prod → dev` |

### Hotfix Workflow

Hotfix follows the **same full workflow** with one delta: base branch is `prod`, merge target is `prod`. Branch name `hub-{N}-hotfix-{desc}` or `issue-{N}-hotfix-{desc}`. Commit format `fix(scope): description (hotfix)`. Hotfix branches MUST come from `prod` — branching from `dev` risks deploying unintended changes.

### Scratchs Repo Workflow

Scratchs (experiments, learning) follows the same issue-driven workflow with these differences:

- Issues/PRs in `devseunggwan/scratchs` directly (skip Hub-only `create-hub-issue`). `gh label list --repo devseunggwan/scratchs` first.
- Default branch: `main`. Branch pattern `issue-{N}-{type}-{desc}`.
- Code review: self-review via `oh-my-claudecode:code-reviewer`.
- Always merge via PR — no direct commits to main.

## Pre-merge Worktree Precondition

`gh pr merge --squash --delete-branch` 는 post-squash 단계에서 base branch (main / dev / prod) 의 local checkout 을 시도하므로, **base branch 를 소유한 worktree 에서 호출**해야 한다. issue-branch worktree 에서 호출하면 git exclusive-ref guard 가 차단한다:

```
fatal: 'main' is already used by worktree at /Users/.../<main-worktree>
```

호출 전 체크리스트:

1. `git worktree list` 로 base branch 점유 worktree 위치 확인
2. **If `--delete-branch` is included**: remove the PR head branch's worktree first (`git worktree remove <issue-worktree-path>`). The post-merge local branch delete step fails if the branch is still occupied by a worktree — `cannot delete branch 'X' used by worktree at ...`. This happens even when invoked from the base (main) worktree, because the failing branch is the *head*, not the base. After removal, re-run `git worktree list` to confirm before proceeding.
3. `cd <base-worktree-path>` 또는 같은 Bash 호출에 `cd <path> && gh pr merge ...` 체이닝 (Bash 호출 간 cwd reset 함정 회피)
4. 호출이 worktree 충돌로 실패해도 PR 은 remote 에서 머지된 상태일 수 있음 (gh 는 remote 머지 → local sync 순서). 수동 정리: `git worktree remove <path> && git branch -D <branch> && git worktree prune && git pull origin <base>`

## Worktree Recovery — No Clone as Substitute

**NEVER** use `gh repo clone` or `git clone` to recover a lost worktree directory.

- **Recovery path**: `git fetch origin <branch> && git worktree add <path> <branch>`
- **Why clone fails**: a clone creates an independent repo outside the git worktree registry. All subsequent `git worktree list`-based guards become blind to it. Files added inside the clone appear as untracked, and the next session inherits the confusion.
- **Before recovery**: run `git worktree list` to confirm the branch ref exists on remote — if it does, `git worktree add` restores it cleanly.
- **No exceptions**: "it works for now" is not a justification for using clone as recovery.

## GitHub Issue Hygiene

### Duplicate Search Before Creation

> **Before creating any issue: `gh search issues "<keywords>" --repo <repo>` (open AND closed). Ask user if ambiguous. Never create duplicates.**

### Session Context Restoration

When resuming from compacted/restored session, read summary's "Pending Tasks" / "Current Work" thoroughly — never re-execute completed actions.

### Config File Backing Repo Check (MUST)

Before creating an issue related to a config file (e.g., `CLAUDE.md`, `.env`, `settings.json`), verify the file's actual source:

1. `ls -la <file>` — check if it's a symlink and find the target
2. `git -C <target_dir> remote -v` — identify the backing repo
3. Create the issue in the backing repo, not in the project where the file appears

### Personal Repo Content Isolation (MUST)

Never write personal repo names, issue numbers, file paths, or configuration details in company/org-level issues, PRs, or commit messages. If a background explanation is needed, use abstract language (e.g., "internal tooling improvement") — not personal repo references (e.g., `devseunggwan/*`, personal dotfiles paths).

### External / Third-Party Repo Content Isolation (MUST)

When writing issues, PRs, or comments to **any repo outside your own org** (open-source upstreams, personal repos of other developers, vendor repos), strip out internal context entirely:

- **Language**: Write in **English only** — never Korean or any other language used internally.
- **No internal identifiers**: No internal repo names (`laplace-*`, `windmill`, internal product codenames), no internal issue/PR numbers (`Hub #1729`, internal `PR #307`), no internal team/customer names, no internal Slack/Notion/Jira links.
- **No absolute paths**: Never paste worktree paths like `/Users/<name>/projects/...` — replace with abstract placeholders (`<repo>/<path>`).
- **No internal terminology**: No internal tooling names that aren't public (e.g., `hubctl`, internal skill names, internal flywheel jargon). If the upstream needs to know the trigger, describe it generically ("a tooling skill we use creates X cache file").
- **Reproduction**: Reproduce the bug/request using only the upstream's public surface. If reproduction requires internal context, the issue does not belong upstream — file it internally instead.
- **Authorization gate (ABSOLUTE — no exceptions)**: Creating, commenting, editing, closing, reopening, or otherwise writing to **any** issue/PR/discussion on a repo outside your own org **REQUIRES explicit per-action user approval. NEVER under any circumstance proceed without it.** This rule has zero auto-mode override, zero batch override, zero retrospect/cleanup override, zero "the user already approved the parent task" inference, zero "the action is reversible so it's fine" reasoning. The user's general "proceed" / "Execute now" / "go ahead" approvals apply ONLY to internal-org actions. For each individual external-repo write, surface the proposed action explicitly ("This would create/edit/comment on `{owner/repo}#{N}`. Approve?") and wait for an explicit yes. If unsure whether a repo is external, treat it as external. **Strike escalation: a single violation here is a hard CRITICAL strike — repeated violations trigger PreToolUse hook enforcement.**
- **Pre-emptive surfacing requirement**: external-surface write directive (PR comment, issue comment, slack send, notion update, email, status page 등) 를 user 가 발화한 시점에 즉시 AskUserQuestion 으로 per-action 승인 게이트를 surface 한다. staging file (`/tmp/...md`, `.omc/plans/...` 등) Write 도 classifier 가 intent 기준 차단하므로 staging 시도 자체가 비용이다. 시퀀스: (1) directive 인식 → (2) AskUserQuestion 에 게시 내용 미리 보여주며 명시적 승인 받기 → (3) 승인 후에야 staging file Write + 외부 surface mutation. classifier 가 차단할 때까지 기다리지 말고, classifier 가 차단할 필요가 없도록 사전에 처리.
- **Why this rule exists**: Leaking internal repo names, customer references, or absolute paths to external repos causes (a) reputational damage (the org looks unprofessional), (b) confidentiality violations, (c) noise on someone else's repo (their inbox, their triage burden), (d) Korean text on English upstreams is rejected and counted as spam. Treat external-repo writes with the same scrutiny as a public blog post.

## Quick Reference

| Phase | Required action |
|-------|----------------|
| Pre-issue | duplicate search (`gh search issues`); config-file backing repo check |
| Issue create | scope-correct repo (personal vs org vs external); template/labels per project |
| Pre-code | issue exists; branch from latest base; worktree created; deps installed |
| Pre-merge | run from base-branch worktree; remove head worktree first if `--delete-branch` |
| Worktree recovery | `git fetch + git worktree add` — never `git clone` |
| External-repo write | per-action AskUserQuestion approval; English; no internal identifiers/paths/terms |

## Integration

- **Entry point**: triggered on issue/branch/worktree creation keywords or session-resume context; CLAUDE.md keeps a 1-line pointer.
- **Pairs with**: `pr-workflow` skill (post-implementation phases), project-level CLAUDE.md (e.g., `laplace-dev-hub/CLAUDE.md`) for repo-specific issue templates and label conventions.
- **Project-level overrides**: project CLAUDE.md may add Hub-specific scope rules (e.g., `scope:hub` semantics, slash command issue lifecycle) — those apply on top of this skill.
