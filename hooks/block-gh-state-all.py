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
import re
import shlex
import sys

# ---------------------------------------------------------------------------
# Tokenization helpers — copied from side-effect-scan.py
# TODO: extract to _hook_utils.py when a third hook needs them
# ---------------------------------------------------------------------------
SHELL_SEPARATORS = {";", "&&", "||", "|", "&"}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_KEYWORDS = {
    "if", "then", "elif", "else", "fi",
    "while", "until", "do", "done",
    "case", "esac", "in", "for",
    "{", "}", "!", "function",
}
PREFIX_WRAPPERS = {"env", "sudo", "nice", "time", "stdbuf", "ionice"}
WRAPPER_OPTS_WITH_ARG = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "sudo": {
        "-u", "-g", "-p", "-C", "-D", "-r", "-t", "-T", "-U", "-h",
        "--user", "--group", "--prompt", "--close-from", "--chdir",
        "--role", "--type", "--host", "--other-user",
    },
    "nice": {"-n", "--adjustment"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "time": {"-f", "--format", "-o", "--output"},
    "ionice": {
        "-c", "--class", "-n", "--classdata",
        "-p", "--pid", "-P", "--pgid", "-u", "--uid",
    },
}

# gh global flags that take a separate-token argument
GH_GLOBAL_FLAGS_WITH_ARG = frozenset({
    "-R", "--repo",
    "--hostname",
    "--color",
})


def safe_tokenize(command: str) -> list[str]:
    """Tokenize with shell operators split into tokens and newlines as separators."""
    lines = [ln for ln in command.split("\n") if ln.strip()]
    if not lines:
        return []
    tokens: list[str] = []
    for idx, line in enumerate(lines):
        if idx > 0:
            tokens.append(";")
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=";|&")
            lex.whitespace_split = True
            lex.commenters = ""
            tokens.extend(list(lex))
        except ValueError:
            continue
    return tokens


def strip_prefix(argv: list[str]) -> list[str]:
    """Peel shell keywords, env assignments, and wrapper commands off the front."""
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok in SHELL_KEYWORDS:
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        if tok in PREFIX_WRAPPERS:
            wrapper = tok
            i += 1
            opts_with_arg = WRAPPER_OPTS_WITH_ARG.get(wrapper, set())
            while i < n:
                nxt = argv[i]
                if ENV_ASSIGN_RE.match(nxt):
                    i += 1
                    continue
                if not nxt.startswith("-"):
                    break
                if "=" in nxt:
                    i += 1
                    continue
                if nxt in opts_with_arg and i + 1 < n:
                    i += 2
                    continue
                i += 1
            continue
        break
    return argv[i:]


def iter_command_starts(tokens: list[str]):
    """Yield argv slices at each command start across shell separators."""
    start = 0
    for i, tok in enumerate(tokens):
        if tok in SHELL_SEPARATORS:
            if start < i:
                yield tokens[start:i]
            start = i + 1
    if start < len(tokens):
        yield tokens[start:]


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
