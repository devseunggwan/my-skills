---
name: retrospect
description: >
  Session retrospect — analyze current Claude Code session against CLAUDE.md rules,
  identify friction patterns and root causes, propose context-appropriate improvement
  actions, then execute after user approval.
  Triggers on "retrospect", "what went wrong", "session review",
  "session improvement", "what was the issue", "improve".
---

# Retrospect

## Overview

Repeated friction wastes cycles across sessions. Unexamined pain stays unresolved.

**Core principle:** ALWAYS analyze root cause before proposing any action.
Symptom-level fixes (e.g., "remember to do X") miss the underlying pattern.

**Pipeline:** `Load → Analyze → Report/Approve → Execute` (4 stages)

**Delegates to:** OMC `tracer` agent (causal pattern analysis), `analyst` agent (pattern clustering)

## The Iron Law

```
NO ACTION WITHOUT ROOT CAUSE ANALYSIS FIRST.
PATTERN ≠ ROOT CAUSE. SYMPTOM ≠ ROOT CAUSE.
REPEATED PATTERN + MEMORY = FAILED REMEDY. ESCALATE.
TRACER + ANALYST CALLS ARE MANDATORY, NOT OPTIONAL.
```

If you haven't completed Stage 2 (Analyze), you cannot propose actions.
"It happened because X" is a symptom. "X happened because of missing rule Y / unclear trigger Z / absent skill W" is a root cause.

## When to Use

Use at the END of a working session to extract learnings:

- Session had repeated tool retries or direction changes
- User gave corrections mid-session ("no, don't do that")
- A task took significantly longer than expected
- Workflow steps were skipped or out of order
- User expressed frustration or redirected multiple times

**Use this ESPECIALLY when:**
- The same mistake happened more than once in the session
- You feel "I should have done that differently"
- A rule in CLAUDE.md was violated — even once
- A new workflow pattern emerged that isn't captured anywhere

## The Four Stages

You MUST complete each stage before proceeding to the next.

### Stage 1: Load Calibration Standard

**Before scanning the conversation:**

1. **Read CLAUDE.md** — load all rules, behavioral guidelines, and workflow requirements
   - Global: `$CLAUDE_CONFIG_DIR/CLAUDE.md`
   - Project: `CLAUDE.md` in cwd (if exists)
   - Key sections: Mandatory Rules, Behavioral Rules, Workflow rules

2. **Identify rule categories** to scan against:
   - Workflow discipline (Issue-Driven Workflow, Planning Before Implementation)
   - Evidence-Based Delivery (No "Trust Me" completions)
   - Atomic Commits + PR Lifecycle
   - Mandatory Testing (unit + functional)
   - Code Review Before Commit
   - Error Recovery Before Asking
   - Communication conventions

3. **Set the calibration frame**: For each rule category, form a question — e.g.,
   "Did the session violate 'Planning Before Implementation'? Were there 3+ step tasks that skipped plan mode?"

### Stage 2: Analyze Conversation

**Pre-scan: Quick friction event identification** — scan the conversation for up to 5 friction events (user corrections, retries, skipped steps, stalls) BEFORE calling agents. This provides the input for agent calls.

**Early exit**: If pre-scan finds 0 friction events, skip agent calls and exit with "No patterns found. ✅" — do not call agents with empty input.

**MANDATORY AGENT CALLS — when pre-scan finds 1+ friction events, MUST call sequentially (analyst depends on tracer output):**

1. **tracer agent** (causal chain analysis) — call FIRST:
   `Agent(subagent_type="oh-my-claudecode:tracer", model="sonnet")`
   - Input: friction events identified from pre-scan
   - Output: causal chains with confidence scores
   - Do NOT skip this call. "I can analyze this myself" is a Red Flag.

2. **analyst agent** (pattern clustering) — call AFTER tracer completes:
   `Agent(subagent_type="oh-my-claudecode:analyst", model="sonnet")`
   - Input: friction events + tracer causal chains (from step 1)
   - Output: clustered patterns with root causes

**Then refine using agent outputs:**

> **Scope:** Scan the most recent 50 turns, or back to the last session boundary.
> Stop after identifying 5 distinct friction events — clustering (step 6) handles de-duplication.
> If session history is not accessible, use the user's verbal summary as input to steps 3–8.

