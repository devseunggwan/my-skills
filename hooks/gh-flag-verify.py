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
- COMPAT values are dict[str, bool] where True = flag takes a value token.
  Value tokens after value-taking flags are consumed and never re-interpreted
  as flag identifiers. This correctly handles positional query strings that
  start with '-' (e.g. `gh search issues "-label:bug"`).
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
# `gh issue list --help` / `INHERITED FLAGS` section (verified 2026-05-11).
# Note: --hostname and --color appear in `gh --help` top-level help but are
# NOT accepted by subcommands — `gh issue list --hostname github.com` returns
# "unknown flag: --hostname". Only --help/-h and --repo/-R are truly inherited.
# ---------------------------------------------------------------------------

GH_GLOBAL_FLAGS: frozenset[str] = frozenset({
    "--help", "-h",
    "--repo", "-R",
})

# gh global flags that consume one additional argument value token.
GH_GLOBAL_FLAGS_WITH_ARG: frozenset[str] = frozenset({
    "-R", "--repo",
})

# ---------------------------------------------------------------------------
# Compatibility table.
# Keys: (subcommand, subsubcommand) tuples where subsubcommand is "" when
#       there is no second word (e.g. ("issue", "list") vs ("search", "issues")).
# Values: dict[flag_name, takes_value] where takes_value=True means the flag
#         consumes the next token as its value (e.g. --assignee string).
#         takes_value=False means the flag is boolean (e.g. --archived).
#
# Sources: `gh <subcmd> [<subsubcmd>] --help` run on 2026-05-11.
# Short flags are listed in the FLAGS section as `-x, --longflag` pairs —
# only the short form is included here when the long form is already present.
# The GH_GLOBAL_FLAGS set covers inherited flags; entries below are
# subcommand-specific flags only (avoids duplication).
#
# Value-taking entries (True) skip the following token so that positional
# query strings starting with '-' (GitHub advanced-search exclusion syntax,
# e.g. `gh search issues "-label:bug"`) are not misidentified as flags.
# ---------------------------------------------------------------------------

