---
name: cmux-hook-install
description: >
  Install cmux claude-hooks into ~/.claude/settings.json.
  Detects symlink, validates idempotency, creates backup.
---

# cmux-hook-install

## Overview

Installs 4 cmux claude-hooks into Claude Code settings.json:
- session-start
- prompt-submit
- stop
- notification

**Core principle:** Safe, idempotent, portable. Detects symlinks and refuses to modify them directly.

## When to Use

- First-time setup on a new machine
- Re-running after cmux updates
- Verifying existing hooks

## Execution Modes

| Mode | Condition | Action |
|------|----------|--------|
| **A** | settings.json is regular file | Direct modification + backup |
| **B** | settings.json is symlink | Show PR workflow guide, exit |
| **C** | cmux not installed | Show install guide, exit |

## Process

### Step 1: Detect settings.json

```bash
SETTINGS_PATH="${HOME}/.claude/settings.json"

# Check existence
if [ ! -f "$SETTINGS_PATH" ]; then
  echo "Error: settings.json not found at $SETTINGS_PATH"
  exit 1
fi

# Detect symlink
if [ -L "$SETTINGS_PATH" ]; then
  TARGET=$(readlink -f "$SETTINGS_PATH")
  echo "Detected symlink: $SETTINGS_PATH -> $TARGET"
  echo "Cannot modify symlink target directly."
  exit 2  # Mode B
fi
```

### Step 2: Check cmux availability

```bash
if ! command -v cmux >/dev/null 2>&1; then
  echo "Error: cmux not installed"
  echo "Install: brew install cmux (or via oh-my-claudecode)"
  exit 3  # Mode C
fi
```

### Step 3: Check idempotency

```bash
if grep -q '"cmux claude-hook' "$SETTINGS_PATH" 2>/dev/null; then
  echo "Existing cmux claude-hooks detected. Skipping (idempotent)."
  exit 0
fi
```

### Step 4: Create backup

```bash
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_PATH="${SETTINGS_PATH}.bak.${TIMESTAMP}"
cp "$SETTINGS_PATH" "$BACKUP_PATH"
echo "Backup created: $BACKUP_PATH"
```

### Step 5: Add hooks via jq

```bash
# Define hooks
HOOKS='[
  {"event": "sessionStart", "promptCommand": "cmux claude-hook session-start"},
  {"event": "promptSubmit", "promptCommand": "cmux claude-hook prompt-submit"},
  {"event": "Stop", "promptCommand": "cmux claude-hook stop"},
  {"event": "Notification", "promptCommand": "cmux claude-hook notification"}
]'

# Merge into existing hooks array or create new
jq -s 'if .[0].hooks then .[0].hooks += .[1] else .[0] + {"hooks": .[1]} end' \
  "$SETTINGS_PATH" <(echo "$HOOKS") > "${SETTINGS_PATH}.tmp" && \
  mv "${SETTINGS_PATH}.tmp" "$SETTINGS_PATH"
```

### Step 6: Validate JSON

```bash
if ! jq empty "$SETTINGS_PATH" 2>/dev/null; then
  echo "Error: Invalid JSON after modification"
  echo "Restoring from backup..."
  cp "$BACKUP_PATH" "$SETTINGS_PATH"
  exit 4
fi
echo "JSON validated OK"
```

### Step 7: Smoke test

```bash
echo '{}' | cmux claude-hook session-start 2>&1 | head -1
```

## Rollback

```bash
BACKUP=$(ls -t "${HOME}/.claude/settings.json".bak.* | head -1)
if [ -n "$BACKUP" ]; then
  cp "$BACKUP" "${HOME}/.claude/settings.json"
  echo "Restored from: $BACKUP"
fi
```

## Exit Codes

| Code | Meaning |
|------|--------|
| 0 | Success (hooks installed or already present) |
| 1 | settings.json not found |
| 2 | Symlink detected (do not modify) |
| 3 | cmux not installed |
| 4 | JSON validation failed |