3. **Refine friction events with agent outputs** — merge pre-scan events with tracer/analyst results:
   - Add any new friction events the agents identified that pre-scan missed
   - Update causal chains using tracer confidence scores
   - Drop false positives that agents ruled out
   - Final list: up to 5 distinct friction events with causal chains attached

4. **Map each event to a CLAUDE.md rule** (or gap):
   - Which rule was applicable?
   - Was it followed, violated, or simply absent?
   - Quote or paraphrase the specific moment

4b. **Tool Friction Pass** — independently analyze tool/feature-level friction:

   This pass runs SEPARATELY from step 4. A friction event may match a rule violation (step 4) AND a tool defect (step 4b) — both are recorded.

   **Tool layers to scan (all 4):**

   | Layer | Examples | Friction signals |
   |-------|----------|-----------------|
   | `mcp` | any custom or third-party MCP server (data warehouse, observability, chat, infra, etc.) | Slow response, missing field, schema mismatch, timeout |
   | `cli` | `gh`, `kubectl`, `git`, plus project-specific CLIs | Missing flag/option, undocumented behavior, workaround needed |
   | `builtin` | Read/Edit/Bash/Grep/Glob, Agent, hooks | Environmental constraint, permission issue, output truncation |
   | `skill` | praxis / OMC / project-specific skills and subagents | Stage boundary unclear, trigger mismatch, prompt defect, wrong routing |

   **For each tool friction event, record:**
   - `tool_name`: specific tool (e.g., "gh CLI", "<plugin-name> MCP", "<skill-name> skill")
   - `layer`: mcp / cli / builtin / skill
   - `friction_type`: missing feature, design defect, documentation gap, performance issue, integration mismatch
   - `evidence`: the specific moment (quote or paraphrase)
   - `expected_behavior`: what should have happened
   - `proposed_fix_direction`: brief suggestion for upstream improvement

   **Representative friction examples (for calibration):**
   1. "gh CLI의 `--state all` 플래그가 없어서 open/closed를 각각 호출해야 했다" → layer: `cli`, friction_type: missing feature
   2. "MCP 응답 지연으로 3회 재시도 후 fallback 전략을 수동 구성했다" → layer: `mcp`, friction_type: performance issue
   3. "skill의 Stage 경계가 불명확해서 step을 건너뛰고 다음 stage로 넘어갔다" → layer: `skill`, friction_type: design defect
   4. "codex exec의 permission mode가 달라 파일 쓰기에 실패했다" → layer: `cli`, friction_type: integration mismatch
   5. "Read 도구의 출력 truncation으로 파일 끝부분을 놓쳤다" → layer: `builtin`, friction_type: design defect

   **Dedup rule (step 4 vs step 4b):**
   - If a friction event has BOTH a rule violation (step 4) AND a tool defect (step 4b), record it in BOTH places
   - Step 4 finding addresses the behavioral correction (what Claude should have done differently)
   - Step 4b finding addresses the tool improvement (what the tool should do differently)
   - The two findings may have different action types (e.g., step 4 → memory, step 4b → upstream feedback)

5. **Find root cause** for each pattern:

   ```
   Symptom:   "Claude retried the same tool 3 times"
   Pattern:   "Error recovery loop"
   Root cause: "No diagnostic step between retries — violated Error Recovery Before Asking rule"

   Symptom:   "Implementation started before plan was approved"
   Pattern:   "Premature execution"
   Root cause: "Task had 4 steps but plan mode was not entered — violated Planning Before Implementation"
   ```

6. **Cluster patterns** — are multiple events the same root cause?
   If 3+ events share a root cause → HIGH priority

7. **Scan MEMORY.md for repeat patterns** (2-hop deterministic scan):
   a. Read MEMORY.md index (single file read) — extract all feedback entry titles and file paths
   b. For each finding's root cause, identify candidate matches from index titles (concept-level, not keyword)
   c. Read each candidate feedback file to confirm semantic match (same root cause, not just similar keywords)
   d. Only mark `repeat=true` if root cause is semantically identical
      - Example: "workflow skip" in index + "workflow violation" in finding = match
      - Example: "commit" matching both "atomic commit" and "pre-commit hook" = NOT auto-match, read file to confirm
   e. `repeat_count` = number of distinct feedback files with matching root cause
   f. If match found with existing resolution action (issue/hook already created): mark as `resolved=true`

