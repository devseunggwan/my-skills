# Praxis

Development workflow skills for Claude Code — disciplined, fast, resilient.

Each skill is an orchestrator with pluggable steps. External integrations (issue tracker, PR tool, code review) are routed via the project's CLAUDE.md — no hardcoded dependencies.

## Prerequisites

| Tier | What works | Dependencies |
|------|-----------|--------------|
| **Standalone** | turbo-setup, recover-sessions, strike / strikes / reset-strikes | `gh` CLI, `jq` (for strike skills) |
| **Enhanced** | + turbo-implement, turbo-completion, debug, retrospect | + oh-my-claudecode |
| **Full** | + all cmux-* skills | + cmux |
| **Multi-provider** | + codex/gemini routing in cmux-*, turbo-implement | + codex-cli, gemini-cli |

## Skills (16)

### Workflow Lifecycle

| Skill | Purpose | Pluggable Steps |
|-------|---------|-----------------|
| `turbo-setup` | Compound setup — issue + plan + branch + worktree + deps in one pass | issue creation, planning |
| `turbo-implement` | Implementation orchestrator — selects execution mode and chains to delivery | ralph, autopilot (pluggable) |
| `turbo-completion` | Compound completion — verify + review + PR + merge + cleanup (--verify-only for standalone verification) | code review, PR creation |

### Development

| Skill | Purpose |
|-------|---------|
| `debug` | Systematic 4-phase debugging — root cause investigation before any fix |
| `retrospect` | Session retrospect — find friction root causes, propose improvements |

### Discipline

| Skill | Purpose |
|-------|---------|
| `strike` | Declare a rule violation — session-scoped counter, escalating signal (1진 warning → 2진 review → 3진 Stop-hook block) |
| `strikes` | Show current strike count + recorded violation reasons for the active session |
| `reset-strikes` | Reset the session strike counter to 0 after a 3진 block (required to unblock responses) |

### Session Management

| Skill | Purpose |
|-------|---------|
| `cmux-save-sessions` | Save cmux session list as JSON snapshot |
| `cmux-resume-sessions` | Restore cmux workspaces from JSON snapshot |
| `cmux-recover-sessions` | Bulk recover sessions after crash (cmux backend) |
| `recover-sessions` | Bulk recover sessions after power loss (tmux backend) |
| `cmux-session-manager` | Daily session lifecycle — status dashboard, cleanup, reorganize |
| `cmux-delegate` | Delegate a task to an independent session with auto-collected context |
| `cmux-orchestrator` | Dispatch and supervise parallel Claude Code workers in cmux |
| `cmux-browser` | Browser automation E2E testing via cmux browser CLI — SPA hydration wait included |

## Architecture

```
Project CLAUDE.md (routing config)
        │
        ▼
┌─ turbo-setup ────────────────────────────────────┐
│  issue(pluggable) → plan(pluggable) → branch     │
│  → worktree → deps                               │
└──────────────────────────────────────────────────┘
        │
        ▼
┌─ turbo-implement ────────────────────────────────┐
│  context → mode select → execute → chain         │
│  modes: manual | ralph | autopilot | guided | codex│
└──────────────────────────────────────────────────┘
        │
        ▼
┌─ turbo-completion ───────────────────────────────┐
│  Stage 0: mode detect (verify-only / full / merge)│
│  Full:  verify → review(pluggable) → PR(pluggable)│
│  Both:  compound → merge → cleanup → learn       │
└──────────────────────────────────────────────────┘
```

**Pluggable** = delegated to project's CLAUDE.md routing. Default: `gh` CLI.
**Built-in** = git operations, universal across all projects.

## Design Principles

- **Orchestrator + pluggable steps**: turbo-* stay as single skills, each step is swappable via CLAUDE.md routing
- **CLAUDE.md is the interface**: no config files — project instructions define routing
- **SRP per skill**: each skill has one responsibility, chaining connects them
- **Discipline over convenience**: Iron Laws gate each phase, no skipping

