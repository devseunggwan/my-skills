# Praxis

Development workflow skills for Claude Code — disciplined, fast, resilient.

Each skill is an orchestrator with pluggable steps. External integrations (issue tracker, PR tool, code review) are routed via the project's CLAUDE.md — no hardcoded dependencies.

## Prerequisites

| Tier | What works | Dependencies |
|------|-----------|--------------|
| **Standalone** | recover-sessions, strike / strikes / reset-strikes | `gh` CLI, `jq` (for strike skills) |
| **Enhanced** | + retrospect | + oh-my-claudecode |
| **Full** | + all cmux-* skills | + cmux |
| **Multi-provider** | + codex/gemini routing in cmux-* | + codex-cli, gemini-cli |

## Skills (11)

### Development

| Skill | Purpose |
|-------|---------|
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
| `cmux-browser` | Browser automation E2E testing via cmux browser CLI — SPA hydration wait included |

## Design Principles

- **CLAUDE.md is the interface**: no config files — project instructions define routing
- **SRP per skill**: each skill has one responsibility
- **Discipline over convenience**: Iron Laws gate each phase, no skipping

## Provider Routing

Skills that dispatch external CLI workers (`cmux-delegate`) can route tasks to multiple AI providers. When only `claude` is installed, the system behaves exactly as before — no errors, no degradation.

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

The hook uses structural tokenization (`safe_tokenize` → `iter_command_starts` →
`strip_prefix`) so that only live `gh search` invocations are matched. Pattern
references inside quoted strings, commit messages, grep patterns, or echo
arguments are transparent pass-throughs.

| Command | Action |
|---------|--------|
| `gh search issues "q" --state all` | **BLOCKED** (exit 2) |
| `gh search prs "q" --state=all` | **BLOCKED** (exit 2) |
| `gh search repos foo --limit 1 --state all` | **BLOCKED** (exit 2) |
| `FOO=1 gh search issues "q" --state all` | **BLOCKED** (env prefix peeled) |
| `sudo gh search issues "q" --state all` | **BLOCKED** (wrapper peeled) |
| `echo x && gh search issues "q" --state all` | **BLOCKED** (chained segment) |
| `gh issue list --state all` | **PASS** (legitimate usage) |
| `gh pr list --state all` | **PASS** (legitimate usage) |
| `gh search issues "q" --state open` | **PASS** |
| `gh search issues "q"` (no --state) | **PASS** |
| `gh pr create --body "describes --state all"` | **PASS** (body literal) |
| `git commit -m "note --state all impact"` | **PASS** (non-gh command) |
| `grep -- "--state all" docs.md` | **PASS** (grep pattern) |
| `echo "--state all is invalid"` | **PASS** (echo argument) |

### Workarounds when --state all is needed

- Omit `--state` entirely — `gh search` returns results regardless of state by default.
- Run two calls: `--state open` then `--state closed`, then merge results.

### Tests

```bash
bash hooks/test-block-gh-state-all.sh
```

Covers 29 cases: 10 block paths (including env-prefix, sudo wrapper, chained
segments), 17 pass paths (legitimate gh list, echo/grep/commit/pr-body false-positive
regressions, non-gh commands), non-Bash tool passthrough, and malformed stdin
fail-open.

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

## UserPromptSubmit Codex Review Worktree Disambiguation

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

## PreToolUse External-Write Falsify Check (opt-in)

`hooks/external-write-falsify-check.py` is an **opt-in** PreToolUse advisory
that warns before posting hypothesis-stage text to external surfaces (PR
comments, issue bodies, Slack messages, Notion pages). It enforces the
global CLAUDE.md rule `External-Surface Write Requires Falsification`
(retraction-cost / downstream-reader-training framing).

### Why this exists — and why opt-in