8. **Auto-assign action type** based on escalation ladder:

   | Condition | Action Type | Rationale |
   |-----------|-------------|-----------|
   | New pattern (structural root cause, likely to recur) | memory | First occurrence — capture for future reference |
   | Repeat (in MEMORY.md, 1-2x) | GitHub issue | Memory alone failed — need systemic fix |
   | Repeat (3x+) | hook or skill | Multiple memory entries = enforcement gap |
   | Missing rule (new) | CLAUDE.md draft | No rule exists for this pattern |
   | Missing rule + Repeat | CLAUDE.md draft + GitHub issue | Missing rule caused repeat — add rule + compliance issue |
   | Tool friction (step 4b finding) | upstream feedback | Tool improvement needed — issue in the tool's **backing repo** (resolve via Stage 4 Action 4 routing table; not always praxis) |
   | One-off mistake (situational cause, unlikely to recur) | note only | No persistent action needed |

   **Distinguishing "New pattern" vs "One-off mistake":**
   - **New pattern**: root cause is structural (missing rule, absent skill, unclear workflow) → likely to recur in future sessions
   - **One-off mistake**: root cause is situational (context loss, typo, unusual edge case) → unlikely to recur under normal conditions
   - When uncertain, default to `memory` (safer to capture than to miss)

   ⚠️ **BLOCKED unless justified**: If `repeat=true`, the action type CANNOT be `memory`.

   **Escape hatch**: If `repeat=true` AND `resolved=true` (existing issue/hook resolution already exists for this feedback), `note only` is allowed. In this case, include a sentence in the report confirming that the existing resolution is still effective.

### Stage 3: Report + Approval

**Output Schema Contract** (normative — Stop hook `retrospect-mix-check.sh` parses this):

Stage 3 output MUST emit, in this order:

1. **Header**: a line matching `^## Retrospect Report` (em-dash or hyphen tail accepted: `## Retrospect Report — {date}` or `## Retrospect Report - {date}`).
2. **Distribution card** between HTML comment fences. Action keys are canonical snake_case enum; verdict values are `PASS` / `FAIL` / `NA`:

   ```markdown
   <!-- AUTHORITATIVE_SCHEMA — Stop hook depends on this. Co-update hooks/retrospect-mix-check.sh + tests/test_retrospect_mix_check.sh + tests/fixtures/retrospect-synth-*.expected.json on any change to this fence or the action key set. -->
   <!-- retrospect:distribution begin -->
   - memory: 1
   - issue: 0
   - claude_md_draft: 0
   - skill_idea: 0
   - hook_code: 0
   - upstream_feedback: 0
   - gate_1_verdict: PASS
   - gate_2_verdict: PASS
   <!-- retrospect:distribution end -->
   ```

3. **Unified findings table** with literal column headers (no abbreviation, no reordering):

   ```
   | # | Category | Tool Layer | Pattern | Root Cause | Rule / Gap | Repeat? | Proposed Actions (1~2) | Rationale | Priority |
   ```

   Column semantics:
   - `Category`: comma-separated subset of `behavioral`, `tool`, `workflow`, `spec-gap` (≥1, see Stage 2 pre-scan categorization)
   - `Tool Layer`: one of `mcp`, `cli`, `builtin`, `skill`, or `—` (mandatory non-`—` when `tool` ∈ Category, optional `skill` for `workflow` / `spec-gap`, `—` for `behavioral`)
   - `Proposed Actions (1~2)`: comma-separated subset of `memory`, `issue`, `claude_md_draft`, `skill_idea`, `hook_code`, `upstream_feedback`
   - `Rationale`: free-form one-line for compound or non-memory rows; for **memory-only** rows (single `memory`, not compound), the cell MUST contain exactly 5 lines matching `^not (issue|claude_md_draft|skill_idea|hook_code|upstream_feedback): .+$`, one line per non-memory action type. Generic single-sentence rationales are NOT acceptable for memory-only findings.

The Stop hook parses the distribution-card fence (deterministic) and the table (anchored on these literal column headers). Drift in this contract requires synchronized edits to `hooks/retrospect-mix-check.sh`, `tests/test_retrospect_mix_check.sh`, and `tests/fixtures/retrospect-synth-*.expected.json`.

**Spec AC-A3 deviation note** — earlier draft asked for "memory-only justification 한 줄" inside the distribution card. v2 relocates that justification into the unified-table `Rationale` column as the structured 5-line `not <action>: <reason>` block: strictly more informative than a single line, single source of truth, eliminates card↔table inconsistency risk.