## Provider Routing

Skills that dispatch external CLI workers (`cmux-orchestrator`, `cmux-delegate`, `turbo-implement`) can route tasks to multiple AI providers. When only `claude` is installed, the system behaves exactly as before — no errors, no degradation.

### Provider CLI Spec

| Provider | Non-interactive command | Output format | Stdin prompt | Write access |
|----------|----------------------|---------------|-------------|-------------|
| `claude` | `cat $F \| claude --model {m} --output-format stream-json --permission-mode auto` | stream-json (JSONL) | `cat file \| claude` | Full |
| `codex` | `cat $F \| codex exec {m:+-m m} -o $RESULT_FILE` | stdout verbose logs + last message isolated in `$RESULT_FILE` (preferred); `--json` JSONL also supported | `cat file \| codex exec` | Sandbox-restricted — explicit fallback required |
| `gemini` | `gemini -p "$(cat $F)" --approval-mode yolo {m:+-m m}` | stream-json (`-o stream-json`) | via `-p` flag | Full |

All providers share the same completion sentinel: `; echo '===WORKER_DONE===' >> $LOG` appended after the CLI exits.

### Model Notation

Unified `--model` flag across all skills: `<provider>:<model>` or bare model name.

| Notation | Resolves to | CLI command |
|----------|-------------|-------------|
| `opus`, `sonnet`, `haiku` | `claude:{name}` | `claude --model {name}` |
| `claude` | Claude default model | `claude` |
| `claude:opus` | Claude Opus | `claude --model opus` |
| `codex` | Codex default model | `codex exec` |
| `codex:o3` | Codex with o3 | `codex exec -m o3` |
| `gemini` | Gemini default model | `gemini` |
| `gemini:flash` | Gemini Flash | `gemini -m flash` |

Bare names (`opus`, `sonnet`, `haiku`) always resolve to Claude — full backward compatibility.

### Task-Type Routing

Two-phase routing: task keywords select the provider, then complexity selects the model.

**Phase 1 — Task type to provider:**

| Task pattern | Provider | Rationale |
|-------------|----------|-----------|
| implement, fix, refactor, code generation | `codex` | Code-centric, fast execution |
| search, analyze, summarize, large context | `gemini` | Large context window, search integration |
| review, design, architecture, security, debug | `claude` | Reasoning depth, nuanced judgment |
| Default (unmatched) | `claude` | Safe default |

**Phase 2 — Complexity to model (claude only; codex/gemini use provider defaults):**

| Provider | Low | Medium | High |
|----------|-----|--------|------|
| `claude` | haiku | sonnet | opus |
| `codex` | (default) | (default) | (default or explicit) |
| `gemini` | (default) | (default) | (default or explicit) |

### Fallback Policy

1. **Pre-flight**: `command -v <cli>` before dispatch. If missing → fall back to `claude:sonnet` with warning.
2. **Runtime**: Worker failure → re-dispatch with `claude` as fallback provider.
3. **Graceful**: If only `claude` is installed, all routing resolves to claude. Original behavior preserved.

> **codex write detection**: After a codex worker completes, run `git status` to verify files were actually written. An empty diff after a code-generation task is a strong signal of sandbox write failure — trigger a claude fallback re-dispatch immediately.
> <!-- TODO: automate re-dispatch on empty git diff -->

### Provider Resolution Logic

Skills parse `--model` using this algorithm:

```
input = "--model" value

if input matches /^(codex|gemini)(?::(.+))?$/:
  provider = match[1]           # "codex" or "gemini"
  sub_model = match[2] || ""    # "" or "o3" or "flash" (colon stripped)
elif input in ["opus", "sonnet", "haiku"]:
  provider = "claude"
  sub_model = input
elif input matches /^claude(?::(.+))?$/:
  provider = "claude"
  sub_model = match[1] || ""
else:
  provider = "claude"
  sub_model = input
```

