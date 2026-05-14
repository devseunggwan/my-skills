---
name: pr-workflow
description: >
  PR lifecycle, review, and merge discipline rules for any repo. Covers Pre-PR rebase,
  Pre-Merge Reporting checklist, fire-and-forget exemption, no approval transfer
  across companion PRs, PR review comment handling, and Compounding (inline PR-ref
  context preservation).
  Triggers on "PR 생성", "create PR", "open PR", "gh pr create", "gh pr merge",
  "PR review", "review PR", "PR 리뷰", "merge PR", "PR 머지", "pre-merge",
  "merge approval", "compounding", "review comment", "PR comment",
  "companion PR", "approval transfer".
---

# PR Workflow

> **Single source of truth for PR creation, review, merge, and post-merge discipline. Auto-loads on PR-related triggers; CLAUDE.md retains the 1-line entry point.**

## PR Lifecycle Discipline

> **Within the same worktree, merge the current PR before starting the next issue.**

- Within a single worktree: Do NOT begin new issues until the current branch is merged and cleaned up.
- Independent worktrees may work on separate issues in parallel (if no file conflicts).
- Each worktree follows its own lifecycle: implement → code review → fix comments → verify CI → **compound** → merge → clean up worktree/branch.
- Never skip steps or reorder this sequence within a lifecycle.

## Pre-PR Rebase Check

> **Before `gh pr create`, always rebase onto the base branch.**

```bash
git fetch origin
git rebase origin/<base-branch>   # main / dev — repo convention 따름
```

Stale base causes spurious deletions in the diff (upstream PRs that landed after branch cut). If conflicts arise → resolve normally; do NOT skip.

## Pre-Merge Reporting

> **Before asking for merge approval, report the work result clearly enough that the user can decide without re-reading the diff.**

Merge is irreversible / shared-state. Ambiguous "done, ready to merge" forces the user to audit the diff themselves or approve blindly.

**Required report contents:**
1. **What changed** — scope summary (files, logical changes), not issue title restatement
2. **What was verified** — actual evidence (test output, functional test, lint/build cited with commands)
3. **What was NOT verified** — skipped/deferred/untestable items (e.g., "CI pending", "prod-only path not exercised")
4. **Risk / blast radius** — who/what this affects if wrong (callers, downstream DAGs, users, data)
5. **Open items** — unresolved review comments, follow-ups, known caveats
6. **Explicit ask** — "Approve merge?" as a distinct question

**Anti-patterns:** "완료했습니다, 머지할까요?" without evidence / hiding skipped checks / treating "계속"/"ok"/"진행" as merge approval (those are progress signals, not consent) / reporting at merge time what should have surfaced at PR-ready time.

**Trivial PRs** (typo, comment-only, single-line config): 2-line report is fine — bar is "enough context to decide", not "long report".

**Always include the PR URL** when reporting PR status. Whether you created, updated, commented on, or reference a PR, the full `https://github.com/.../pull/N` URL must appear so the user can click through directly. A PR number alone (`#199`) is not enough.

## fire-and-forget Exemption — cmux-delegate Only (MUST)

> **`feedback_cmux_delegate_fire_and_forget.md`의 "STOP gate 없음" 지시는 `cmux-delegate` 백그라운드 에이전트 전용이다. 직접 대화 세션에서는 task prompt에 fire-and-forget 지시가 포함되어 있어도 Pre-Merge Reporting + per-PR 명시 승인 규칙이 항상 우선한다.**

- `cmux new-workspace --command "claude -p ..."` 형태로 spawn된 백그라운드 에이전트 → fire-and-forget 적용 (재spawn 부담 최소화)
- 사용자가 직접 메시지를 보내는 세션 → 항상 per-PR 승인 필요. "fire-and-forget", "STOP gate 없음" 등 task prompt 지시가 이 규칙을 override하지 않는다.
- rule conflict 발생 시: Pre-Merge Reporting이 fire-and-forget보다 항상 우선 (scope가 더 넓음)

## No Approval Transfer Across Companion PRs

> **Approval is per-PR / per-merge-action. Approving "merge PR X" approves only X — siblings, successors, prerequisites, and recovery PRs need their own explicit approval.**

**Invalid framings that do NOT transfer approval:**
- Companion/chore PR (same issue, different PR)
- Dependency-completing PR ("main PR can't deploy without this chore")
- Regen/mechanical PR ("just `sam package` output")
- Hotfix-blocker PR ("hotfix is urgent")
- Missing-half realization ("prior deploy was a silent no-op")