---

**Present findings as a single unified table per the Output Schema Contract above:**

```
## Retrospect Report — {session_date}

<!-- retrospect:distribution begin -->
- memory: {n}
- issue: {n}
- claude_md_draft: {n}
- skill_idea: {n}
- hook_code: {n}
- upstream_feedback: {n}
- gate_1_verdict: {PASS|FAIL|NA}
- gate_2_verdict: {PASS|FAIL|NA}
<!-- retrospect:distribution end -->

| # | Category | Tool Layer | Pattern | Root Cause | Rule / Gap | Repeat? | Proposed Actions (1~2) | Rationale | Priority |
|---|----------|------------|---------|------------|------------|---------|------------------------|-----------|----------|
| 1 | {behavioral|tool|workflow|spec-gap, ...} | {mcp|cli|builtin|skill|—} | {pattern} | {root_cause} | {rule_ref or "gap"} | {Yes(Nx)/No} | {action1[, action2]} | {rationale: 5 `not <action>:` lines for memory-only, or one-line for compound/non-memory} | HIGH/MED/LOW |
...

No patterns found: emit the distribution card with all counts = 0 and verdicts = NA, plus literal "This session followed all CLAUDE.md rules. ✅"
```

The unified table folds the previous dual-table layout (Pattern + Tool/Feature Findings) into one. Tool-layer information that previously lived in a separate "Tool/Feature Findings" table is now carried in the `Tool Layer` column of every row tagged with `tool` in `Category`. Reviewers see all findings in priority order without cross-referencing two tables.

**Sorting**: rows SHOULD be sorted by `Priority` (HIGH → MED → LOW). Within the same priority, prefer non-memory `Proposed Actions` first so escalations surface above behavioral memos.

**Action type baseline comes from Stage 2 escalation ladder**, but Stage 3 MUST explicitly evaluate all six action types per finding and select 1–2 composite actions.

> **Exception — one-off mistakes**: If Stage 2 classified the finding as `note only` (situational root cause, unlikely to recur), skip the evaluation below entirely. No persistent action is created; the finding appears in the report as acknowledged only.

**For each finding (except one-off), evaluate ALL six action types before selecting:**

| Action Type | When to Choose | Skip If |
|-------------|---------------|---------|
| **MEMORY.md feedback** | New pattern (1st occurrence, repeat_count=0), individual learning | repeat=true (memory is BLOCKED) |
| **GitHub issue** | Systemic fix needed (tool/skill implementation), repeat pattern (1–2×) | One-off mistake, purely local insight |
| **CLAUDE.md draft** | Explicit rule gap exists, cross-project scope needed | Existing rule already covers this pattern |
| **Skill idea note** | Repeat pattern needs enforcement mechanism, manual recall is insufficient | Single memo is sufficient, no recurring trigger |
| **Hook code** | Repeat (3x+) requiring automated enforcement; manual recall has repeatedly failed | Fewer than 3 repeats; skill idea or rule is sufficient |
| **Upstream feedback** | Tool/feature-level defect identified in step 4b; improvement needed in the tool itself, not in Claude's behavior | Finding is purely a rule violation with no tool-level root cause |

**Selection matrix — three axes to determine compound vs. single action:**

| Axis | Signal → Action |
|------|----------------|
| **Repeat count** | 0× → `memory` (first occurrence); 1–2× → `issue` (memory blocked — repeat=true); 3×+ → `skill` or `hook` (enforcement gap) |
| **Scope** | Cross-project impact → `CLAUDE.md draft`; single-project → `MEMORY.md` |
| **Gap type** | Rule violated → `memory` (reinforce); rule absent → `CLAUDE.md draft` (fill gap); no enforcement → `skill idea` |

> **Axis precedence: Repeat-count is the highest-priority axis.** When `repeat=true`, the Scope and Gap type axes cannot override to `memory` — the repeat-count constraint (issue / skill / hook) always wins. Apply Scope and Gap type only to determine additional actions alongside the repeat-count result.

**Compound action is the default for HIGH-priority findings.** A single `memory` action is acceptable only when the rationale for skipping all other types is explicitly stated in the `Rationale` column.

**Before approval, explain each action's concrete plan:**