The four production praxis hooks (`block-gh-state-all`, `side-effect-scan`,
`memory-hint`, `codex-review-route`) each followed the canonical adoption
path: feedback-memo → ≥5 recurrences → structural hook. The
`External-Surface Write Requires Falsification` rule does not yet have
that recurrence trail (zero memory entries, zero issues at adoption time
— see issue #173). Shipping default-on would skip the established
evidence bar; shipping with the code unavailable would discard already-
written infrastructure (245 LOC + 151 LOC tests, ported `_hook_utils`
patterns).

Compromise: the code lands in `main`, **but `hooks/hooks.json` does not
register it**. Users who want the advisory enable it explicitly. This
preserves the option without changing default behavior, and gives
evidence collection a defined opt-in cohort instead of forcing the
question.

### What is warned

| Tool call shape | Warned when body contains hypothesis marker |
|----------------|----------------------------------------------|
| `gh issue comment --body <text>` | yes |
| `gh pr comment -b <text>` | yes |
| `gh pr review --comment --body <text>` (or `--approve` / `--request-changes`) | yes |
| `gh issue create --body-file <path>` | yes (file contents read) |
| `gh pr edit -F <path>` | yes |
| `mcp__*slack*__*send*` / `*post*message*` | yes (body field) |
| `mcp__*notion*__*create_page*` / `*update_page*` | yes (text fields concatenated) |
| `gh issue list` / `gh search issues` / Read tool | passthrough silent |

Hypothesis markers (whole-segment substring match): English 16 —
`might`, `could be`, `could fail`, `could break`, `potentially`,
`potential `, `appears to`, `seems to`, `likely `, `suspected`,
`hypothesis`, `is failing`, `is broken`, `may have`, `may be `; Korean 6 —
`가설`, `추정`, `추측`, `가능성`, `의심됨`, `의심된다`.

### Response

```text
REMINDER (External-Surface Write Falsification): hypothesis markers
detected in body. Verify each factual claim with executed evidence
before posting...
```

Default mode emits the reminder to stderr and **exits 0** (advisory,
not block). Set `PRAXIS_EXTERNAL_WRITE_STRICT=1` to convert into a hard
block (exit 2) — useful in CI or session-pinned workflows where you
want the gate to fire on the user's behalf.

### How to enable

Add an entry to your `~/.claude/settings.json` or `.claude/settings.json`
under `hooks.PreToolUse`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|mcp__.*slack.*|mcp__.*notion.*",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/external-write-falsify-check.sh" }
        ]
      }
    ]
  }
}
```

For strict mode (hard block):

```bash
export PRAXIS_EXTERNAL_WRITE_STRICT=1
```

Strict-mode env var accepts the **literal value `1` only** — `true` / `yes` / `on`
do NOT activate strict mode (defaults to advisory).

Restart Claude Code after adding the entry.

### Heuristic limits

The marker check is purely lexical. It cannot tell internal-team-DM
Slack from a customer-facing channel, nor can it tell a verified-fact
"could break" (an evidenced consequence) from a hypothesis "could break"
(an unverified guess). The CLAUDE.md rule's `Applies to` / `Does NOT
apply to` carveouts are NOT replicable in marker detection — the user
remains responsible for interpreting the reminder in context.

Known specific gaps (acknowledged; preconditions for any future
default-on flip — see follow-up tracking issue):

- **`likely` / `potential ` markers prone to false positives.** Phrases
  like "Most likely cause: stale cache" (a verified RCA write-up) or
  "Potential customers list: 5 brands" (business term) trip the warning.
- **Literal `\n` inside a quoted `--body` value splits the body.** The
  shared `_hook_utils.safe_tokenize` treats literal `\n` characters as
  command separators inside quoted strings. Use `--body-file` or a
  heredoc when content contains newlines and you want the full body
  scanned as one unit.
- **`--body-file -` / `-F -` (stdin) silent-passes.** `gh` accepts `-` as
  the file path placeholder for stdin (`gh issue create -F -`). The hook
  treats `-` as a literal file path; `open("-")` fails and the body is
  recorded as empty, so any hypothesis content streamed via stdin is not
  scanned. Use `--body-file <real-path>` when you want the body scanned.

### Parsing guarantees

Inherited from `_hook_utils.safe_tokenize` (same primitive as
`side-effect-scan.sh` and `block-gh-state-all.sh`):

- Quoted strings, comments, and `echo` arguments do not match markers.
- Env prefixes (`FOO=1 gh ...`), wrapper commands (`sudo`, `env`,
  `time`), shell control-flow keywords are peeled before scanning.
- Subshells (`$(...)`) are opaque to shlex — not decomposed (same
  acknowledged limitation as the sibling hooks).

### Tests

```bash
bash tests/test_external_write_falsify_check.sh
```

Covers 25 cases across the warn / silent / strict-block dimensions:
`gh` write subcommands (`comment`, `create`, `edit`, `review`) with each
body flag form (`--body`, `-b`, `--body-file`, `-F`, `--body=value`),
MCP slack / notion writes including nested shapes (Notion
`children[].paragraph.rich_text[].text.content`, Slack
`blocks[].text.text`) gated to recognized container/leaf entry points so
that property metadata (`properties.{name}.title[].text.content`) does
not surface as body, Korean marker, verified-claim silent paths,
non-write commands (`gh list` / `gh search`), chained Bash writes,
strict env toggle, and malformed-JSON fail-open.

### Evidence-trail follow-up

Memory entry for this rule + recurrence tracking will be filed as a
separate issue. The decision to flip default-on (or to roll back this
opt-in hook entirely) is gated on that trail.

Code-level preconditions for any future default-on flip are tracked in
issue #174. P2 (MCP nested-body extraction, gated to recognized
container/leaf entry points) has shipped. P3 (positional `gh` body
detection) was dropped after `gh --help` confirmed positional body is
not a supported gh CLI shape (`gh issue comment` accepts a single
positional, rejecting `<num> <body>` with `accepts 1 arg(s)`). P1
(false-positive frequency data accumulation) remains open and gates
the default-on flip.

## PreToolUse Commit Title Length Check

`hooks/commit-title-length-check.py` intercepts every AI-authored `git commit`
Bash call and emits `permissionDecision: "ask"` when the first line of the
commit message exceeds the configured maximum (default 50, matching the global
CLAUDE.md "Git Commit & Title Rules — Title: max 50 characters" rule).

### Why a PreToolUse hook instead of a git commit-msg hook

The issue body suggests a commit-msg hook because that is the natural insertion
point. However, the praxis distribution model ships Claude Code hooks (loaded
via `hooks.json`), not git-side hooks.

A git commit-msg hook would require installation into every repo's `.git/hooks/`
directory — an out-of-band setup step that is easy to miss, not portable across
worktrees, and breaks when a repo is freshly cloned. A PreToolUse hook fires
centrally for every AI-authored Bash call in any repo/worktree, with no per-repo
setup required.

Trade-off: the hook only catches AI-authored commits (not manual shell commits),
which is exactly the population that produced the silent violations described in
issue #177.

### What is warned

| Command shape | Action |
|---------------|--------|
| `git commit -m "title"` | ask when `len(title) > 50` |
| `git commit --message "title"` | ask when `len(title) > 50` |
| `git commit -m="title"` | ask when `len(title) > 50` |
| `git commit -am "title"` | ask when `len(title) > 50` |
| `git commit --amend -m "title"` | ask when `len(title) > 50` |
| `git commit -F /path/to/file` | reads first line; ask when over limit |
| `git commit -F -` (stdin) | silent pass (acknowledged limitation) |
| `Merge ...` / `Revert ...` title | silent pass (auto-generated) |
| `git status`, `git push`, etc. | silent pass (not a commit) |

Length counting uses Python `len(str)` which counts Unicode code points — the
correct measure for the 50-char rule in Korean/CJK mixed commit titles.

### Configuration

| Env var | Default | Effect |
|---------|---------|--------|
| `CLAUDE_COMMIT_TITLE_MAX` | `50` | Override the maximum title length |

Setting `CLAUDE_COMMIT_TITLE_MAX=80` allows longer titles (e.g. for repos with
a 72-char convention) without disabling the hook.

### Response

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "Commit title too long: 82 chars (max 50).\nTitle: '...'\nShorten to ≤50 chars, or embed `# title-length:ack` to bypass."
  }
}
```

### Opt-out marker

Embed `# title-length:ack` anywhere in the command to bypass the check for
known-intentional long titles (e.g. auto-generated merge commits handled by a
script):