## PreToolUse gh search --state all Block

`hooks/block-gh-state-all.sh` intercepts every Bash tool call and hard-blocks
the invalid flag combination `gh search <subcmd> ... --state all`.

### Why this exists

`gh issue list` and `gh pr list` accept `--state all`, but `gh search issues`
/ `gh search prs` only accept `--state {open|closed}`. Conflating these
produces `invalid argument "all" for "--state" flag` at runtime. A feedback
memo (`feedback_verify_cli_flags.md`) was tried first but produced 5+
recurrences — structural enforcement replaced the memo.

### What is blocked

| Command | Action |
|---------|--------|
| `gh search issues "q" --state all` | **BLOCKED** (exit 2) |
| `gh search prs "q" --state=all` | **BLOCKED** (exit 2) |
| `gh search repos foo --limit 1 --state all` | **BLOCKED** (exit 2) |
| `gh issue list --state all` | **PASS** (legitimate usage) |
| `gh pr list --state all` | **PASS** (legitimate usage) |
| `gh search issues "q" --state open` | **PASS** |
| `gh search issues "q"` (no --state) | **PASS** |

### Workarounds when --state all is needed

- Omit `--state` entirely — `gh search` returns results regardless of state by default.
- Run two calls: `--state open` then `--state closed`, then merge results.

### Tests

```bash
bash hooks/test-block-gh-state-all.sh
```

Covers 14 cases: 4 block paths, 7 pass paths, non-Bash tool passthrough, and malformed stdin fail-open.

## PreToolUse Side-Effect Scan

`hooks/side-effect-scan.sh` intercepts every Bash tool call and flags commands
with collateral side effects before the agent runs them. Goal: prevent the
"primary-effect only" blind spot that has caused unintended merges, unintended
prod deploys, and stray auto-commits from CLIs that write to git internally.

### Detection categories

| Category | Trigger examples | Risk |
|----------|------------------|------|
| `git-commit` | `git commit`, `git merge`, `git rebase`, `git cherry-pick`, `git revert`, `iceberg-schema migrate`, `iceberg-schema promote`, `omc ralph` | Commits to the wrong branch or under the wrong author |
| `git-push` | `git push` | Remote published without intent |
| `gh-merge` | `gh pr merge`, `gh pr create`, `gh workflow run` | Unintended PR state change or workflow dispatch |
| `kubectl-apply` | `kubectl apply`, `kubectl delete`, `kubectl replace`, `kubectl patch` | Shared cluster mutation |

### Response

When any category matches, the hook emits:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "[category] reason..."
  }
}
```

Claude Code surfaces this as a permission prompt so the user can confirm or
redirect before the command executes.

### Prod emphasis

If any token on the command line matches `prod`, `production`,
`--env prod`/`--environment=prod`, the reason is prefixed with a
`⚠️  PROD scope` warning so the reviewer treats it with extra care.

### Opt-out marker

Known-intentional invocations can bypass the hook by embedding the literal
marker anywhere in the command:

```bash
git push origin main  # side-effect:ack
```

Use sparingly — the marker is a deliberate assertion that the side effect is
exactly what the current step requires.

### Parsing guarantees

Commands are tokenized with `shlex.shlex(..., posix=True, punctuation_chars=";|&")`
(not regex), so:

- Quotes (`"`/`'`) protect literal strings from being parsed as commands.
- Shell operators (`;`, `|`, `&`, `&&`, `||`) are always emitted as standalone
  tokens, even when typed without surrounding whitespace — `git push&&echo ok`
  and `echo x|git push origin main` both split cleanly and each segment is
  scanned for command starts.