For each finding, present:
1. **What will be created** (file path, issue title, hook name, or CLAUDE.md rule text)
2. **Why this action type** (escalation rationale — e.g., "Already recorded 3x in MEMORY.md")
3. **How it will be verified** (what check confirms it works)

Example (single action — repeat pattern):
> Finding #2: Workflow step skipped (4th occurrence)
> - **Proposed Actions**: GitHub issue
> - **Rationale**: Already recorded 3x in MEMORY.md. Memory alone has failed. Structural fix required.
> - **What will be created**: issue — `feat(hook): add external-repo commit guard`
> - **Verify**: issue URL returned + `gh issue view` confirms existence

Example (compound action — rule gap + repeat):
> Finding #1 (HIGH): Hasty interpretation without verification (ambiguous signal → worst-case conclusion, 3 occurrences)
> - **Proposed Actions**: `CLAUDE.md draft` + `GitHub issue`
> - **Rationale**: Rule absent + 3× repeat → fill the rule gap (CLAUDE.md draft) and track enforcement compliance (GitHub issue); matches Stage 2 ladder: "Missing rule + Repeat"
> - **What will be created**:
>   - CLAUDE.md draft: new rule requiring a disconfirmation check before concluding from ambiguous signals
>   - issue — `feat(retrospect): enforce falsify-first check on ambiguous signal interpretation`
> - **Verify**: CLAUDE.md draft shown to user for approval + issue URL returned

**Then ask for approval per item using AskUserQuestion:**

```
For each finding, user selects:
  ✅ Execute now  |  ⏭ Skip  |  🕐 Defer (create note only)
```

Do NOT execute any action until user approves.

### Stage 4: Execute

**"note only" items require no execution** — they appear in the completion report as acknowledged but need no persistent artifact.

For each approved action:

1. **MEMORY.md feedback** → Write to `$CLAUDE_CONFIG_DIR/projects/.../memory/` with proper frontmatter
   - Type: `feedback`
   - Include: rule, why, how to apply
   - Update `MEMORY.md` index

   **⚠️ MANDATORY: Duplicate check before creating any memory file:**

   **Precondition:** This check applies ONLY when the finding's action type is `memory` (new pattern). If Stage 2 already marked `repeat=true` and escalated to issue/hook/CLAUDE.md, skip this check — the escalation ladder takes precedence over merge.

   a. Reuse Stage 2 Step 7's repeat scan results — if a finding matched an existing memory but was NOT escalated (i.e., it's a genuinely new sub-pattern), that file is the merge target
   b. If no Stage 2 match: scan MEMORY.md index for entries with overlapping root cause or topic (concept-level, not keyword)
   c. For each candidate, read the existing memory file and compare:
      - Same root cause / principle → **merge**: append new context (examples, How to apply items) to the existing file. If merge makes this the 2nd+ occurrence, re-evaluate whether action type should escalate per Stage 2 Step 8
      - Related but distinct principle → **create new file** (genuinely different insight)
   d. **Never create a new file when the insight is a specific instance of an existing general rule** — add it as a numbered sub-item instead
   e. After merge or create, update MEMORY.md index (update description if merged, add new line if created)

2. **GitHub issue** → Use project's issue creation skill or `gh issue create`
   - Title: Conventional Commits format (per project convention)
   - Body: per project convention, with background + task list

3. **CLAUDE.md draft** → Write proposed rule addition as a markdown block
   - ⚠️ `$CLAUDE_CONFIG_DIR/CLAUDE.md` is **global scope** — changes affect every project
   - Present the draft to user for review BEFORE any edit
   - Apply only with explicit approval ("yes, add this rule")

