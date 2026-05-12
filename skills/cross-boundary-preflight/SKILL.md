---
name: cross-boundary-preflight
description: >
  Cross-boundary pre-flight checklist generator. Fires when intent matches:
  port intent (code/config move from project A to project B), cross-repo write
  (gh pr create --repo or gh issue create --repo where target repo differs from
  CLAUDE_PROJECT_DIR), or cross-worktree file copy. Enumerates source/target
  ownership, applicable hook contracts, label conventions, and caller chain
  requirements before the action is attempted.
  Triggers on "cross boundary", "port to", "move to repo", "copy to project",
  "cross-repo pr", "cross-repo issue", "cross-worktree copy",
  "cross-boundary preflight", "pre-flight checklist".
---

# cross-boundary-preflight

## Overview

Five documented session failures share one meta-pattern: a rule existed in
context but had no execution-time retrieval trigger at the action boundary.
Adding more memos to CLAUDE.md has not prevented recurrence — the structural
gap is the absence of a pre-flight gate.

**What this skill does:** intercepts before a cross-boundary action executes,
classifies source and target ownership, enumerates every applicable hook
contract for the combination, and surfaces the checklist via `AskUserQuestion`
so the agent can confirm readiness before the action is attempted.

**The five failure patterns this addresses:**

| # | Surface | Hook / Rule violated |
|---|---------|---------------------|
| 1 | deep-dive Lane 3 synthesis recommended MOVE: personal dotfiles → company repo | Personal repo content isolation + external-repo write authorization gate |
| 2 | Hook implemented in project-local `.claude/hooks/` instead of praxis `hooks/` | Hooks in praxis belong to the praxis repo — not project-local |
| 3 | `gh search ... --state all` | `block-gh-state-all` hook (the flag does not exist) |
| 4 | `gh issue create` with heredoc body | praxis PreToolUse hook rejects heredoc — use `--body-file <path>` |
| 5 | `gh pr create --repo <other>` without caller-evidence line | `block-pr-without-caller-evidence` + external-write authorization gate |

## When to Use

Use proactively whenever the current intent matches any of these:

- **PORT intent** — the agent is about to move or copy code, config, hooks,
  or skills from one project to another (different repo, different worktree,
  different org).
- **CROSS_REPO_WRITE** — a `gh pr create --repo <X>`, `gh issue create --repo <X>`,
  or `gh issue comment` where `<X>` differs from the repo rooted at
  `$CLAUDE_PROJECT_DIR`.
- **CROSS_WORKTREE_COPY** — a file copy (`cp`, `rsync`, `Write`) whose
  destination path is inside a different worktree than the current cwd.
- **GH_CLI_CONTRACT** — intent to run `gh search` with a `--state` flag, or
  to produce an inline heredoc body for `gh issue create` / `gh pr create`.
- **HOOK_LOCATION** — intent to implement or move a praxis hook into a
  project-local `.claude/hooks/` directory.

Triggers: "cross boundary", "port to", "move to repo", "copy to project",
"cross-repo pr", "cross-repo issue", "cross-worktree copy",
"pre-flight checklist"

## Inputs

```
/cross-boundary-preflight
/cross-boundary-preflight "gh pr create --repo devseunggwan/praxis"
/cross-boundary-preflight "move hooks/block-foo.sh to project-local"
```

Optional: a one-line description of the intended action. If omitted, the
skill infers intent from the current conversation context.

## Process

### Step 1: Detect Intent Type

From `{{ARGUMENTS}}` and the current conversation context, classify the
intended action into one or more of these intent types. Multiple types may
apply simultaneously.

| Intent Type | Detection Signal |
|-------------|-----------------|
| `PORT` | "move", "copy", "port", "migrate" + mention of two distinct projects or repos |
| `CROSS_REPO_WRITE` | `gh pr create --repo <X>`, `gh issue create --repo <X>`, `gh issue comment` where `<X>` is explicit and differs from current project repo |
| `CROSS_WORKTREE_COPY` | `cp`, `rsync`, `Write` with destination path inside a different worktree |
| `GH_CLI_CONTRACT` | `gh search` with `--state` flag, or heredoc (`<<EOF`) in a `gh issue create` / `gh pr create` body |
| `HOOK_LOCATION` | intent to write or register a hook in `.claude/hooks/` or project-local settings rather than in the praxis `hooks/` directory |

