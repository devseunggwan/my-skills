#!/usr/bin/env python3
"""PreToolUse(Bash) guard: validate gh CLI flag-subcommand compatibility.

Intercepts every Bash tool call containing a `gh <subcmd> [<subsubcmd>]`
invocation and blocks it when any supplied `--flag` or `-x` short flag is
not in the subcommand's accepted set.

Motivation: Claude routinely pattern-matches a flag from one subcommand into
another where it does not exist (e.g. `--state all` on `gh search issues`,
`--base` on `gh issue list`), causing an `invalid argument` error that wastes
a round-trip. A static table checked before execution catches these before
the command is issued.

Design notes:
- Static frozen table: faster than runtime --help parsing, deterministic
  across gh versions in most use cases, easily extendable via issue/PR.
- Flag set sourced from `gh <subcmd> --help` output (verified live — see PR
  #176 for the captured --help outputs backing each entry).
- Unknown subcommands are transparent pass-throughs (fail-open). Only
  subcommands explicitly listed in COMPAT are validated.
- Short flags are only validated when the subcommand's table includes them.
  Many subcommands share `-R / --repo` as an inherited global flag; these
  are listed in GH_GLOBAL_FLAGS and always allowed regardless of subcommand.
- block-gh-state-all.py covers the specific `--state all` case on gh search
  subcommands. This hook may co-block the same command; both hooks run in
  parallel (PreToolUse) and deny > ask precedence means double-block is
  harmless.
- Exits 2 (deny) when an invalid flag is detected. Exits 0 otherwise.
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
# gh global flags accepted by every subcommand (inherited flags).
# These are always allowed regardless of subcommand. Sourced from
# `gh --help` / `INHERITED FLAGS` section in all subcommand help pages.
# ---------------------------------------------------------------------------

GH_GLOBAL_FLAGS: frozenset[str] = frozenset({
    "--help", "-h",
    "--repo", "-R",
    "--hostname",
    "--color",
})

# gh global flags that consume one additional argument value token.
GH_GLOBAL_FLAGS_WITH_ARG: frozenset[str] = frozenset({
    "-R", "--repo",
    "--hostname",
    "--color",
})

# ---------------------------------------------------------------------------
# Compatibility table.
# Keys: (subcommand, subsubcommand) tuples where subsubcommand is "" when
#       there is no second word (e.g. ("issue", "list") vs ("search", "issues")).
# Values: frozenset of accepted long flags (--flag) and short flags (-x).
#
# Sources: `gh <subcmd> [<subsubcmd>] --help` run on 2026-05-11.
# Short flags are listed in the FLAGS section as `-x, --longflag` pairs —
# only the short form is included here when the long form is already present.
# The GH_GLOBAL_FLAGS set covers inherited flags; entries below are
# subcommand-specific flags only (avoids duplication).
# ---------------------------------------------------------------------------

COMPAT: dict[tuple[str, str], frozenset[str]] = {
    # -----------------------------------------------------------------------
    # gh search issues
    # Source: `gh search issues --help`
    # -----------------------------------------------------------------------
    ("search", "issues"): frozenset({
        "--app",
        "--archived",
        "--assignee",
        "--author",
        "--closed",
        "--commenter",
        "--comments",
        "--created",
        "--include-prs",
        "--interactions",
        "--involves",
        "--jq", "-q",
        "--json",
        "--label",
        "--language",
        "--limit", "-L",
        "--locked",
        "--match",
        "--mentions",
        "--milestone",
        "--no-assignee",
        "--no-label",
        "--no-milestone",
        "--no-project",
        "--order",
        "--owner",
        "--project",
        "--reactions",
        "--repo", "-R",
        "--sort",
        "--state",          # accepts {open|closed} only — NOT "all"
        "--team-mentions",
        "--template", "-t",
        "--updated",
        "--visibility",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh search prs
    # Source: `gh search prs --help`
    # -----------------------------------------------------------------------
    ("search", "prs"): frozenset({
        "--app",
        "--archived",
        "--assignee",
        "--author",
        "--base", "-B",
        "--checks",
        "--closed",
        "--commenter",
        "--comments",
        "--created",
        "--draft",
        "--head", "-H",
        "--interactions",
        "--involves",
        "--jq", "-q",
        "--json",
        "--label",
        "--language",
        "--limit", "-L",
        "--locked",
        "--match",
        "--mentions",
        "--merged",
        "--merged-at",
        "--milestone",
        "--no-assignee",
        "--no-label",
        "--no-milestone",
        "--no-project",
        "--order",
        "--owner",
        "--project",
        "--reactions",
        "--repo", "-R",
        "--review",
        "--review-requested",
        "--reviewed-by",
        "--sort",
        "--state",          # accepts {open|closed} only — NOT "all"
        "--team-mentions",
        "--template", "-t",
        "--updated",
        "--visibility",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh search repos
    # Source: `gh search repos --help`
    # -----------------------------------------------------------------------
    ("search", "repos"): frozenset({
        "--archived",
        "--created",
        "--followers",
        "--forks",
        "--good-first-issues",
        "--help-wanted-issues",
        "--include-forks",
        "--jq", "-q",
        "--json",
        "--language",
        "--license",
        "--limit", "-L",
        "--match",
        "--number-topics",
        "--order",
        "--owner",
        "--size",
        "--sort",
        "--stars",
        "--template", "-t",
        "--topic",
        "--updated",
        "--visibility",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh issue list
    # Source: `gh issue list --help`
    # -----------------------------------------------------------------------
    ("issue", "list"): frozenset({
        "--app",
        "--assignee", "-a",
        "--author", "-A",
        "--jq", "-q",
        "--json",
        "--label", "-l",
        "--limit", "-L",
        "--mention",
        "--milestone", "-m",
        "--search", "-S",
        "--state", "-s",    # accepts {open|closed|all}
        "--template", "-t",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh pr list
    # Source: `gh pr list --help`
    # -----------------------------------------------------------------------
    ("pr", "list"): frozenset({
        "--app",
        "--assignee", "-a",
        "--author", "-A",
        "--base", "-B",
        "--draft", "-d",
        "--head", "-H",
        "--jq", "-q",
        "--json",
        "--label", "-l",
        "--limit", "-L",
        "--search", "-S",
        "--state", "-s",    # accepts {open|closed|merged|all}
        "--template", "-t",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh issue create
    # Source: `gh issue create --help`
    # -----------------------------------------------------------------------
    ("issue", "create"): frozenset({
        "--assignee", "-a",
        "--body", "-b",
        "--body-file", "-F",
        "--editor", "-e",
        "--label", "-l",
        "--milestone", "-m",
        "--project", "-p",
        "--recover",
        "--template", "-T",
        "--title", "-t",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh pr create
    # Source: `gh pr create --help`
    # -----------------------------------------------------------------------
    ("pr", "create"): frozenset({
        "--assignee", "-a",
        "--base", "-B",
        "--body", "-b",
        "--body-file", "-F",
        "--draft", "-d",
        "--dry-run",
        "--editor", "-e",
        "--fill", "-f",
        "--fill-first",
        "--fill-verbose",
        "--head", "-H",
        "--label", "-l",
        "--milestone", "-m",
        "--no-maintainer-edit",
        "--project", "-p",
        "--recover",
        "--reviewer", "-r",
        "--template", "-T",
        "--title", "-t",
        "--web", "-w",
    }),

    # -----------------------------------------------------------------------
    # gh issue comment
    # Source: `gh issue comment --help`
    # -----------------------------------------------------------------------
    ("issue", "comment"): frozenset({
        "--body", "-b",
        "--body-file", "-F",
        "--create-if-none",
        "--delete-last",
        "--edit-last",
        "--editor", "-e",
        "--web", "-w",
        "--yes",
    }),

    # -----------------------------------------------------------------------
    # gh pr comment
    # Source: `gh pr comment --help`
    # -----------------------------------------------------------------------
    ("pr", "comment"): frozenset({
        "--body", "-b",
        "--body-file", "-F",
        "--create-if-none",
        "--delete-last",
        "--edit-last",
        "--editor", "-e",
        "--web", "-w",
        "--yes",
    }),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_gh_global_flags(argv: list[str], start: int) -> int:
    """Walk past gh global flags from index `start` to find the subcommand.

    Consumes tokens for flags that take a separate argument value
    (e.g. `-R owner/repo`). Returns the index of the first non-flag token.
    """
    i = start
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-"):
            break
        i += 1
        if "=" not in tok and tok in GH_GLOBAL_FLAGS_WITH_ARG and i < len(argv):
            i += 1  # consume the value token
    return i


def _extract_flags(argv: list[str], flags_start: int) -> list[str]:
    """Extract all flag tokens (tokens starting with '-') from argv[flags_start:].

    Value tokens after `--flag value` pairs are not collected — we only care
    about the flag identifiers themselves. Handles both `--flag value` and
    `--flag=value` forms; the latter yields `--flag` as the flag identifier
    (we strip the `=value` part before comparing).

    Positional arguments (issue numbers, query strings, etc.) are ignored.
    """
    flags: list[str] = []
    i = flags_start
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            break  # end of options
        if tok.startswith("-"):
            if "=" in tok:
                # --flag=value → flag is everything before first '='
                flags.append(tok.split("=", 1)[0])
            else:
                flags.append(tok)
        i += 1
    return flags


def check_gh_flags(argv: list[str]) -> tuple[bool, str]:
    """Check a single command segment for gh flag compatibility.

    Returns (is_invalid, reason_message).
    is_invalid=True means the command should be blocked.
    """
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return False, ""

    # Walk past any gh global flags to find the subcommand word.
    sub_start = _skip_gh_global_flags(argv, 1)
    if sub_start >= len(argv):
        return False, ""  # no subcommand present

    subcommand = argv[sub_start]
    if subcommand.startswith("-"):
        return False, ""  # flag where subcommand expected — malformed, skip

    # Determine whether this subcommand has a sub-subcommand (e.g. "search issues").
    subsubcommand = ""
    flags_start = sub_start + 1
    key: tuple[str, str]

    # Check two-word form first (e.g. search issues, search prs).
    if flags_start < len(argv) and not argv[flags_start].startswith("-"):
        candidate_subsub = argv[flags_start]
        two_word_key = (subcommand, candidate_subsub)
        if two_word_key in COMPAT:
            subsubcommand = candidate_subsub
            flags_start += 1
            key = two_word_key
        else:
            # Try single-word key (e.g. issue list, pr create).
            one_word_key = (subcommand, argv[flags_start])
            if one_word_key in COMPAT:
                subsubcommand = argv[flags_start]
                flags_start += 1
                key = one_word_key
            else:
                return False, ""  # unknown subcommand — pass through
    else:
        key = (subcommand, "")
        if key not in COMPAT:
            return False, ""  # unknown subcommand — pass through

    allowed = COMPAT[key] | GH_GLOBAL_FLAGS

    flags_in_command = _extract_flags(argv, flags_start)
    for flag in flags_in_command:
        if flag not in allowed:
            subcmd_display = (
                f"gh {subcommand} {subsubcommand}".strip()
                if subsubcommand
                else f"gh {subcommand}"
            )
            reason = (
                f"Flag '{flag}' is not valid for '{subcmd_display}'. "
                f"Run 'gh {subcommand}"
                + (f" {subsubcommand}" if subsubcommand else "")
                + " --help' to see accepted flags."
            )
            return True, reason

    return False, ""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _emit_deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
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

    # Collapse backslash line continuations so multi-line invocations parse
    # as a single command segment (same pre-processing as sibling hooks).
    command = command.replace("\\\n", " ")

    tokens = safe_tokenize(command)
    if not tokens:
        return 0

    for argv in iter_command_starts(tokens):
        is_invalid, reason = check_gh_flags(argv)
        if is_invalid:
            _emit_deny(reason)
            return 2  # deny exit code

    return 0


if __name__ == "__main__":
    sys.exit(main())