4. **Upstream feedback** → Resolve the tool's **backing repo first** (do NOT hardcode any specific repo), then create a labeled issue there. Hardcoding misroutes plugin defects, custom MCP defects, dotfiles defects across user environments.

   **Backing repo resolution (MUST do BEFORE issue creation):**

   | Tool name / layer pattern | Backing repo resolution |
   |---|---|
   | `mcp__<plugin>__*` from a Claude Code plugin | Read `repository` field from that plugin's `.claude-plugin/plugin.json` (or equivalent manifest) |
   | `mcp__<service>-*` from a custom/team MCP server | The MCP server's source repo — `git remote -v` of the server's directory, or read its package manifest |
   | Skill within the praxis distribution itself | The praxis source repo this skill was installed from — read `repository` field in praxis's own plugin manifest |
   | Hook in `~/.claude/hooks/` or a globally symlinked CLAUDE.md/AGENTS.md | The user's dotfiles backing repo — resolve via `ls -la` symlink chain, then `git remote -v` of the target dir |
   | CLI tool (e.g., `gh`, `kubectl`) | The CLI's open-source upstream if accessible; otherwise `note only` |
   | Builtin tool (Read/Edit/Bash/Grep) | Typically not actionable — `note only` |
   | Other / ambiguous | Ask the user; do NOT fall back to a hardcoded repo |

   If the active project's CLAUDE.md provides a feature-to-repo mapping, consult it before deciding a repo.

   **Then create the issue (using the resolved backing repo):**
   - Title: `{type}({tool_layer}): {friction description}` (Conventional Commits format)
   - Label: `tool-friction:{layer}` is praxis's own convention. Apply it ONLY when the resolved backing repo is the praxis distribution itself. For any other backing repo, use that repo's existing label conventions (e.g., `bug`, `enhancement`); do NOT auto-create praxis-style labels in unrelated repos.
   - If `tool-friction:*` is needed and missing in the praxis repo: `gh label create "tool-friction:{layer}" --repo <resolved-praxis-repo>`
   - Body: include evidence, expected behavior, proposed fix direction from step 4b finding
   - Command: `gh issue create --repo <resolved_backing_repo> --title "$TITLE" --label "$LABEL" --body "$BODY"` — substitute the resolved repo, never hardcode
   - **Verification (mandatory):** issue URL is returned, `gh issue view {url}` succeeds, AND the URL's repo matches the resolved backing repo (catches misrouting)

5. **Skill idea note** → Write to `{current_project}/.omc/plans/retrospect-skill-idea-{slug}.md`
   - `{current_project}` = `$CLAUDE_PROJECT_DIR` or `git rev-parse --show-toplevel`
   - Include: problem, proposed skill trigger, pipeline sketch

6. **Hook code** → For enforcement-level actions (repeat 3x+):
   a. Write hook script to `.claude/hooks/` or appropriate location
   b. Present the hook code to user for review
   c. Explain how to register in `.claude/settings.json` (show the exact JSON entry)
   d. Use AskUserQuestion: "Hook을 settings.json에 등록할까요?" (✅ 등록 / ⏭ 파일만 유지 / 🕐 나중에)
   e. If approved: Edit `.claude/settings.json` to register the hook
   f. If skipped/deferred: leave the hook file in place and provide manual registration instructions

7. **Verification** — For each executed action, verify the artifact:

   | Artifact | Verification |
   |----------|-------------|
   | MEMORY.md feedback (new) | File exists + MEMORY.md index updated |
   | MEMORY.md feedback (merged) | Existing file updated (diff shown) + MEMORY.md index description updated if needed |
   | GitHub issue | `gh issue view {url}` returns valid data |
   | Upstream feedback | `gh issue view {url}` returns valid data + correct `tool-friction:{layer}` label attached |
   | Hook code | Script file exists + settings.json registration confirmed (dry-run varies by hook type — no generic check) |
   | CLAUDE.md draft | Diff shown to user + explicit approval received |
   | Skill idea note | File exists in `.omc/plans/` |

   Report verification results in the completion table.

8. **Completion report:**

```
## Actions Executed

| # | Action | Result |
|---|--------|--------|
| 1 | MEMORY.md feedback added | ✅ {file_path} |
| 2 | GitHub issue created | ✅ {url} |
...

Session learnings captured. Next session will benefit from these improvements.
```

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "It was a one-off mistake, not worth capturing" | If it happened once, it can happen again. Capture it. |
| "I know the root cause, I'll just note the symptom" | Symptoms recur. Root causes get fixed. Write the root cause. |
| "MEMORY.md is already long, skip this" | Length doesn't matter. Missing the pattern is the cost. |
| "The session was mostly fine, nothing to retrospect" | Even 1 friction event is worth 2 minutes to capture. |
| "I'll do this later" | Later never comes. Do it at session end while context is fresh. |
| "This is a tool issue, not a Claude issue" | Tool + Claude interaction is within scope. Both can be improved. |
| "Tool issue라서 이번 retrospect scope 밖이다" | Scope 안이다. Step 4b에서 분석하고 `upstream feedback`으로 도구의 backing repo (Stage 4 Action 4 의 routing 표 참고)에 이슈를 남겨야 한다. |
| "도구 결함이지 내 행동 문제가 아니다" | 둘 다일 수 있다. Step 4 (행동 교정)와 step 4b (도구 개선)에 각각 기록하라. 하나만 선택하지 마라. |