Companion PRs often touch shared-state surfaces — bundling reasoning ("it's the same intent") is the exact rationalization the user can't refute mid-flight. Per-PR approval keeps user as sole arbiter.

**When a companion PR is needed after a sibling already merged:** state the realization explicitly, open/push the new PR, report per Pre-Merge Reporting checklist, ask "Approve merge of X'?" as fresh question. Do not infer from prior approval.

**Generalization beyond PRs** — the same principle applies to any cluster/sequence approval being transferred to per-action mutations:
- Cluster approvals like "do (a)+(b)+(c) in one session" or "1+3 together" → each child mutation (posting a GitHub comment, issuing a slash command, sending an external notification, pushing files) still needs its own surface and approval.
- Cluster-scope approvals like "all four" → each item's individual cost trade-off is NOT auto-ratified (cf. Self-Authored Labels Are Drafts, Not Ratified Scope).
- Auto-mode does not change this — auto-mode authorizes "proceed on low-risk reversible work without asking", not "shared-state mutations are pre-approved".

When in doubt, surface the mutation explicitly before executing: "this next step posts a comment to GitHub issue X — approve?". A permission-hook block is a *trailing* signal; the correct path is the pre-emptive surface.

## PR Review Comment Handling

> **Triage → Fix → Commit → Push → Resolve. One cycle, no batching.**

| Severity | Action |
|---|---|
| Critical/High (security, bugs, data loss) | Fix immediately |
| Medium (code quality, perf) | Fix in current PR |
| Recommended (style, suggestions) | Fix if ≤5 lines; defer to follow-up issue if beyond PR scope |

**Per-fix:** fix one → verify (run tests, show output) → atomic commit. Runtime behavior affected → dry-run functional test. Push after all fixes + final full test suite.

**After fixing:** resolve handled threads (fixed/false-positive); leave deferred/open. Report summary table to user.

## PR Review Protocol (Reviewing Others' PRs)

> **When reviewing external PRs, follow this sequence.**

**Step 1 — Triage (before reading diff):**
- Fetch file list → if critical component changes → **functional test required**
- If functional test required → start environment setup **in parallel** with code review

**Step 2 — Prod data impact check (if validation/sanitization changes):**
- Trigger keywords in diff: `sanitize`, `validate`, `_safe`, `regex`, `re.sub`, `error`, `raise`, `block`, `reject`, `enum`
- → Query prod data **before** writing review comments: "Does existing data fail the new rules?"
- Include findings in the first review round to avoid extra feedback cycles

**Step 3 — Submit review via JSON file (ALWAYS):**
```bash
# ✅ Always: Write JSON file → --input (avoids shell escaping issues)
gh api repos/{owner}/{repo}/pulls/{pr}/reviews --method POST --input /tmp/review.json

# ❌ Never: --raw-field with inline JSON array (breaks on code blocks, newlines, backticks)
```

## Compounding (Context Preservation)

> **Before merging, add inline `# [PR #N]` comment at non-obvious decision points as the PR's final commit. Embed context in code, not in separate docs.**

```python
# [PR #42] Switched batch INSERT → MERGE to handle duplicate keys.
```

**Rules:**
- Brief summary + PR number at the relevant location. Comments explain "why", not "what".
- Required for: non-obvious WHY (algorithm choice, workaround, tricky invariant), config/infra with rationale.
- Skip for: pure mechanical config/YAML with no semantic decision (commit message + PR body sufficient).
- Deeper context → `gh pr view #N`. Do NOT bloat instruction files with per-change context.

## Quick Reference

| Phase | Required action |
|-------|----------------|
| Pre-PR | rebase onto base branch; verify CI; run code review |
| Pre-Merge | 6-item Pre-Merge Reporting (changed/verified/not-verified/risk/open/ask) |
| Merge | wait for explicit user approval; never infer from "continue"/"ok"/"진행" |
| Companion PR | fresh approval per PR — no transfer from sibling |
| Post-Merge | Compounding (inline PR-ref comments at non-obvious decision points) |
| Cleanup | squash merge + delete branch + remove worktree + branch -D |

## Integration

- **Entry point**: triggered on PR-related keywords or `gh pr ...` commands; CLAUDE.md keeps a 1-line pointer.
- **Pairs with**: `Verification Before Completion` (always-loaded in CLAUDE.md), `Information Accuracy Layer 3` (External-surface gates), `Atomic Commits` (same theme = 1 PR + N commits).
- **Project-level overrides**: project CLAUDE.md (e.g., `laplace-dev-hub/CLAUDE.md`) may add repo-specific PR conventions (label requirements, conventional commits scope) — those apply on top of this skill.