- Env prefixes (`FOO=1 git push`), wrapper commands (`env`, `sudo`, `nice`,
  `time`, `stdbuf`, `ionice`), and their option flags are peeled from argv
  before matching — including both `--user admin` (separate value) and
  `--user=admin` (embedded), plus bare flags like `env -i`, `sudo -E`,
  `stdbuf -oL`. Nested wrappers (`sudo -E env GIT_TRACE=1 git push`) are
  unwrapped iteratively.
- Shell control-flow keywords (`if`, `then`, `elif`, `else`, `fi`, `while`,
  `until`, `do`, `done`, `for`, `case`, `esac`, `in`, `function`, `!`, `{`,
  `}`) are peeled from the start of each segment so `if true; then git push`,
  `for x in 1; do kubectl apply`, and `if git push; then ...` all reach the
  real executable.
- Newlines in the raw command are treated as command separators so multi-line
  Bash blocks (`echo prep\ngit push origin main` across two lines) get the
  second line scanned as a new segment.
- Subshells (`$(...)`) are opaque to shlex and **not** decomposed — an
  acknowledged limitation; rely on the author to use `# side-effect:ack`
  explicitly if they're running side-effecting code through `$()`.

### Tests

`tests/test_side_effect_scan.sh` covers 54 cases — positive detection across
all categories, prod emphasis, opt-out, shlex-aware evasions,
operator-adjacent one-liners, env/sudo prefix peeling, wrapper option flags
(long/short/equals/bare), nested wrappers, shell control-flow keywords,
newline-separated multi-line commands, GNU `time -f FORMAT` / `-o FILE`
arg-taking flags, non-Bash passthrough, malformed input. Run before editing
the hook:

```bash
./tests/test_side_effect_scan.sh
```

## PreToolUse Memory Hint

`hooks/memory-hint.py` fires on every Bash tool call and emits stderr lines
referencing user-scoped memory files whose YAML frontmatter declares
`hookable: true` plus a matching `hookKeywords: [...]` token. The signal is
purely attention-shifting for the LLM's next reasoning step — the hook
**never blocks**, **never asks**, **always exits 0**.

### Why this exists

Some friction patterns can be matched with structural enforcement (the two
hooks above are examples). Others — like "verify the CLI flag before using
it" — only show up as soft-textual rules in memory files. Without a hook,
Claude only retrieves those memories *after* a failure, not while
constructing the tool call. This hook surfaces them at decision-construction
time so the LLM has the option to reconsider before executing.