```bash
git commit -m "Merge remote-tracking branch 'origin/main' into feature/long-name"  # title-length:ack
```

### Parsing guarantees

Inherits `safe_tokenize` / `iter_command_starts` / `strip_prefix` from
`_hook_utils.py` (same primitive as the sibling hooks):

- Shell operators (`;`, `&&`, `||`, `|`) split command segments — a chained
  `git fetch && git commit -m "long"` correctly reaches the `git commit` segment.
- Env prefixes (`GIT_AUTHOR_NAME=x git commit -m "title"`), wrapper commands
  (`sudo`, `env`), and shell control-flow keywords are peeled before matching.
- Quoted strings protect their contents — `echo "git commit -m 'fake'"` does
  not trigger the hook because `echo` is argv[0] of that segment.
- Second `-m` flag is body, not title — `git commit -m "short" -m "long body"`
  only checks the first `-m` value.
- Subshells (`$(...)`) are opaque — acknowledged limitation shared with all
  sibling hooks.
- **Literal newline inside a single quoted `-m` value bypasses the check.**
  `git commit -m "Title<newline>Body"` (where `<newline>` is an unescaped LF
  character inside the quoted string) is split by `_hook_utils.safe_tokenize`'s
  newline-aware preprocessor before shlex sees the opening quote, leaving an
  unmatched-quote fragment that gets dropped. Use `-m "title" -m "body"` or
  heredoc-assigned variables for multi-line commit messages — both extract
  the title correctly. This is a documented limitation of the shared
  tokenizer (see `_hook_utils.py` docstring), preserved to keep
  newline-separated multi-command detection intact for sibling hooks.