## Red Flags — STOP

If you catch yourself:

- Proposing actions before completing Stage 2 analysis
- Writing "root cause: Claude forgot to X" without tracing WHY the forgetting happened
- Adding a MEMORY.md entry that just repeats the CLAUDE.md rule verbatim (no new insight)
- Creating a GitHub issue for every minor friction (low-ROI noise)
- Skipping the approval step and executing actions directly
- Editing `$CLAUDE_CONFIG_DIR/CLAUDE.md` without presenting the draft first — this is global config, affects every project
- Proposing `memory` for a pattern that already exists in MEMORY.md (MUST escalate instead)
- Skipping tracer/analyst agent calls ("I can analyze this myself")
- Generating artifacts without verification ("issue created" without showing URL)
- Creating a new memory file without checking existing entries for overlap (MUST merge into existing when root cause matches)
- **Proposing MEMORY.md feedback as the only action when the same rule was violated 3+ times** — this ignores memo's proven limits; enforcement mechanisms (skill, hook, rule) MUST be evaluated alongside memory
- **Proposing MEMORY.md feedback as the only action when the finding is a rule gap (rule absent)** — gaps are not filled by memos; CLAUDE.md draft or skill idea MUST be considered
- **Forcing tool friction into only a rule-violation frame** — tool-layer defects from step 4b MUST be reported in the separate Tool/Feature Findings table and evaluated for `upstream feedback`, not collapsed into rule-violation findings
- **Skipping step 4b entirely** ("no tool issues this session") — step 4b is mandatory. If no tool friction is found, record "No tool/feature friction detected. ✅" explicitly

**ALL of these mean: STOP. Return to Stage 2.**

## Quick Reference

| Stage | Key Activity | Success Criteria |
|-------|-------------|-----------------|
| **1. Load** | Read CLAUDE.md, form scan questions | Rule categories identified |
| **2. Analyze** | Scan conversation, map to rules, find root cause | Root cause (not symptom) for each pattern |
| **3. Report** | Present table, collect approval per item | User approved at least 1 item (or confirmed 0 findings) |
| **4. Execute** | Run approved actions, verify artifacts | Completion report with links/paths + verification results |

## Error Handling

| Stage | Failure | Action |
|-------|---------|--------|
| Stage 1 (load) | CLAUDE.md not found (project or global) | Proceed with global defaults; flag the missing file in the report |
| Stage 2 (analyze) | Session history not accessible | Fall back to the user's verbal summary as input to steps 3–8 |
| Stage 2 (analyze) | No friction events found | Exit with "No patterns found. ✅" — do not fabricate findings |
| Stage 2 (analyze) | MEMORY.md scan failed (file not accessible) | Treat all findings as new patterns (repeat=false). Flag scan failure in report |
| Stage 2 (analyze) | MEMORY.md is empty | Normal processing — all findings are new patterns |
| Stage 2 (analyze) | tracer/analyst call failed | Fall back to manual analysis. Flag agent failure in report. Warn about reduced root cause quality |
| Stage 3 (report) | User rejects all findings | Capture the rejection itself as a feedback signal for future retrospects |
| Stage 4 (execute) | MEMORY.md write fails | Report the path error; never silently drop the feedback |
| Stage 4 (execute) | GitHub issue creation fails | Fall back to saving a note in `.omc/plans/` for later manual creation |
| Stage 4 (execute) | Upstream feedback issue creation fails | Fall back to saving a note in `.omc/plans/tool-friction-{slug}.md` with intended `tool-friction:{layer}` label and issue draft |
| Stage 4 (execute) | `tool-friction:*` label doesn't exist (and the resolved backing repo is the praxis distribution) | Auto-create with `gh label create "tool-friction:{layer}" --repo <resolved-praxis-repo>` and retry |

## Integration

**Entry point:** End of a working session, or after a particularly rough workflow experience
**Exit point:** Completion report shown → optionally chain to next session's `turbo-setup`

**OMC delegation:**
- `tracer` agent: causal chain analysis for complex friction patterns
- `analyst` agent: cluster multiple friction events into root causes
- Project's issue creation skill: GitHub issue creation in Stage 4