If no intent type can be classified → emit:
```
No cross-boundary intent detected. Proceeding without pre-flight.
```
and exit (do not call `AskUserQuestion`).

### Step 2: Classify Ownership Axes

For `PORT` and `CROSS_REPO_WRITE` intents, identify:

**Source ownership** (where the artifact currently lives):
- `personal` — user's personal repos (dotfiles, `devseunggwan/scratchs`, etc.)
- `praxis` — the praxis distribution (`devseunggwan/praxis`)
- `org` — company/team org repos (e.g., laplace-*)
- `project-local` — `.claude/` directory inside the current project

**Target ownership** (where the artifact will go):
- Same classification as above

Ownership classification hints:
- URL/path contains `devseunggwan/` and is NOT the praxis repo → `personal`
- URL/path matches the praxis repo (`devseunggwan/praxis`) → `praxis`
- URL/path contains the org name or is an org-level resource → `org`
- Destination is `.claude/hooks/` inside the cwd project → `project-local`

### Step 3: Build Hook Contract Matrix

For each active intent type, enumerate the applicable contracts:

#### `PORT` (any combination of personal → praxis → org)

| Combination | Contracts |
|-------------|-----------|
| `personal → org` | ① Personal repo content isolation (CLAUDE.md): strip internal refs, write in English, no internal identifiers in the artifact. ② External-repo write authorization gate: per-action explicit approval required before any write. |
| `personal → praxis` | ① Praxis is an external-org repo — the external-repo authorization gate applies. ② Strip personal paths / internal names before posting. |
| `org → personal` | Content is internal — ensure no confidential data (customer names, internal IDs, Slack links) appears in the personal repo artifact. |
| `project-local → praxis` (hooks) | Hooks live in `praxis/hooks/`, registered in `praxis/hooks/hooks.json`. A project-local `.claude/hooks/` entry for a praxis-owned hook causes deployment drift — the canonical location is the praxis distribution. |

#### `CROSS_REPO_WRITE` (gh pr create / gh issue create / gh issue comment to external repo)

All three apply simultaneously:

1. **External-repo write authorization gate** (CLAUDE.md §GitHub Issue Hygiene):
   - Per-action explicit user approval required. No "proceed" / "ok" / "continue" inference.
   - Proposed content must be shown to user BEFORE write.

2. **`block-pr-without-caller-evidence`** (fires on any `gh pr create`):
   - PR body MUST contain the literal line: `Caller chain verified: <source_skill_or_context>`
   - Without it the PreToolUse hook blocks the command.

3. **Body delivery format**:
   - Use `--body-file <path>` (write body to a temp file first).
   - Inline heredoc (`<<EOF`) is blocked by the praxis PreToolUse static analysis hook.

4. **Language & content rules** (CLAUDE.md §External / third-party repo content isolation):
   - Write in English only (no Korean in external repos).
   - No internal identifiers: `laplace-*`, `hub #N`, internal Slack/Notion links, internal tool names.
   - No absolute local paths — use `<repo>/<path>` placeholders.

#### `GH_CLI_CONTRACT` — `gh search --state`

- `block-gh-state-all` hook (PreToolUse Bash): `--state all` is NOT a valid flag for `gh search issues` / `gh search prs`. The hook hard-blocks the command.
- Correct pattern: run two separate calls — `--state open` and `--state closed`.

#### `GH_CLI_CONTRACT` — heredoc body

- The praxis PreToolUse static analysis hook performs argv-level parsing. Heredoc sequences (`<<EOF`, `<<'EOF'`) in `gh issue create` / `gh pr create` bodies are rejected at the hook level.
- Correct pattern: write body to `/tmp/<slug>.md` via the `Write` tool, then pass `--body-file /tmp/<slug>.md`.

#### `HOOK_LOCATION`

- Praxis hooks are canonical at `praxis/hooks/` and registered in `praxis/hooks/hooks.json`.
- A hook placed in the project-local `.claude/hooks/` for cross-project enforcement creates deployment drift: it only fires in that one project's session, not globally. The correct location is the praxis distribution with an entry in `hooks.json`.
- After adding: run `./scripts/check-plugin-manifests.py` to verify packaging.

### Step 4: Surface Pre-Flight Checklist

Call `AskUserQuestion` with a checklist of all contracts that apply to the
detected intent. Present:

1. **Intent type(s) detected** — one-line per type
2. **Source → Target ownership** — only for PORT and CROSS_REPO_WRITE
3. **Applicable contracts** — one bullet per contract from Step 3
4. **Confirmation question** — ask the agent to verify each contract before proceeding

```
Question: "Cross-boundary pre-flight: {N} contract(s) apply. Confirm all are satisfied before proceeding?"

Options:
  - "✅ All satisfied — proceed"
  - "⚠ Need to fix: [describe which contract is not yet met]"
  - "🛑 Abort — intent was wrong"
```

Do NOT proceed with the cross-boundary action until the user (or agent)
confirms "All satisfied".

### Step 5: Post-Confirmation Gate

After "✅ All satisfied" is selected:

1. For `CROSS_REPO_WRITE`: remind the agent that approval is **per-action**. Approving this pre-flight does NOT cover a second `gh` write in the same session — each write needs its own gate.
2. For `HOOK_LOCATION`: remind the agent to run `./scripts/check-plugin-manifests.py` after adding the hook to `hooks.json`.
3. For `GH_CLI_CONTRACT` body delivery: remind the agent to use `Write` tool → `/tmp/<slug>.md` → `--body-file` pattern before executing.
4. Emit a one-line summary: `Pre-flight complete. {intent_type} action cleared to proceed.`

## Error Handling

| Situation | Action |
|-----------|--------|
| Intent type cannot be determined from arguments or context | Ask user a clarifying question: "What is the cross-boundary action you're about to take?" — use the answer as input to Step 1 |
| Target repo is the same as current project repo | No cross-boundary action detected; exit without pre-flight |
| User selects "🛑 Abort" | Emit: "Pre-flight aborted. Cross-boundary action cancelled." Stop here — do not proceed |
| User selects "⚠ Need to fix" | Surface the specific unmet contract, suggest the correct pattern (from Step 3), then re-offer the checklist after the fix |

## Example Flow — Scenario #5: Cross-Repo `gh pr create`

```
Agent intent: Create a PR in devseunggwan/praxis from a feature branch

[Step 1] Intent type detected: CROSS_REPO_WRITE
  - Command pattern: gh pr create --repo devseunggwan/praxis

[Step 2] Ownership:
  - Source: current project (org or personal)
  - Target: praxis (devseunggwan/praxis — external-org repo)

[Step 3] Applicable contracts:
  1. External-repo write authorization gate — per-action explicit approval required
  2. block-pr-without-caller-evidence — PR body must contain "Caller chain verified: ..."
  3. Body delivery — use --body-file /tmp/pr-body.md (heredoc blocked by hook)
  4. Language — English only, no internal identifiers

[Step 4] AskUserQuestion:

  "Cross-boundary pre-flight: 4 contracts apply. Confirm all are satisfied?"

  ① External-repo write authorization gate: user has given explicit per-action
    approval for THIS specific PR create action.
  ② PR body contains: Caller chain verified: <source_skill>
  ③ Body written to /tmp/pr-body.md and passed via --body-file (no heredoc)
  ④ Body is in English with no internal identifiers or Korean text

  Options: ✅ All satisfied | ⚠ Need to fix | 🛑 Abort

[Step 5] On "✅ All satisfied":
  "Pre-flight complete. CROSS_REPO_WRITE action cleared to proceed.
   Reminder: this approval covers only this specific PR create — any
   subsequent gh writes need their own pre-flight gate."
```

## Worked Example — Scenario #3: `gh search --state all`

```
Agent intent: Search for all issues (open and closed) in a repo

[Step 1] Intent type detected: GH_CLI_CONTRACT (--state flag)
  - Draft command: gh search issues --repo owner/repo --state all

[Step 3] Applicable contracts:
  1. block-gh-state-all (PreToolUse Bash): --state all is not a valid flag.
     The hook hard-blocks this command.
  2. Correct pattern: run two calls —
       gh search issues --repo owner/repo --state open
       gh search issues --repo owner/repo --state closed

[Step 4] AskUserQuestion:

  "GH_CLI_CONTRACT pre-flight: --state all is blocked by the block-gh-state-all
   hook. Have you replaced it with two separate --state open / --state closed calls?"

  Options: ✅ Yes, using two calls | ⚠ No, fixing now | 🛑 Abort

[Step 5] On "✅ Yes, using two calls":
  "Pre-flight complete. GH_CLI_CONTRACT action cleared to proceed."
```