### Tests

```bash
bash tests/test_commit_title_length_check.sh
```

Covers 47 cases: boundary (50 chars), under (49 chars), long via `-m` /
`--message` / `-m=value` / `--amend` / `-am`, Korean 51-code-point title,
Hub #1912 regression (82-char title), Merge/Revert skip, body-in-second-m
protection, chained command, `CLAUDE_COMMIT_TITLE_MAX` override (both
directions), `-F` file (short and long), `-F -` stdin pass-through, opt-out
marker, echo false-positive guard, non-Bash tool passthrough, malformed JSON
fail-open, plus regression coverage for `git -C <dir>` global flags,
attached-form `-m"value"`, `-S<keyid>` whitelist (must not be misparsed as
combined `-m`), and `-C <dir>` + relative `-F <file>` resolution including
stacked `-C` flags.

## PreToolUse Pre-Merge Approval Gate

`hooks/pre-merge-approval-gate.py` fires on every PreToolUse(Bash) event and
intercepts `gh pr merge` invocations. In direct interactive Claude sessions the
gate emits `permissionDecision: "ask"` so the user sees the merge attempt and
must approve it in the Claude Code permission UI. Background cmux-delegate
agents (identified by `CMUX_DELEGATE=1` in their shell environment) pass
through silently — the delegation intent from the task prompt already carries
the authorization.

### Why this exists

Merge is shared-state and irreversible. A task prompt containing a
"fire-and-forget" or "no STOP gate" directive — intended for background agents
dispatched via `cmux-delegate` — can bleed into direct interactive sessions
that mistakenly apply the same exemption. This hook removes the exemption
ambiguity by making the environment variable (`CMUX_DELEGATE=1`) the sole
signal for the background-agent path.

The per-PR approval rule is already codified in the global `CLAUDE.md` (`No
Approval Transfer Across Companion PRs` and `Pre-Merge Reporting`). This hook
adds structural enforcement so the rule fires even when memory-based feedback
is not retrieved.

### What is blocked

| Scenario | Action |
|----------|--------|
| Direct session (no `CMUX_DELEGATE`), any `gh pr merge` | `permissionDecision: "ask"` |
| Background agent (`CMUX_DELEGATE=1`), any `gh pr merge` | silent pass-through |
| Inline `env CMUX_DELEGATE=1 gh pr merge` from direct session | `ask` — inline env sets the child's env, not the hook's own env |
| `# merge-approval:ack` marker (or any comment text) | `ask` — no agent-attachable bypass exists by design |
| Non-merge gh commands (`gh pr view`, `gh pr list`, etc.) | silent pass-through |
| `git commit -m "merge note"` (merge in message, not a gh call) | silent pass-through |

### Trigger

1. `tool_name == "Bash"` — non-Bash tools exit 0 silently.
2. Tokenize with `_hook_utils.safe_tokenize` + `iter_command_starts` +
   `strip_prefix` and scan every command segment.
3. Any segment whose `argv[0..2] == ("gh", "pr", "merge")` triggers the check
   (`gh` global flags such as `-R/--repo`/`--hostname`/`--color` are skipped
   so `gh -R owner/repo pr merge` is detected correctly).
4. If `CMUX_DELEGATE=1` in the hook's own process env → pass.
5. Otherwise → emit `permissionDecision: "ask"`.

### Inline env limitation (known)

The hook reads its **own** process environment, not the child's. An inline
`env CMUX_DELEGATE=1 gh pr merge` prefix only sets `CMUX_DELEGATE` for the
child `gh` process — the hook process sees no `CMUX_DELEGATE`. This is
intentional: the only authoritative delegation signal is `CMUX_DELEGATE=1`
set in the session's shell environment at startup (e.g. by `cmux-delegate`
when spawning the agent workspace).

