# Praxis

Development workflow skills for Claude Code — disciplined, fast, resilient.

Each skill is an orchestrator with pluggable steps. External integrations (issue tracker, PR tool, code review) are routed via the project's CLAUDE.md — no hardcoded dependencies.

## Prerequisites

| Tier | What works | Dependencies |
|------|-----------|--------------|
| **Standalone** | turbo-setup, recover-sessions | `gh` CLI |
| **Enhanced** | + turbo-implement, turbo-completion, debug, retrospect | + oh-my-claudecode |
| **Full** | + all cmux-* skills | + cmux |
| **Multi-provider** | + codex/gemini routing in cmux-*, turbo-implement | + codex-cli, gemini-cli |

## Skills (12)

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
| `codex` | `cat $F \| codex exec {m:+-m m}` | stdout text / `--json` JSONL | `cat file \| codex exec` | Sandbox-restricted — explicit fallback required |
| `gemini` | `gemini -p "$(cat $F)" --approval-mode yolo {m:+-m m}` | stream-json (`-o stream-json`) | via `-p` flag | Full |

All providers share the same completion sentinel: `; echo '===WORKER_DONE===' >> $LOG` appended after the CLI exits.

### Model Notation

Unified `--model` flag across all skills: `<provider>:<model>` or bare model name.

| Notation | Resolves to | CLI command |
|----------|-------------|-------------|
| `opus`, `sonnet`, `haiku` | `claude:{name}` | `claude --model {name}` |
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
elif input matches /^claude:.+$/:
  provider = "claude"
  sub_model = split(":")[1]
else:
  provider = "claude"
  sub_model = input
```

## Local Development

### Canonical clone path

This repository should live at **`~/projects/praxis`**. The CLI tools shipped
by skills (e.g. `cmux-recover-sessions`, `claude-recover`, `cmux-save-sessions`)
are symlinked from `~/.local/bin` into this clone, so patches you commit here
land in the version that actually runs at the shell. Keeping a second clone
under a legacy name risks `~/.local/bin` symlinks pointing at stale code —
a real failure mode previously hit during recover-sessions debugging.

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