COMPAT: dict[tuple[str, str], dict[str, bool]] = {
    # -----------------------------------------------------------------------
    # gh search issues
    # Source: `gh search issues --help`
    # -----------------------------------------------------------------------
    ("search", "issues"): {
        "--app": True,
        "--archived": False,
        "--assignee": True,
        "--author": True,
        "--closed": True,
        "--commenter": True,
        "--comments": True,
        "--created": True,
        "--include-prs": False,
        "--interactions": True,
        "--involves": True,
        "--jq": True, "-q": True,
        "--json": True,
        "--label": True,
        "--language": True,
        "--limit": True, "-L": True,
        "--locked": False,
        "--match": True,
        "--mentions": True,
        "--milestone": True,
        "--no-assignee": False,
        "--no-label": False,
        "--no-milestone": False,
        "--no-project": False,
        "--order": True,
        "--owner": True,
        "--project": True,
        "--reactions": True,
        "--repo": True, "-R": True,
        "--sort": True,
        "--state": True,        # accepts {open|closed} only — NOT "all"
        "--team-mentions": True,
        "--template": True, "-t": True,
        "--updated": True,
        "--visibility": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh search prs
    # Source: `gh search prs --help`
    # -----------------------------------------------------------------------
    ("search", "prs"): {
        "--app": True,
        "--archived": False,
        "--assignee": True,
        "--author": True,
        "--base": True, "-B": True,
        "--checks": True,
        "--closed": True,
        "--commenter": True,
        "--comments": True,
        "--created": True,
        "--draft": False,
        "--head": True, "-H": True,
        "--interactions": True,
        "--involves": True,
        "--jq": True, "-q": True,
        "--json": True,
        "--label": True,
        "--language": True,
        "--limit": True, "-L": True,
        "--locked": False,
        "--match": True,
        "--mentions": True,
        "--merged": False,
        "--merged-at": True,
        "--milestone": True,
        "--no-assignee": False,
        "--no-label": False,
        "--no-milestone": False,
        "--no-project": False,
        "--order": True,
        "--owner": True,
        "--project": True,
        "--reactions": True,
        "--repo": True, "-R": True,
        "--review": True,
        "--review-requested": True,
        "--reviewed-by": True,
        "--sort": True,
        "--state": True,        # accepts {open|closed} only — NOT "all"
        "--team-mentions": True,
        "--template": True, "-t": True,
        "--updated": True,
        "--visibility": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh search repos
    # Source: `gh search repos --help`
    # -----------------------------------------------------------------------
    ("search", "repos"): {
        "--archived": False,
        "--created": True,
        "--followers": True,
        "--forks": True,
        "--good-first-issues": True,
        "--help-wanted-issues": True,
        "--include-forks": True,
        "--jq": True, "-q": True,
        "--json": True,
        "--language": True,
        "--license": True,
        "--limit": True, "-L": True,
        "--match": True,
        "--number-topics": True,
        "--order": True,
        "--owner": True,
        "--size": True,
        "--sort": True,
        "--stars": True,
        "--template": True, "-t": True,
        "--topic": True,
        "--updated": True,
        "--visibility": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh issue list
    # Source: `gh issue list --help`
    # -----------------------------------------------------------------------
    ("issue", "list"): {
        "--app": True,
        "--assignee": True, "-a": True,
        "--author": True, "-A": True,
        "--jq": True, "-q": True,
        "--json": True,
        "--label": True, "-l": True,
        "--limit": True, "-L": True,
        "--mention": True,
        "--milestone": True, "-m": True,
        "--search": True, "-S": True,
        "--state": True, "-s": True,    # accepts {open|closed|all}
        "--template": True, "-t": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh pr list
    # Source: `gh pr list --help`
    # -----------------------------------------------------------------------
    ("pr", "list"): {
        "--app": True,
        "--assignee": True, "-a": True,
        "--author": True, "-A": True,
        "--base": True, "-B": True,
        "--draft": False, "-d": False,
        "--head": True, "-H": True,
        "--jq": True, "-q": True,
        "--json": True,
        "--label": True, "-l": True,
        "--limit": True, "-L": True,
        "--search": True, "-S": True,
        "--state": True, "-s": True,    # accepts {open|closed|merged|all}
        "--template": True, "-t": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh issue create
    # Source: `gh issue create --help`
    # -----------------------------------------------------------------------
    ("issue", "create"): {
        "--assignee": True, "-a": True,
        "--body": True, "-b": True,
        "--body-file": True, "-F": True,
        "--editor": False, "-e": False,
        "--label": True, "-l": True,
        "--milestone": True, "-m": True,
        "--project": True, "-p": True,
        "--recover": True,
        "--template": True, "-T": True,
        "--title": True, "-t": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh pr create
    # Source: `gh pr create --help`
    # -----------------------------------------------------------------------
    ("pr", "create"): {
        "--assignee": True, "-a": True,
        "--base": True, "-B": True,
        "--body": True, "-b": True,
        "--body-file": True, "-F": True,
        "--draft": False, "-d": False,
        "--dry-run": False,
        "--editor": False, "-e": False,
        "--fill": False, "-f": False,
        "--fill-first": False,
        "--fill-verbose": False,
        "--head": True, "-H": True,
        "--label": True, "-l": True,
        "--milestone": True, "-m": True,
        "--no-maintainer-edit": False,
        "--project": True, "-p": True,
        "--recover": True,
        "--reviewer": True, "-r": True,
        "--template": True, "-T": True,
        "--title": True, "-t": True,
        "--web": False, "-w": False,
    },

    # -----------------------------------------------------------------------
    # gh issue comment
    # Source: `gh issue comment --help`
    # -----------------------------------------------------------------------
    ("issue", "comment"): {
        "--body": True, "-b": True,
        "--body-file": True, "-F": True,
        "--create-if-none": False,
        "--delete-last": False,
        "--edit-last": False,
        "--editor": False, "-e": False,
        "--web": False, "-w": False,
        "--yes": False,
    },

    # -----------------------------------------------------------------------
    # gh pr comment
    # Source: `gh pr comment --help`
    # -----------------------------------------------------------------------
    ("pr", "comment"): {
        "--body": True, "-b": True,
        "--body-file": True, "-F": True,
        "--create-if-none": False,
        "--delete-last": False,
        "--edit-last": False,
        "--editor": False, "-e": False,
        "--web": False, "-w": False,
        "--yes": False,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_gh_global_flags(argv: list[str], start: int) -> tuple[int, str | None]:
    """Walk past gh global flags from index `start` to find the subcommand.

    Consumes tokens for flags that take a separate argument value
    (e.g. `-R owner/repo`). Returns (index, bad_flag) where:
    - index is the position of the first non-flag token (the subcommand).
    - bad_flag is None when all pre-subcommand flags are in GH_GLOBAL_FLAGS;
      when a `-*` token is NOT a recognized global flag, bad_flag is set to
      that token and the caller should deny.
    """
    i = start
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-"):
            break
        # Strip `=value` suffix to get the bare flag name for lookup.
        bare = tok.split("=", 1)[0]
        if bare not in GH_GLOBAL_FLAGS:
            return i, tok  # unknown pre-subcommand flag — signal denial
        i += 1
        if "=" not in tok and tok in GH_GLOBAL_FLAGS_WITH_ARG and i < len(argv):
            i += 1  # consume the value token
    return i, None


def _collect_flags(
    argv: list[str],
    flags_start: int,
    subcommand_flags: dict[str, bool],
) -> list[str]:
    """Collect flag identifiers from argv[flags_start:], skipping value tokens.

    Only collects tokens that have valid flag form:
      - Long flags: start with '--' (e.g. --label, --state)
      - Short flags: '-' followed by exactly one character (e.g. -R, -L, -w)

    Tokens like '-label:bug' (single dash + multiple chars) are GitHub
    advanced-search exclusion qualifiers used as positional arguments — they
    are NOT flag identifiers and are silently ignored. This handles cases such
    as `gh search issues "-label:bug"` where shlex strips the quotes and
    delivers '-label:bug' as a plain token.

    For value-taking flags (subcommand_flags[flag] is True or flag is in
    GH_GLOBAL_FLAGS_WITH_ARG), advances past the following token so that
    values starting with '-' are never re-interpreted as flag identifiers.
    Handles both `--flag value` and `--flag=value` forms; the latter yields
    `--flag` as the identifier (the `=value` part is stripped).
    """
    flags: list[str] = []
    i = flags_start
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            break  # end of options
        if tok.startswith("-"):
            # Determine whether this token has valid flag form.
            # Long flag: starts with '--'
            # Short flag: '-' + exactly one character
            # Anything else (e.g. '-label:bug') is a positional — skip it.
            is_long_flag = tok.startswith("--")
            is_short_flag = len(tok) == 2 and tok[0] == "-" and tok[1] != "-"
            if not is_long_flag and not is_short_flag:
                i += 1  # positional that looks like a search qualifier — ignore
                continue
            if "=" in tok:
                # --flag=value form — value is embedded; no next-token skip needed
                flag_name = tok.split("=", 1)[0]
                flags.append(flag_name)
                i += 1
            else:
                flags.append(tok)
                i += 1
                # Consume the value token when this is a value-taking flag
                # so it is never interpreted as a flag identifier.
                takes_value = subcommand_flags.get(tok) or tok in GH_GLOBAL_FLAGS_WITH_ARG
                if takes_value and i < len(argv) and argv[i] != "--":
                    i += 1  # skip the value token
        else:
            i += 1  # positional argument — skip
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
    sub_start, bad_global = _skip_gh_global_flags(argv, 1)
    if bad_global is not None:
        bare_bad = bad_global.split("=", 1)[0]
        allowed_list = ", ".join(sorted(GH_GLOBAL_FLAGS))
        reason = (
            f"Global flag '{bare_bad}' is not a recognized gh inherited flag. "
            f"Allowed: {allowed_list}. "
            f"Note: --hostname and --color are not accepted by gh subcommands."
        )
        return True, reason
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

    subcommand_flags: dict[str, bool] = COMPAT[key]
    # Build the allowed set: subcommand flag names + global flag names.
    allowed: frozenset[str] = frozenset(subcommand_flags) | GH_GLOBAL_FLAGS

    flags_in_command = _collect_flags(argv, flags_start, subcommand_flags)
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
