---
name: cmux-resume-sessions
description: >
  Restore cmux workspaces from a JSON snapshot.
  Uses snapshots saved by cmux-save-sessions as input.
  Triggers on "resume sessions", "session restore", "session resume", "cmux resume", "restore sessions".
---

# cmux Resume Sessions

## Overview

Restores cmux workspaces from a JSON snapshot saved by `cmux-save-sessions`.
Restores workspace structure (name, cwd) and continues Claude Code conversations automatically.

> **Role separation**:
> - `cmux-resume-sessions`: Intentional restore from JSON snapshot (file-based)
> - `cmux-recover-sessions`: Post-crash/power-loss recovery from tmux sessions (process-based)

## The Iron Law

```
RESUME RESTORES STRUCTURE AND CONTINUES CONVERSATIONS.
```

Resume restores workspace structure (name, cwd) and runs `claude --continue` to pick up the most recent conversation in each directory.
It does NOT restore runtime state of previously running commands or sessions.

## Commands

### `resume [snapshot]` — Restore sessions from snapshot

**How to run:**
1. User requests "resume sessions", "session restore", etc.
2. Snapshot selection:
   - No argument: use the most recent snapshot
   - Filename or full path specified: use that snapshot
3. Execute:
```bash
bash "$(dirname "$0")/cmux-resume-sessions" [snapshot-file]
```
4. Show output to the user

**What gets restored:**
- Creates a cmux workspace per session (with `--cwd` for working directory)
- Sets workspace name to match the saved name
- Runs `claude --continue` in each workspace (continues the most recent conversation for that cwd)
- Sessions with non-existent cwd are skipped (with warning)

**Flags:**
- `--no-claude`: Skip auto-starting Claude Code (restore workspace structure only)

**What is NOT restored:**
- Previously running commands
- Session runtime state (git status, open editors, etc.)

## Output Example

```
Resuming from: sessions-20260407-143000.json
  Saved at: 2026-04-07T14:30:00+0900 | Host: macbook-pro.local | Sessions: 7

  ✓ Review PR comments → workspace:150 (/Users/nathan.song/projects/hub)
  ✓ Fix auth bug → workspace:151 (/Users/nathan.song/projects/backend)
  ⚠ SKIP: Old worktree task (cwd not found: /tmp/wt-deleted)
  ✗ FAIL: Broken session

Done. Created: 2 | Skipped: 1 | Failed: 1
```

## Integration

- **cmux-save-sessions**: Produces the input data for this skill
- **cmux-session-manager**: Use `status` to verify results after restore
- **cmux-orchestrator**: Can restart workers in restored workspaces

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "cmux is not running" | cmux app not running | Start cmux app |
| "jq is required" | jq not installed | `brew install jq` |
| "cwd not found" | Directory was deleted since save | Session is auto-skipped |
| "No snapshots" | No saved snapshots exist | Save first with `cmux-save-sessions` |
| Duplicate sessions created | Overlap with already-open sessions | Check existing sessions before restore |
