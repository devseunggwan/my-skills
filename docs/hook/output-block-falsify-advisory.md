# PreToolUse Output-Block Falsification Advisory

`hooks/output-block-falsify-advisory.py` fires on every `PreToolUse` event
for `AskUserQuestion` and `Bash` tool calls. It detects two surfaces where
a self-authored proposal block is about to be surfaced without a falsification
check and emits an advisory reminder.

### Why this exists

The global CLAUDE.md rule **"Output-Block-Level Falsification Gate"** instructs:

> Before surfacing a self-authored proposal as a complete output block, run
> an explicit falsification test on its premise. If a concrete invalidating
> link/artifact exists — STOP. Do not surface the proposal.

Despite this rule being loaded into context (4+ memory entries accumulated
2026-05-03 through 2026-05-13), the retrieval trigger does not fire at the
specific moment the proposal block is authored. The pattern is consistent:
same-session repeats where a wrong-framing issue cancelled at T+0 recurs
with an identical anti-pattern at T+1h.

Text rules and MEMORY.md entries alone have proven insufficient to prevent
recurrence. A structural hook moves the gate to the tool-call use-site.

Reference: issue [#221](https://github.com/devseunggwan/praxis/issues/221).

**Escalation criteria:** After ~1 month of advisory operation (target: ~2026-06-15),
evaluate recurrence rate. If advisory is repeatedly bypassed without falsification,
escalate to blocking (`exit 2`) for the `AskUserQuestion` `(Recommended)` surface.

### What is detected

| Tool | Trigger condition | Advisory emitted |
|------|-----------------|-----------------|
| `AskUserQuestion` | Any option `label` contains `(Recommended)` or `(추천)` (case-insensitive for English form) | Yes |
| `Bash` | Command matches a bulk-action mutation keyword (see table below) | Yes |
| Any other tool | — | Silent pass-through |
| Malformed payload / missing field | — | Silent fail-open |

**This hook never blocks.** Advisory mode only — exit 0 in all cases.

#### AskUserQuestion: (Recommended) marker

`(Recommended)` and `(추천)` in option labels are the canonical signal for a
self-authored proposal block about to be surfaced. The CLAUDE.md rule names
`(Recommended)` as a primary trigger for the falsification gate.

#### Bash: bulk-action mutation keywords

| Type | Patterns detected |
|------|-----------------|
| English (regex, case-insensitive) | `close\s+all`, `delete\s+all`, `merge\s+all`, `reject\s+all`, `approve\s+all` |
| Korean (substring) | `전부 닫`, `모두 닫`, `전부 삭제`, `모두 삭제`, `전부 머지`, `모두 머지`, `다 머지`, `전부 클로즈`, `모두 클로즈` |

Bulk-action commands often reflect a downstream consequence of a proposal block
whose premise was not falsified ("close all linked issues" after a misframed
proposal). The advisory fires conservatively: only mutation-verb patterns are
matched; read-only commands (`git log --all`, `gh pr list`) do not fire.

### Response shape

**Advisory message** (emitted to stderr, never stdout):

```
[output-block-falsify-advisory] Surfacing a recommendation/bulk-action
proposal? Run the output-block falsification gate first: is the proposal's
premise already addressed by in-flight work, a merged PR, or a parallel
proposal in this session? If yes — STOP and cite the invalidating link
instead of surfacing the proposal.
```

**Exit code:** always `0` (never blocks).

**JSON response:** none — the hook communicates via stderr only
(`additionalContext` in Claude Code's terminology). Claude Code reads stderr
from advisory PreToolUse hooks and includes it in the model's context.

### Parsing guarantees

| Condition | Behavior |
|-----------|----------|
| Malformed / missing stdin JSON | exit 0 (silent pass) |
| `tool_name` not `AskUserQuestion` or `Bash` | exit 0 (silent pass) |
| Missing `questions` / `options` / `command` fields | exit 0 (silent pass) |
| `python3` unavailable | exit 0 (shell shim guards) |
| Hook `.py` file missing | exit 0 (shell shim guards) |
| Any uncaught exception | exit 0 (silent pass, no crash) |

The hook uses no external dependencies (no PyYAML, no third-party packages).
All parsing is done with the Python standard library only.

### Tests

```bash
bash tests/test_output_block_falsify_advisory.sh
```

Covers 10 cases:

**Positive (AskUserQuestion):**
- Option label `(Recommended)` → advisory emitted
- Option label `(추천)` → advisory emitted

**Negative (AskUserQuestion):**
- Option labels without marker → silent pass

**Positive (Bash):**
- `gh pr merge --all` with "merge all" phrasing → advisory emitted
- `gh issue close --all` with "close all" phrasing → advisory emitted
- Korean: `모두 삭제` → advisory emitted

**Negative (Bash):**
- `git status` → silent pass
- `gh pr list --all` (read-only, no mutation verb) → silent pass

**Edge:**
- Malformed JSON stdin → exit 0, silent pass
- Empty payload → exit 0, silent pass
