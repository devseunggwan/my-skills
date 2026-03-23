---
name: recover-sessions
description: Bulk recover Claude Code sessions after power loss or tmux crash. Interactive interview to determine recovery scope, layout, and execution mode. Triggers on "recover", "session recovery", "restore sessions", "power recovery".
---

# Recover Sessions

## Overview

Bulk recover Claude Code sessions after power loss or tmux server crash.

**Core principle:** Claude Code conversations are safely persisted to disk as `.jsonl` files. Recovery = find saved sessions and arrange them in tmux panes.

## When to Use

- After a Mac power loss when all tmux sessions are gone
- After tmux server crash that killed all running sessions
- After reboot when previous work sessions need to be restored
- Triggers: "recover", "session recovery", "restore sessions", "power recovery"

## Prerequisites

- `claude-recover` script in `skills/recover-sessions/claude-recover` (symlinked to `~/.local/bin/`)
- tmux installed (`brew install tmux`)
- Ghostty terminal (tab-based workflow)

## Process

### Step 1: Verify Script Installation

```bash
which claude-recover || echo "NOT INSTALLED"
```

If missing, create symlink:

```bash
ln -sf ~/projects/my-skills/skills/recover-sessions/claude-recover ~/.local/bin/claude-recover
```

### Step 2: Interview — Recovery Scope

Ask the user via `AskUserQuestion`:

**Q1: When did the crash happen?**

```
When did the power loss / crash occur?
1. Today (recover sessions from yesterday)
2. Yesterday
3. Last Friday (weekend crash)
4. Custom date range
```

- Option 1 → `--from <yesterday> --to <yesterday>`
- Option 2 → `--from <2 days ago> --to <yesterday>`
- Option 3 → `--from <last Monday> --to <last Friday>`
- Option 4 → Ask follow-up: "Enter start date (MM-DD or YYYY-MM-DD):" then "Enter end date (leave empty for yesterday):"

### Step 3: Scan and Present Results

Run the scan with determined date range:

```bash
claude-recover --list --from <start> --to <end>
```

Present the results to the user. If 0 sessions found, suggest widening the range.

### Step 4: Interview — Session Selection

Ask the user via `AskUserQuestion`:

**Q2: Which sessions to recover?**

```
Found N sessions. Which ones to recover?
1. All (recover everything)
2. Let me review — show me the list and I'll pick
```

If option 2: Show the numbered list and ask which numbers to include/exclude.
(Note: current script recovers all filtered sessions. For selective recovery, user can manually run `claude --resume <session-id>` for specific ones.)

### Step 5: Interview — Layout

Ask the user via `AskUserQuestion`:

**Q3: How should sessions be arranged in tmux?**

```
How many panes per Ghostty tab?
1. 1x2 — 2 panes (top/bottom, default)
2. 2x1 — 2 panes (left/right)
3. 2x2 — 4 panes (2x2 grid)
4. 3x2 — 6 panes (3 columns, 2 rows)
5. Custom (enter CxR)
```

Show calculated tab count: "N sessions ÷ P panes = T tabs"

### Step 6: Interview — Execution Mode

Ask the user via `AskUserQuestion`:

**Q4: How to open the recovered sessions?**

```
How should the tmux sessions be opened?
1. Manual — show attach commands, I'll open tabs myself
2. Auto-attach — attach to first session, show rest
3. Auto-windows — open all in Ghostty windows automatically
```

### Step 7: Final Confirmation

Present the recovery plan summary and ask for **explicit approval** before executing:

```
═══════════════════════════════════════════════
 Recovery Plan
═══════════════════════════════════════════════

 Date range:  03-18 ~ 03-20
 Sessions:    22 (filtered from 85 total)
 Layout:      2x2 (4 panes per tab)
 Tabs needed: 6
 Mode:        Manual (show attach commands)

 Command to execute:
   claude-recover --from 03-18 --to 03-20 --layout 2x2

═══════════════════════════════════════════════

Proceed with recovery?
1. Yes, execute
2. Change settings
3. Cancel
```

- Option 1 → Execute the command
- Option 2 → Return to the relevant interview step
- Option 3 → Abort

### Step 8: Execute Recovery

Run the approved command:

```bash
claude-recover --from <start> --to <end> --layout <CxR> [--attach|--windows]
```

### Step 9: Verify and Guide

After execution, verify tmux sessions were created:

```bash
tmux ls 2>/dev/null | grep "^cr-"
```

Then guide the user on attaching (output depends on the chosen mode).

## Script Reference

### CLI Options

| Option | Description |
|--------|-------------|
| `--days N` | Scan last N days |
| `--from DATE` | Start date (YYYY-MM-DD or MM-DD) |
| `--to DATE` | End date (default: yesterday) |
| `--layout CxR` | Grid layout per tab (default: 1x2) |
| `--list` | List only, don't create tmux sessions |
| `--attach` | Auto-attach to first session after creation |
| `--windows` | Open all in Ghostty windows |

### Filtering Pipeline

The script automatically excludes:

| Filter | What it removes |
|--------|----------------|
| Subagent paths | `/subagents/` directory sessions |
| Teammate sessions | `<teammate-message>` (omc team workers) |
| Team orchestrators | `oh-my-claudecode:team` command sessions |
| Command-only | Skill auto-invocations with ≤5 user messages |
| Short sessions | Less than 4 user messages |
| Schedule/auto | Known prefixes (SLA, daily commit, morning briefing, etc.) |
| Exited sessions | `/exit` or `/quit` detected in last 15 lines |
| No content | Sessions with no identifiable user message |

### Layout Examples

```
1x2 = ┌───┐    2x2 = ┌───┬───┐    3x2 = ┌───┬───┬───┐
      │ 1 │          │ 1 │ 2 │          │ 1 │ 2 │ 3 │
      ├───┤          ├───┼───┤          ├───┼───┼───┤
      │ 2 │          │ 3 │ 4 │          │ 4 │ 5 │ 6 │
      └───┘          └───┴───┘          └───┴───┴───┘
```

## Prevention: Session Naming

Prevention beats recovery. Always name sessions at startup:

```bash
claude --name "hub-700-feat-xyz"
```

Named sessions recover instantly: `claude --resume "hub-700"` (fuzzy match).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No sessions to recover" | No sessions in range | Widen `--from`/`--to` range |
| tmux creation fails | tmux not installed | `brew install tmux` |
| Wrong directory | cwd extraction failed | Check progress.cwd in jsonl |
| Ghostty windows don't open | Ghostty not running | Launch Ghostty first |

## Integration

**Workflow position:** System recovery (runs before any other skill)

```
[Power loss / Reboot] → [recover-sessions] → [Resume daily work]
```
