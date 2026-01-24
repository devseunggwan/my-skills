---
name: context-recovery
description: Use when completing a side-task (bug fix, tool issue, dependency problem) before returning to main work. Use when you solved a blocker and are about to continue.
---

# Context Recovery

## Overview

After solving a blocking problem, explicitly return to the original goal before continuing.

**Core principle:** Side-quests are means, not ends. Always ask "What was I trying to do before this?"

## The Pattern

```
WHEN a blocker is resolved:

1. STOP - Do not continue with momentum
2. STATE - "Original goal was: [X]"
3. VERIFY - Is the blocker resolution sufficient for [X]?
4. RESUME - Continue with [X], not with tangent
```

## Red Flags

You are losing context when:
- You solved a tool/config issue and feel "done"
- You're about to start something new without checking original goal
- Someone asks about the original task and you need to think hard
- Your next action isn't directly serving the original goal

## Anti-Pattern: Momentum Trap

```
❌ WRONG:
  Fix issue-guard.sh → "It works!" → What else can I improve?

✅ RIGHT:
  Fix issue-guard.sh → "It works!" → "Original goal: test receiving-code-review skill" → Test it
```

## Implementation

After ANY side-task completion:

1. **Verbalize the original goal** - Say it out loud in response
2. **Check task list** - If using TodoWrite, check pending tasks
3. **Re-read session file** - @session-N.md contains the issue goal

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| "I'll remember" | No. State it explicitly. |
| Continuing with tangent work | Stop. State original goal. |
| Treating blocker fix as achievement | Blocker fix = prerequisite, not goal |
