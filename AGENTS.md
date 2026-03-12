# my-skills

Personal workflow skills for Claude Code. Provides behavioral discipline skills that orchestrate OMC agents with enforcement rules.

## Skills

| Skill | Purpose | Triggers |
|-------|---------|----------|
| `finish-branch` | Branch completion lifecycle — merge verify, cleanup, compounding | "cleanup", "finish branch", "worktree cleanup" |
| `verify-completion` | Enforce verification evidence before completion claims | "verify", "verification", "done check" |
| `debug` | Systematic 4-phase debugging with root cause investigation | "debug", "why failing", "root cause" |
| `pr-dev-to-prod` | Create release PR from dev to prod with impact analysis | "dev to prod", "release PR" |
| `install-claude-stack` | Install Claude Code plugin stack | "install stack" |

## Design Principle

- **my-skills = discipline / orchestration** (when, what order, why)
- **OMC = execution capability** (ultraqa, debugger, code-reviewer)
- Skills enforce workflow gates; OMC agents do the actual work
