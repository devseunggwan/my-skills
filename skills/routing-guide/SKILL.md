---
name: routing-guide
description: >
  Skill, agent, hook routing decision tree. Component responsibilities (SRP),
  unified Plan/Execute/Verify/Deliver/Debug routing tables, agent delegation
  by complexity tier, model routing rules (haiku/sonnet/opus), and OMC mode
  keywords. Auto-loads when user asks about which skill/agent/model to use,
  or when routing decisions are needed.
  Triggers on "어떤 skill", "어떤 agent", "어떤 모델", "which skill",
  "which agent", "which model", "delegate", "subagent", "ralph", "autopilot",
  "ultrawork", "ecomode", "model routing", "haiku/sonnet/opus", "context7",
  "deep-dive", "deep-interview".
---

# Routing Guide

> **Single source of truth for skill/agent/model routing across all repos. Auto-loads on routing-related triggers; CLAUDE.md retains the 1-line entry point.**

## Component Responsibilities (SRP)

| Component | Role | Example |
|-----------|------|---------|
| **Hook** | Side effects, automation | worktree-guard, test-reporter |
| **Skill** | Knowledge injection | `praxis:*`, `oh-my-claudecode:*`, project-specific skills |
| **Subagent** | Deep reasoning, specialized work | architect, planner, executor |

## Skill & Agent Routing (Unified Decision Tree)

> One request → one path. Match conditions top-to-bottom; first match wins.
> Subagents protect the main context window — delegate actively, one objective per agent, multiple in parallel for complex problems.

### Plan (decide what/how)

| Condition (match top-to-bottom) | Skill/Agent | Notes |
|---------------------------------|-------------|-------|
| Requirements ambiguous (no files/criteria) | `omc:deep-interview` | Socratic, math-gated |
| Investigation + requirements | `omc:deep-dive` | trace → interview |
| Generic planning | `omc:plan` | optional interview |
| Project-specific planning | see project CLAUDE.md | hub:*, praxis:*, etc. |

### Execute (write code)

| Condition | Skill/Mode | Notes |
|-----------|-----------|-------|
| Setup from scratch (issue+branch+worktree) | manual (`gh issue create` + `git worktree add`) | follow Issue-Driven Worktree Workflow |
| Full-cycle autonomous (plan→code→QA) | `omc:autopilot` | includes ralph+ultrawork |
| Persist until done | `omc:ralph` | loop with verification |
| 5+ independent parallel tasks | `omc:ultrawork` | no persistence |
| Coordinated agent team | `omc:team` | native Claude Code |
| Documentation lookup | `context7` | library docs |

### Verify (mandatory before completion)

Before any completion claim, run the project's tests + lint and paste the actual output. See **Verification Before Completion** for the evidence contract. No skill wraps this — same-turn evidence in the assistant message is what the Stop hook gates on.

### Deliver (PR → merge → cleanup)

| Condition | Skill | Notes |
|-----------|-------|-------|
| Project-specific review/PR | see project CLAUDE.md | hub:code-review, hub:create-hub-pr, etc. |
| Branch cleanup after merge | manual (`gh pr merge --squash --delete-branch`, `git worktree remove`, `git branch -D`) | trivial, no skill wrapping |

### Debug (investigate problems)

| Condition | Skill/Agent | Notes |
|-----------|-------------|-------|
| Bug / test failure | read stack trace + `omc:debugger` agent if non-trivial | direct diagnosis, no enforced phase ceremony |
| Causal tracing (why did X happen) | `omc:trace` | 3-lane hypothesis |
| Deep investigation + spec | `omc:deep-dive` | trace + interview |
| OMC session diagnosis | `omc:debug` | session/runtime only |

### Agent Delegation (within execution)

| Complexity | Model | Agent Examples |
|------------|-------|---------------|
| Simple (search, lookup) | haiku | `explore`, `executor-low`, `code-reviewer-low`, `architect-low` |
| Standard (implement, review) | sonnet | `executor`, `explore-medium` |
| Complex (design, security, incident) | opus | `architect`, `explore-high`, `executor-high`, `code-reviewer`, `security-reviewer` |
| **Default** | **sonnet** | |

### Override Rules (keyword conflict resolution)

> When a keyword triggers multiple skills, these rules determine priority.

| Keyword | Priority Skill | Alternative (explicit only) |
|---------|---------------|---------------------------|
| `plan` | project planner skill (see project CLAUDE.md) | `omc:plan` (generic context) |

### OMC Mode Keywords

| Keyword | Effect |
|---------|--------|
| `plan` | Start planning interview (routes via Override Rules) |
| `autopilot` / `ultrapilot` | Autonomous implementation (workflow steps still apply) |
| `ralph` | Persistence loop — don't stop until verified complete |
| `ulw` / `ultrawork` | Maximum parallel execution |
| `eco` / `ecomode` | Token-efficient parallel execution |
| `stop` / `cancel` | Cancel any active OMC mode |

## Model Routing Rules (MANDATORY)

> **Cost-aware model selection is NOT optional. Opus-for-everything wastes 80%+ of API budget.**

| Tier | Model | When to Use | Budget |
|------|-------|-------------|--------|
| **Low** | `haiku` | File search, code lookup, README edit, worktree cleanup, status check, simple rename | $0.01/task |
| **Medium** | `sonnet` | Feature implementation, test writing, code review triage, PR creation, bug fix, refactoring | $0.05/task |
| **High** | `opus` | Architecture decision, complex debugging, security review, production incident, multi-repo design | $0.25/task |

**Routing signals (auto-detect):**
- Keywords `find`, `search`, `list`, `status`, `cleanup`, `rename`, `move` → **haiku**
- Keywords `implement`, `add`, `fix`, `test`, `review`, `refactor` → **sonnet**
- Keywords `architect`, `design`, `security`, `incident`, `debug.*race`, `system.*design` → **opus**
- **Default: sonnet** (NOT opus)

**cmux orchestrator integration:**
When spawning workers via `cmux new-workspace --command "claude -p ..."`, always include `--model <tier>` based on task complexity. Never default to opus for batch workers.

**cmux environment rules:**
- **`cwt`**: user shell function (`git worktree add` + GUI workspace open). AI must NOT call directly (GUI window). Run `git worktree add` then prefer `/cmux-delegate` (AI-callable) over instructing user to run `cwt`.
- **`cmux.json`**: project-root file with cmux command palette entries. Do not delete/overwrite/reformat — preserve existing entries when adding.
- **`cmux claude-hook` in settings.json**: `~/.claude/settings.json` hooks contain `cmux claude-hook` entries (session-start, prompt-submit, stop, notification). When modifying settings.json hooks, always preserve these entries.

## Quick Reference

| Decision | Default |
|----------|---------|
| Generic plan | `omc:plan` |
| Investigation needed first | `omc:deep-dive` |
| Persist until done | `omc:ralph` |
| 5+ parallel tasks | `omc:ultrawork` |
| Library docs | `context7` |
| Model tier | `sonnet` (NOT opus) |
| Bug diagnosis | read stack trace + `omc:debugger` |

## Integration

- **Entry point**: triggered on routing-decision keywords or "which skill/agent/model" questions; CLAUDE.md keeps a 1-line pointer.
- **Pairs with**: project-level CLAUDE.md (hub:* / project-specific routing tables override generic), `pr-workflow` skill (PR-specific routing).