Reference: issue [#139](https://github.com/devseunggwan/praxis/issues/139).

### Frontmatter contract

Memory authors opt in by adding two fields to their existing frontmatter:

```yaml
---
name: my-memory
description: Short rule statement
type: feedback
hookable: true                           # NEW — opt-in switch
hookKeywords: [kubectl, hubctl, gh]      # NEW — match tokens (whole-token)
---
```

| Field | Required | Notes |
|-------|----------|-------|
| `hookable` | yes | scalar; `true` / `True` / `TRUE` / `yes` / `Yes` enable. Anything else (or missing) → not indexed. |
| `hookKeywords` | yes | flat single-line list, e.g. `[a, b, "c d"]`. Scalar form (`hookKeywords: kubectl`) is **rejected** — the memory is silently skipped. |
| `description` | no | optional; emitted after em-dash when present. Without it, the stderr line is just `[memory:hookable] {filename}`. |
| `type` | no | unrelated taxonomy field; the parser ignores it. `type` ≠ `hookable`. |

### Hook execution model

Per Anthropic docs (https://code.claude.com/docs/en/hooks), PreToolUse hooks
run **in parallel**. Array position in `hooks.json` is presentational, not a
priority gate. When multiple hooks return decisions, precedence is
`deny > defer > ask > allow`. `memory-hint` only emits stderr (no
`permissionDecision`) so it co-fires with the blocking hooks — the user may
see a hint line *alongside* a block from `block-gh-state-all` (exit 2) or an
`ask` from `side-effect-scan`. Co-firing is intentional: the hint can
clarify *why* a block fired.

### Matching semantics

- **Whole-token equality, case-sensitive.** `hookKeywords: [kubectl]` matches
  the bare token `kubectl` but NOT `Kubectl`, `KUBECTL`, or `kubectl-prod`.
  Authors who want case-insensitive matching list the casings explicitly.
- Quoted **multi-word** strings are preserved as a single token (shlex
  behavior). `echo "use kubectl"` parses tokens as `[echo, use kubectl]`
  (the quotes are stripped, the spaces stay) — the keyword `kubectl` does
  NOT match the multi-word token. This is the false-positive guard.
- Quoted **single-word** strings are NOT protected — shlex strips the quotes
  and the bare word is matched normally. `gh search issues "kubectl"` ends
  up as `[gh, search, issues, kubectl]` and matches the `kubectl` keyword.
- Comment-prefixed lines (`# kubectl get`) DO match. `safe_tokenize` runs
  with `commenters = ""` so `#` is just another token; `kubectl` ends up as
  argv[1] of the segment and is matched. Niche case; accepted v1 behavior.

### Discovery and fail-safe

Memory directory resolution order:
1. `PRAXIS_MEMORY_DIR` env var (when set + points to an existing directory)
2. fallback `~/.claude/projects/{slugified-cwd}/memory/` — slugify rule:
   replace `/` with `-` on the absolute cwd
3. neither resolves → exit 0 silently (no fallback attempt, no error)

Five exit-0 fail-safe paths:
- python3 missing (shell wrapper guard)
- malformed JSON stdin
- non-Bash tool
- empty command
- memory directory missing or unreadable

### YAML parser limits

Pure-regex parser, no PyYAML dependency. Supported shapes: flat scalar
`hookable`, flat single-line list `hookKeywords` (e.g. `[a, b, "c d"]`),
optional `description`. Multi-line / flow-mapping / anchored YAML forms are
NOT supported — any parse error skips that memory, never the hook.

### Tests

```bash
bash tests/test_memory_hint.sh
```

Covers 21 cases: hit/silent core paths, frontmatter gates, noise cap, mtime
ordering, discovery fail-safes, malformed inputs, AC-21 (no description),
AC-22 (scalar rejection), AC-23 (case sensitivity).

## PostToolUse Built-in Task Classification

`hooks/builtin-task-postuse.py` fires after any built-in task **management**
tool executes and emits a corrective context note so Claude is not misled by
upstream hook false positives.

### Why this exists

Claude Code ships two distinct sets of `Task*` tools with completely different
semantics:

| Tool | Role | Spawns subagent? |
|------|------|-----------------|
| `Task` | Agent spawner | **Yes** |
| `TaskCreate` | Create task list entry | No |
| `TaskUpdate` | Update task list entry | No |
| `TaskGet` | Read task list entry | No |
| `TaskList` | List task list entries | No |
| `TaskStop` | Cancel task list entry | No |
| `TaskOutput` | Read task output | No |

Some upstream hooks (e.g. OMC `pre-tool-enforcer`) conflate the management
tools with `Task` and emit misleading "agent spawn" signals for them. This
PostToolUse hook fires immediately after those tools execute and injects a
correction note — "no subagent was spawned, prior signals were false positives"
— so Claude's subsequent reasoning reflects the actual operation.

### Covered tools

`TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`, `TaskStop`, `TaskOutput`

### Tests

`tests/test_builtin_task_postuse.sh` covers 18 cases: corrective output for
all 6 management tools, silent pass-through for `Task` / `Agent` / `Bash` /
`Edit` / `Write` / `Read` / `Skill`, and edge cases (empty stdin, malformed
JSON, missing tool field). Run before editing the hook:

```bash
./tests/test_builtin_task_postuse.sh
```

## Stop Hook Completion Evidence Verification

`hooks/completion-verify.sh` fires on every `Stop` event and blocks assistant
turns that declare completion without same-turn verification evidence.

### Why this exists

Memory-based feedback alone (`feedback_test_pass_not_done.md` and friends) was
insufficient — the same evidence-less "✅ done" pattern recurred across
sessions, costing one extra round-trip every time. A hook moves enforcement
from "Claude tries to remember" to "Claude is structurally blocked from
shipping unverified completion claims."

### What is blocked

When the last 10 lines of the last assistant message match `CLAIM_PATTERNS`
(완료 / 작업 완료 / `done.` / `finished.` / `all done` / `implementation
complete` / etc.), the hook checks the **current turn** — i.e., everything
since the last real user input — for verification evidence.

The turn passes only if **all** of the following hold:

| Gate | Condition |
|------|-----------|
| L1 | A `Bash` tool_use occurred in this turn |
| L3 | Its `tool_result.content` matches `EVIDENCE_PATTERNS` (`X passed`, `tests passed`, `\bPASS\b`, `exit code 0`, `lint clean`, `테스트.*통과`, `✅`, etc.) |
| L2 | At least one `EVIDENCE_PATTERNS`-matching span from that `tool_result` is paste'd verbatim in the assistant message text — e.g. `12 passed`, `tests passed`, `lint clean`, `✅` |

A claim with no Bash, with Bash but no evidence signal, or with evidence but
the verify token not quoted, all block. Tool results from non-Bash tools
(e.g. `Read`, `Write`) do **not** count as evidence — only an actually
executed Bash command qualifies. Span-based paste detection is decoration-
agnostic — pytest's `============= 12 passed in 0.85s =============` border
output passes when the assistant cites `12 passed in 0.85s`.

### Response

When blocked, the hook emits:

```json
{
  "decision": "block",
  "reason": "Completion claim detected without same-turn verification evidence. ..."
}
```

and appends an entry to `~/.claude/scope-confirm/stop-triggered.log`.

### Fail-safe paths

The hook exits 0 (passes) when any of:

- `stop_hook_active` is true (re-entry guard)
- `transcript_path` is missing or unreadable
- The transcript is empty or contains no parseable assistant text
- The claim does not appear in the last 10 lines (mid-message 완료 mention)
- `jq` is not installed

### Why "same turn" specifically

Cross-turn carry-over (verifying in turn N, claiming in turn N+1) is the
exact pattern this hook is designed to prevent — it lets stale evidence
silently age out. Strict same-turn enforcement matches the global CLAUDE.md
"Verification Before Completion" rule that requires verification commands in
the *immediately preceding* turn.

### No escape hatch

Unlike `side-effect-scan.sh` (`# side-effect:ack` marker), this hook
intentionally has **no bypass**. False positives should be reported as a new
issue, not papered over with a marker — the pattern this hook catches is the
same pattern the marker would re-enable.

### Tests

`tests/test_completion_verify.sh` covers 12 cases: 8 acceptance scenarios
(same-turn pass, no-Bash claim, no-evidence claim, no-paste claim,
mid-message claim ignored, non-Bash tool ignored, realistic pytest
output, Korean evidence) and 4 fail-safes (`stop_hook_active`, missing
transcript, empty file, malformed JSONL). Run before editing the hook:

```bash
./tests/test_completion_verify.sh
```

## Stop Hook Retrospect Mix Check

`hooks/retrospect-mix-check.sh` fires on every `Stop` event and blocks the
retrospect skill's Stage 3 output from defaulting to memory-only when
findings are tagged `tool` / `workflow` / `spec-gap`, or when memory-only
findings ship without a structured 5-line rationale.

### Why this exists

Predecessor work (`retrospect-tool-friction`) added Stage 2 step 4b (Tool
Friction Pass) and an upstream-feedback action type, but in practice the
retrospect skill kept resolving most findings as memory-only — even tool
and workflow friction got memo'd instead of escalated. A spec-only fix
(stronger Red Flags + selection matrix) was insufficient because the LLM
would acknowledge the rule and still skew memory; the same pattern that
caused this hook's existence is the one that proved memory-based feedback
alone fails. So the gate moved out-of-band: a Stop hook that parses the
structural distribution-card fence emitted by Stage 3 and rejects outputs
that violate the T3 double gate.

This is the second praxis hook to follow the "spec defines the contract,
hook enforces it" pattern (after `completion-verify.sh`).

### What is blocked

When the last assistant message contains:

1. A line matching `^## Retrospect Report` (em-dash or hyphen tail)
2. The HTML-fenced distribution card `<!-- retrospect:distribution begin -->`
3. The most recent `## Retrospect Report` block does NOT contain
   `## Actions Executed` (i.e., we're in Stage 3 awaiting approval)

…the hook parses the card and the unified findings table, then blocks if any
of the following hold:

| Trigger | Why blocked |
|---------|------------|
| `gate_1_verdict: FAIL` in the distribution card | Stage 2.5 Gate-1 (categorical) was violated |
| `gate_2_verdict: FAIL` in the distribution card | Stage 2.5 Gate-2 (procedural rationale) was violated |
| `gate_1_verdict` or `gate_2_verdict` key missing | Distribution card is malformed or Stage 2.5 was skipped |
| Any row with `Category` ∈ {tool, workflow, spec-gap} AND `Proposed Actions = memory` (single) | Gate-1 violation detected via independent table parse |
| Any row with `Proposed Actions = memory` (single) whose `Rationale` lacks exactly 5 lines `^not (issue\|claude_md_draft\|skill_idea\|hook_code\|upstream_feedback): .+$` | Gate-2 violation detected via independent table parse |

### What is NOT blocked (pass-through)

- Non-retrospect Stop events (most assistant messages)
- Retrospect outputs at Stage 4 (`## Actions Executed` present in most-recent block)
- `behavioral`-only findings with valid 5-line rationales — legitimately memory-only
- Compound actions like `memory, skill_idea` — Gate-2 only checks single `memory`

### Trigger condition summary

Hook fires only when ALL three conditions hold; this scoping is what
makes Stage 3 the gate point and prevents a previously-successful Stage 4
from creating a permanent same-session bypass.

### Fail-safe paths

The hook exits 0 (passes) when any of:

- `stop_hook_active` is true (re-entry guard)
- `transcript_path` is missing or unreadable
- The transcript is empty or contains no parseable assistant text
- The last assistant message is not a retrospect Stage 3 output (any of
  the 3 identifier conditions fails)
- `jq` is not installed
- The distribution-card fence is malformed (parse error)

### No bypass marker

Like `completion-verify.sh`, this hook intentionally has **no escape
hatch**. False positives must be reported as a new issue, not papered
over with a marker — the pattern this hook catches is the same pattern
the marker would re-enable.

### Stop hook ordering

The Stop array in `hooks/hooks.json` runs in order:
`completion-verify` → `retrospect-mix-check` → `strike-counter stop`.

`completion-verify` checks evidence-of-completion claims; `retrospect-mix-
check` checks retrospect Stage 3 mix. The two gates are independent — they
match on different signals — and both must pass. If both block, only the
first one's reason reaches the user (Claude Code Stop hooks short-circuit
on the first `decision: block`); fix the upstream issue and re-run.

### Rollback

If a hook bug produces false blocks in production:

```bash
# Option 1: revert the hooks.json registration entry
git -C ~/.claude/plugins/.../praxis apply --reverse <patch>

# Option 2: edit hooks/hooks.json, remove the retrospect-mix-check entry
#          from the "Stop" array, save.

# Option 3: temporary kill switch — edit ${CLAUDE_PLUGIN_ROOT}/hooks/
#           retrospect-mix-check.sh and add `exit 0` at the top.
```

### Tests

`tests/test_retrospect_mix_check.sh` covers 26 cases plus 4 synthetic
regression fixtures (AC-R1~R4):

- 4 pass scenarios (behavior-only with rationale, escalated tool, escalated
  workflow, compound action)
- 7 block scenarios (Gate-1 across 3 categories, Gate-2 across 4 forms,
  combined)
- 2 pass-through (non-retrospect, post-Stage-4)
- 5 fail-safe (`stop_hook_active`, missing/empty/malformed transcript, no
  `jq`)
- 3 regression (T19 same-session rerun, T20 hyphen header, T21 interaction
  with `completion-verify`)
- 5 hardening (T22 escaped pipe in cell, T23 short row schema violation,
  T24 degenerate `memory, memory`, T25 dual-card last-wins, T26 retrospect
  inside fenced code block)

Fixtures live in `tests/fixtures/retrospect-synth-{tool,workflow,behavior,
mixed}.jsonl` with `.expected.json` sidecars (`{expected_decision,
must_contain, must_not_contain}`).

```bash
./tests/test_retrospect_mix_check.sh
```

## Multi-Platform Packaging

Runtime source (`skills/`, `hooks/`, `scripts/`) is shared. Platform-specific
packaging is *generated* from canonical metadata, not hand-edited:

- `manifests/plugin.base.json` — shared metadata (name, description, author,
  repository, homepage, category, keywords). `VERSION` is the authoritative
  version string.
- `manifests/platforms/{claude,codex}.json` — per-platform output list.
- `scripts/build-plugin-manifests.py` — regenerate every artifact. Idempotent.
- `scripts/check-plugin-manifests.py` — CI drift gate. Verifies generated
  files match the source and that the Codex adapter shell's symlinks
  (`plugins/praxis/{skills,hooks,scripts}`) point at the repo root.

Generated (committed) outputs:

| Path | Consumer |
|------|----------|
| `.claude-plugin/plugin.json` | Claude plugin root |
| `.claude-plugin/marketplace.json` | Claude marketplace catalog |
| `.agents/plugins/marketplace.json` | Codex marketplace root |
| `plugins/praxis/.codex-plugin/plugin.json` | Codex plugin root |
| `plugins/praxis/{skills,hooks,scripts}` | Symlinks into repo-root runtime |

**Do not edit generated files directly.** Change `manifests/*.json` (or
`VERSION`) and re-run the build script. Run `./scripts/check-plugin-manifests.py`
before committing if you touched any packaging surface.

Adding a new platform = one file at `manifests/platforms/<name>.json` + one
build run. No skill, hook, or existing-platform changes required.

## Local Development

### Canonical clone path

This repository should live at **`~/projects/praxis`**. The CLI tools shipped
by skills (e.g. `cmux-recover-sessions`, `claude-recover`, `cmux-save-sessions`,
`cmux-browser`) are symlinked from `~/.local/bin` into this clone, so patches
you commit here land in the version that actually runs at the shell. Keeping a
second clone under a legacy name risks `~/.local/bin` symlinks pointing at stale
code — a real failure mode previously hit during recover-sessions debugging.

### CLI tools (not skills)

These are shell wrappers installed via `scripts/install.sh` into `~/.local/bin`.
They are not AI skills — they have no `SKILL.md` and cannot be invoked as `/praxis:*`.

| Binary | Source | Purpose |
|--------|--------|---------|
| `cmux-browser` | `skills/cmux-browser/cmux-browser` | Pass-through for `cmux browser`; intercepts selector-missing errors and adds subcommand-specific usage hints |

### Install / refresh CLI symlinks

```bash
# From inside this clone:
./scripts/install.sh
```

Idempotent. Existing valid links are left alone; missing or drifted ones
are corrected. Re-run after pulls or after adding a new CLI script.

### Verify symlinks point at this clone

```bash
./scripts/verify-symlinks.sh
```

Exits non-zero on drift, so it can be wired into CI or a SessionStart hook
to catch "patch landed in the wrong clone" before it bites a future session.
