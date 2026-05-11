#!/usr/bin/env python3
"""PreToolUse(Bash) guard: enforce 50-character limit on git commit titles.

Global CLAUDE.md rule: "Git Commit & Title Rules — Title: max 50 characters".
This hook intercepts AI-authored `git commit` Bash calls before they execute
and emits permissionDecision "ask" when the first line of the commit message
exceeds the configured maximum (default 50, override via CLAUDE_COMMIT_TITLE_MAX).

Why a PreToolUse hook instead of a git commit-msg hook:
  The praxis distribution model ships Claude Code hooks (loaded via hooks.json).
  A git commit-msg hook would require installation into every repo's .git/hooks/
  directory — an out-of-band setup step that is easy to miss, not portable across
  worktrees, and breaks when a repo is freshly cloned. A PreToolUse hook fires
  centrally for every AI-authored Bash call in any repo/worktree, with no per-repo
  setup required. Trade-off: it only catches AI-authored commits (not manual shell
  commits), which is exactly the population that produced the silent violations.

Detection path:
  git commit [-m|-F|--message|--file] <value>  →  extract title (first line)
  len(title) > MAX                              →  emit permissionDecision "ask"

Opt-out: embed `# title-length:ack` anywhere in the command to bypass.
Skip: Merge / Revert commits, -F - (stdin body), unreadable -F files.
Config: CLAUDE_COMMIT_TITLE_MAX=<n> (integer ≥ 1) overrides default 50.
"""
from __future__ import annotations

import json
import os
import sys

# Resolve sibling `_hook_utils.py` regardless of cwd at invocation time.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_utils import (  # type: ignore[import-not-found]  # noqa: E402
    iter_command_starts,
    safe_tokenize,
    strip_prefix,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX = 50
OPT_OUT_MARKER = "# title-length:ack"

# Prefixes that indicate auto-generated merge/revert commits — skip them.
SKIP_PREFIXES = ("Merge ", "Revert ")

# Flags that carry the commit message as the next token (or in --flag=value form).
MESSAGE_FLAGS = frozenset({"-m", "--message"})
# Flags that carry a file path whose first line is the title.
FILE_FLAGS = frozenset({"-F", "--file"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_max() -> int:
    """Read CLAUDE_COMMIT_TITLE_MAX; fall back to DEFAULT_MAX on invalid value."""
    raw = os.environ.get("CLAUDE_COMMIT_TITLE_MAX", "")
    if raw.strip():
        try:
            val = int(raw.strip())
            if val >= 1:
                return val
        except ValueError:
            pass
    return DEFAULT_MAX


def _title_from_file(path: str) -> str | None:
    """Read first line of a file; return None on any error or if stdin placeholder."""
    if path == "-":
        return None  # stdin — acknowledged limitation, silent pass
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.readline().rstrip("\n")
    except OSError:
        return None  # unreadable — silent pass


def _extract_titles(argv: list[str]) -> list[str]:
    """Extract commit title candidates from a git-commit argv.

    Only the FIRST -m / --message flag contributes the title; subsequent -m
    flags are body paragraphs and are ignored (git treats them that way).
    -F / --file reads the file and takes the first line.

    Handles:
      git commit -m "title"
      git commit --message "title"
      git commit -m="title" / --message="title"
      git commit -F /tmp/msg
      git commit --file /tmp/msg
      git commit -am "title"   (combined short flag, e.g. -a -m together)
      git commit --amend -m "title"
    """
    argv = strip_prefix(argv)
    if not argv or argv[0] != "git":
        return []
    if len(argv) < 2 or argv[1] != "commit":
        return []

    titles: list[str] = []
    message_seen = False
    i = 2
    while i < len(argv):
        tok = argv[i]

        # Handle --flag=value embedded form.
        if "=" in tok and not tok.startswith("-") is False:
            key, _, val = tok.partition("=")
            if key in MESSAGE_FLAGS and not message_seen:
                titles.append(val.split("\n")[0])
                message_seen = True
                i += 1
                continue
            if key in FILE_FLAGS:
                t = _title_from_file(val)
                if t is not None:
                    titles.append(t)
                i += 1
                continue

        # Handle combined short flags like -am "title" (git allows -a -m merged).
        # Pattern: token starts with '-', contains 'm', and is not a long flag.
        if (
            tok.startswith("-")
            and not tok.startswith("--")
            and "m" in tok[1:]
            and not message_seen
        ):
            # e.g. "-am" → treat as if -m follows
            if i + 1 < len(argv):
                titles.append(argv[i + 1].split("\n")[0])
                message_seen = True
                i += 2
                continue

        # Standard separate-token flags.
        if tok in MESSAGE_FLAGS and not message_seen:
            if i + 1 < len(argv):
                titles.append(argv[i + 1].split("\n")[0])
                message_seen = True
                i += 2
                continue
            i += 1
            continue

        if tok in FILE_FLAGS:
            if i + 1 < len(argv):
                t = _title_from_file(argv[i + 1])
                if t is not None:
                    titles.append(t)
                i += 2
                continue
            i += 1
            continue

        i += 1

    return titles


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _emit_ask(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open on malformed stdin

    if payload.get("tool_name") != "Bash":
        return 0

    command = payload.get("tool_input", {}).get("command", "") or ""
    if not command.strip():
        return 0

    if OPT_OUT_MARKER in command:
        return 0

    tokens = safe_tokenize(command)
    if not tokens:
        return 0

    max_len = _get_max()

    for argv in iter_command_starts(tokens):
        titles = _extract_titles(argv)
        for title in titles:
            if any(title.startswith(p) for p in SKIP_PREFIXES):
                continue
            length = len(title)
            if length > max_len:
                _emit_ask(
                    f"Commit title too long: {length} chars (max {max_len}).\n"
                    f"Title: {title!r}\n"
                    "Shorten to ≤50 chars, or embed `# title-length:ack` to bypass."
                )
                return 0  # ask emitted; only report first violation

    return 0


if __name__ == "__main__":
    sys.exit(main())
