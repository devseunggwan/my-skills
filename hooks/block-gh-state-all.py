#!/usr/bin/env python3
"""PreToolUse(Bash) guard: block `gh search <subcmd> ... --state all`.

`gh issue list` and `gh pr list` accept `--state all`.
`gh search issues` / `gh search prs` only accept `--state {open|closed}`.
Conflating these causes `invalid argument "all" for "--state" flag` — a
recurring mistake caught by structural enforcement rather than a memo.

Uses shlex tokenization (same approach as side-effect-scan.py) so that
pattern references inside quoted strings, echo arguments, or comments are not
mistakenly blocked.

Exits 2 (PreToolUse blocking code) when the command is a live `gh search`
call with `--state all`. Exits 0 otherwise (transparent pass-through).
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

# gh global flags that take a separate-token argument
GH_GLOBAL_FLAGS_WITH_ARG = frozenset({
    "-R", "--repo",
    "--hostname",
    "--color",
})


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_blocked_gh_search(argv: list[str]) -> bool:
    """Return True iff argv is a live `gh search <subcmd> ... --state all` call."""
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return False

    # Skip gh global flags to reach the subcommand.
    # For flags that take a separate value (e.g. -R owner/repo), consume both.
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-"):
            break  # reached the subcommand
        i += 1
        if "=" not in tok and tok in GH_GLOBAL_FLAGS_WITH_ARG and i < len(argv):
            i += 1  # consume separate value token

    if i >= len(argv) or argv[i] != "search":
        return False
    i += 1  # skip "search"

    # Skip the search object (issues, prs, repos, commits, code)
    if i >= len(argv) or argv[i].startswith("-"):
        return False  # no object word present — not a valid gh search invocation
    i += 1

    # Scan remaining tokens for --state all or --state=all
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--state="):
            if tok.split("=", 1)[1] == "all":
                return True
        elif tok == "--state" and i + 1 < len(argv) and argv[i + 1] == "all":
            return True
        i += 1

    return False


STDERR_MESSAGE = (
    "BLOCKED: `gh search <subcmd> ... --state all` is invalid.\n"
    "`gh search` subcommands only accept --state {open|closed}, not 'all'.\n"
    "Workarounds:\n"
    "  • Omit --state entirely (returns results regardless of state)\n"
    "  • Run two calls: --state open and --state closed\n"
)


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

    # Backslash line continuation → single space so tokenizer sees one line
    command = command.replace("\\\n", " ")

    tokens = safe_tokenize(command)
    if not tokens:
        return 0

    for argv in iter_command_starts(tokens):
        if is_blocked_gh_search(argv):
            sys.stderr.write(STDERR_MESSAGE)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