### No opt-out marker (deliberate)

Unlike `side-effect-scan` (`# side-effect:ack`), this hook has **no
agent-attachable bypass**. Issue #180's contract is that direct sessions
ALWAYS surface a per-PR approval prompt — a comment-style marker would let
the agent silently self-bypass the same gate it is meant to enforce. The
only authoritative bypass is `CMUX_DELEGATE=1` in the *session's* shell env
at startup; inline `env CMUX_DELEGATE=1` does not satisfy this (see above).

If a legitimate direct-session merge must proceed, approve the surfaced
prompt — that single confirmation is the approval the rule requires.

### Response

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "gh pr merge detected in a direct interactive session..."
  }
}
```

### Tests

```bash
bash tests/test_pre_merge_approval_gate.sh
```

Covers direct-session ASK paths (bare, `--merge`, `--delete-branch`),
background-agent SILENT paths, non-merge command SILENT paths,
chained-command ASK paths, quoted-body SILENT (text mentions "gh pr merge"
but is not executed), inline-env ASK, non-Bash tool SILENT, malformed-JSON
SILENT, `gh -R/--repo/--hostname/--color` global-flag handling, and
regression tests confirming the previously-shipped `# merge-approval:ack`
marker no longer bypasses (round 4 finding — agent-attachable bypass
removed by design).

## Session-Scope Read-Intent vs Mutation-Pivot Gate

