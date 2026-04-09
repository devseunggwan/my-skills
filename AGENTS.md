# Praxis

Development workflow skills for Claude Code — disciplined, fast, resilient.

Each skill is an orchestrator with pluggable steps. External integrations (issue tracker, PR tool, code review) are routed via the project's CLAUDE.md — no hardcoded dependencies.

## Skills (14)

### Workflow Lifecycle

| Skill | Purpose | Pluggable Steps |
|-------|---------|-----------------|
| `turbo-setup` | Compound setup — issue + plan + branch + worktree + deps in one pass | issue creation, planning |
| `turbo-implement` | Implementation orchestrator — selects execution mode and chains to delivery | ralph, autopilot (pluggable) |
| `turbo-deliver` | Compound delivery — auto-detects PR state for full or merge-only mode | code review, PR creation |
| `verify-completion` | Enforce verification evidence before any completion claim | — (built-in) |

### Development

| Skill | Purpose |
|-------|---------|
| `debug` | Systematic 4-phase debugging — root cause investigation before any fix |
| `brainstorm` | Diamond Model — diverge ideas, then converge with quantified evaluation |
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
│  modes: manual | ralph | autopilot | guided      │
└──────────────────────────────────────────────────┘
        │
        ▼
┌─ turbo-deliver ──────────────────────────────────┐
│  Step 0: mode detect (PR exists?)                │
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