`hooks/session-intent.py` is a multi-event hook (`UserPromptSubmit` +
`PreToolUse`) that detects the session-scope drift pattern described in
issue [#178](https://github.com/devseunggwan/praxis/issues/178): a user
opens a session with read-intent (`compare`, `analyze`, `review`, `비교`,
`검토`, `장단점`, ...), the AI authors an A/B option menu, cumulative
"1" selections drift into a mutation cascade, and the assistant attempts a
public-surface mutation (`gh issue comment`, `gh pr merge`, ...) without
the user ever speaking an explicit mutation verb.

### Why a hook (not a skill)

Existing memory rules at the individual-decision level (`feedback_falsify_
external_finding_premise`, `feedback_no_option_cycling_after_fundamental_
block`, `feedback_self_authored_labels_not_ratified_scope`) fire per-
decision, but the friction here is at the session-trajectory level —
invisible from any single decision point. A skill cannot intercept tool
calls; only a `PreToolUse` hook can gate at the actual mutation boundary.
The "lower-resolution lexical-only" concern raised in the issue body is
addressed by combining the hook (gate) with a session state file (cross-
turn memory).

### State persistence

Hooks are independent processes — no shared in-memory state. Session
intent is persisted to a JSON file, resolved in this order:

1. `PRAXIS_SESSION_INTENT_FILE` env var (explicit path; used by tests)
2. `$CLAUDE_PROJECT_DIR/.praxis-session-intent.json` (when injected)
3. `${TMPDIR:-/tmp}/praxis-session-intent-${PPID}.json` (PPID isolates
   concurrent Claude Code sessions)

State file shape:

```json
{
  "read_intent_anchored": true,
  "read_intent_marker": "compare",
  "first_prompt_snippet": "compare pros/cons of issue 178",
  "mutation_verb_seen": false,
  "mutation_verb_seen_at": ""
}
```

The `read_intent_anchored` field is set **once** on the first prompt —
subsequent prompts do not overwrite the anchor. The `mutation_verb_seen`
field is sticky once set; it never resets within a session.

### Event handlers

**UserPromptSubmit** — scans the prompt:

1. If `read_intent_anchored` is not yet set in the state file, this is
   the session opener. Scan for read-intent markers and write the verdict
   (anchor stays for the rest of the session).
2. Independently, scan every prompt for mutation verbs. If found, set
   `mutation_verb_seen: true`. Same-utterance read + mutation verb means
   both flags get written in the same write, so the later mutation tool
   call passes silently (false-positive guard).

**PreToolUse** — only fires on `Bash` tool with a mutating `gh` command
(v1 scope). When matched:

- `read_intent_anchored == true` AND `mutation_verb_seen == false` →
  emit `permissionDecision: "ask"` (default) or `"deny"` if
  `PRAXIS_INTENT_PIVOT_MODE=block` is set.
- Otherwise → silent pass.

### Mutation-capable surface (v1 scope)

| Pattern | Action |
|---------|--------|
| `gh issue (close\|comment\|create\|edit\|delete\|reopen\|lock\|unlock\|transfer)` | gate candidate |
| `gh pr (create\|comment\|edit\|merge\|close\|reopen\|ready\|review)` | gate candidate |
| `gh release (create\|edit\|delete\|upload)` | gate candidate |
| `gh label (create\|edit\|delete)` | gate candidate |
| `gh api ... --method (POST\|PATCH\|PUT\|DELETE)` | gate candidate |
| `gh issue list`, `gh pr view`, `gh api repos/foo/bar` (default GET) | silent |
| Non-`gh` Bash commands | silent |
| MCP `mcp__*slack*__*post*`, `mcp__*notion*__*update*`, etc. | **v2** (not yet covered) |

`gh` global flags (`-R/--repo`, `--hostname`, `--color`) are peeled before
subcommand detection so `gh -R owner/repo issue create` is detected
correctly. Tokenization uses the shared `_hook_utils.safe_tokenize` /
`iter_command_starts` / `strip_prefix` pipeline so quoted bodies, env
prefixes, and shell control-flow keywords are handled consistently with
the other PreToolUse(Bash) hooks.

### Read-intent + mutation-verb lexicon

Module-level constants in `session-intent.py`. English markers are
matched as whole words (regex `(?<![A-Za-z0-9])MARKER(?![A-Za-z0-9])`)
to avoid `comment` matching `commentary`. Korean markers are matched as
substrings since CJK has no whitespace tokenization.

Read-intent (English): `compare`, `analyze`, `analyse`, `review`, `check`,
`investigate`, `explore`, `evaluate`, `assess`, `examine`, `diff`,
`pros/cons`, `pros and cons`, `trade-off`, `tradeoff`, `summary`,
`summarize`, `summarise`, `look at`, `look into`.

Read-intent (Korean): `비교`, `검토`, `분석`, `확인`, `조사`, `살펴`,
`장단점`, `요약`, `정리해`, `리뷰`, `체크`.

Mutation verbs (English): `close`, `merge`, `post`, `push`, `comment`,
`create`, `cancel`, `delete`, `remove`, `publish`, `send`, `submit`,
`approve`, `reject`, `execute`, `run it`, `go ahead`, `proceed`,
`ship it`.

Mutation verbs (Korean): `닫`, `머지`, `게시`, `푸시`, `등록`, `삭제`,
`취소`, `전송`, `보내`, `승인`, `반려`, `실행해`, `올려`, `진행해`,
`처리해`.

### Modes

| `PRAXIS_INTENT_PIVOT_MODE` | Effect |
|----------------------------|--------|
| unset (default) | `permissionDecision: "ask"` — surfaces a confirmation prompt |
| `block` | `permissionDecision: "deny"` — hard block, user must re-anchor explicitly |

### False-positive guards

- **Anchor-once semantics** — read-intent is only checked on the first
  prompt of the session. A mid-conversation `review` mention does NOT
  re-anchor the session.
- **Same-utterance read + mutation** — "review this PR and merge if
  good" records both flags simultaneously; later `gh pr merge` passes.
- **Quoted strings** — `echo "next step: gh pr merge"` does not trip the
  scan (shlex tokenization respects quotes).
- **Read-only `gh`** — `gh issue list`, `gh pr view`, `gh api repos/...`
  (default GET) are explicit silent paths.
- **Session opener without intent state** — if the mutation tool fires
  before any `UserPromptSubmit` has run (state file absent), the gate
  is silent (no anchor to compare against).

### Fail-safe paths

The hook exits 0 silently when:

- `python3` is unavailable (shell wrapper guard)
- The JSON payload is malformed
- The event type cannot be determined (unknown / missing `hookEventName`)
- The tool is not `Bash` (PreToolUse path)
- The Bash command is empty or tokenizes to zero tokens
- The state file is missing or unreadable (PreToolUse path)
- The state directory write fails (UserPromptSubmit path — gate simply
  won't fire for this session, equivalent to a missing state file)

### Tests

```bash
bash tests/test_session_intent.sh
```

21 cases: read-intent anchor write, mutation-verb flag write, mutation
tool call gate paths (ask / silent / deny / block-mode), Korean
read-intent and Korean mutation verbs, malformed JSON fail-open, unknown
event silent, quoted-string tokenization, first-call empty-state silent,
same-utterance read+mutation silent, `gh api --method POST` ask vs
default-GET silent, non-Bash tool silent, anchor-stickiness, and
`gh -R owner/repo` global-flag handling.

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
