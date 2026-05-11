#!/usr/bin/env python3
"""PreToolUse advisory: warn before posting hypothesis-form claims to external surfaces.

Public/shared-state writes — PR comments, issue bodies, Slack messages, Notion
pages — train downstream readers (review bots, teammates) on the published
facts. Posting hypothesis-stage thinking to these surfaces creates retraction
and noise cost when the hypothesis turns out to be false.

This hook detects:
  - Bash calls invoking `gh issue/pr comment`, `gh issue/pr create` with a body
    flag (`--body`, `-b`, `--body-file`, `-F`)
  - MCP tool calls writing to chat / docs surfaces (slack send/post,
    notion create_page / update_page)

When the body contains hypothesis markers (might / could / potentially / appears
to / is failing / 가설 / 추정), it emits a stderr advisory reminding the user
to verify each factual claim with executed evidence before posting.

Exits 0 by default — this is an advisory, not a block. Set
`PRAXIS_EXTERNAL_WRITE_STRICT=1` to convert into a hard block (exit 2).

Uses shlex tokenization (same approach as block-gh-state-all.py / side-effect-scan.py)
so that pattern references inside quoted strings, echo arguments, or comments
are not mistakenly flagged.
"""
from __future__ import annotations

import json
import os
import re
import sys

# Resolve sibling `_hook_utils.py` regardless of cwd at invocation time.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_utils import (  # type: ignore[import-not-found]  # noqa: E402
    iter_command_starts,
    safe_tokenize,
    strip_prefix,
)


# ---------------------------------------------------------------------------
# Detection — heuristic markers
# ---------------------------------------------------------------------------

# English hypothesis markers — conservative list to reduce false positives.
HYPOTHESIS_MARKERS_EN = (
    "might ", "could be", "could fail", "could break",
    "potentially", "potential ",
    "appears to", "seems to",
    "likely ", "suspected", "hypothesis",
    "is failing", "is broken",
    "may have", "may be ",
)
HYPOTHESIS_MARKERS_KO = (
    "가설", "추정", "추측", "가능성", "의심됨", "의심된다",
)


# ---------------------------------------------------------------------------
# Bash gh detection
# ---------------------------------------------------------------------------

GH_GLOBAL_FLAGS_WITH_ARG = frozenset({
    "-R", "--repo",
    "--hostname",
    "--color",
})

# `gh <obj> <sub>` pairs that write to external surfaces.
GH_WRITE_SUBCOMMANDS = frozenset({
    ("issue", "comment"),
    ("pr", "comment"),
    ("issue", "create"),
    ("pr", "create"),
    ("issue", "edit"),
    ("pr", "edit"),
    ("pr", "review"),  # accepts --body / -b / --body-file / -F; posts public review comment
})

GH_BODY_FLAGS_WITH_ARG = frozenset({"-b", "--body", "-F", "--body-file"})


def _resolve_body(flag: str, value: str) -> str:
    """Read body content. For --body-file, read file contents (best effort)."""
    if flag in {"-F", "--body-file"}:
        try:
            with open(value, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""  # treat unreadable file as empty body — advisory-only hook
    return value


def _extract_gh_flag_body(argv: list[str]) -> str | None:
    """Pull body text from --body / --body-file in a gh argv. None if absent."""
    for i, tok in enumerate(argv):
        if "=" in tok:
            key, _, val = tok.partition("=")
            if key in GH_BODY_FLAGS_WITH_ARG:
                return _resolve_body(key, val)
            continue
        if tok in GH_BODY_FLAGS_WITH_ARG and i + 1 < len(argv):
            return _resolve_body(tok, argv[i + 1])
    return None


def _gh_positional_tokens(argv: list[str]) -> list[str]:
    """Return positional (non-flag) tokens from a gh argv, with flag-with-arg pairs peeled.

    Global flags (`--repo` / `-R` / `--hostname` / `--color`) and body flags
    (`--body` / `-b` / `--body-file` / `-F`) that take a value consume the
    following token. Other flags are assumed bare — adequate for picking out
    the `<obj> <sub> <num> <body>` positional spine.
    """
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return []
    flags_with_arg = GH_GLOBAL_FLAGS_WITH_ARG | GH_BODY_FLAGS_WITH_ARG
    positional: list[str] = []
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            positional.extend(argv[i + 1:])
            break
        if tok.startswith("-"):
            i += 1
            if "=" not in tok and tok in flags_with_arg and i < len(argv):
                i += 1
            continue
        positional.append(tok)
        i += 1
    return positional


def _is_number_like(token: str) -> bool:
    """Issue/PR positional argument shape: bare integer or github URL."""
    return token.isdigit() or "://" in token


# [PR #179] P3: gh CLIs that take `<obj> <sub> <num> <body>` positional form
# (e.g. `gh issue comment 1 "body"`) bypassed flag-only body extraction.
# Detect positional body for write subcommands when the 3rd positional is
# number-like (issue/PR id or URL) and a 4th positional follows.
def _extract_gh_positional_body(argv: list[str]) -> str | None:
    """Positional body form: `gh <obj> <sub> <num-like> <body>`.

    Restricted to known write subcommands so that read-only chains like
    `gh issue list 1 2` cannot surface a stray positional as body.
    """
    positional = _gh_positional_tokens(argv)
    if len(positional) < 4:
        return None
    obj, sub, num, body = positional[0], positional[1], positional[2], positional[3]
    if (obj, sub) not in GH_WRITE_SUBCOMMANDS:
        return None
    if not _is_number_like(num):
        return None
    return body


def _extract_gh_body(argv: list[str]) -> str | None:
    """Pull body text from gh argv. Flag-style takes precedence; falls back to positional."""
    flag_body = _extract_gh_flag_body(argv)
    if flag_body is not None:
        return flag_body
    return _extract_gh_positional_body(argv)


def _is_gh_external_write(argv: list[str]) -> bool:
    """Return True iff argv invokes a gh subcommand that writes to a public surface."""
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return False

    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-"):
            break
        i += 1
        if "=" not in tok and tok in GH_GLOBAL_FLAGS_WITH_ARG and i < len(argv):
            i += 1

    if i + 1 >= len(argv):
        return False
    obj, sub = argv[i], argv[i + 1]
    return (obj, sub) in GH_WRITE_SUBCOMMANDS


# ---------------------------------------------------------------------------
# MCP detection
# ---------------------------------------------------------------------------

MCP_EXTERNAL_WRITE_PATTERNS = (
    re.compile(r".*slack.*send.*", re.IGNORECASE),
    re.compile(r".*slack.*post.*", re.IGNORECASE),
    re.compile(r".*slack.*update.*", re.IGNORECASE),
    re.compile(r".*notion.*create.*page.*", re.IGNORECASE),
    re.compile(r".*notion.*update.*page.*", re.IGNORECASE),
    re.compile(r".*notion.*append.*block.*", re.IGNORECASE),
)


def _is_mcp_external_write(tool_name: str) -> bool:
    return any(p.match(tool_name) for p in MCP_EXTERNAL_WRITE_PATTERNS)


# Keys whose value (and entire subtree) is treated as body content.
BODY_TEXT_KEYS = frozenset({
    "text", "content", "body", "message", "page_content", "rich_text",
})


# [PR #179] P2: MCP payloads nest body text under shapes like Notion's
# `children[].paragraph.rich_text[].text.content` (3 levels deep) and Slack's
# `blocks[].text.text`. A flat top-level scan missed both. Recursive walk:
# once a body-text key is entered, every descendant string is collected.
# `mrkdwn` and similar type strings inside Slack's nested text dicts can be
# false-collected, but they don't match hypothesis markers — harmless.
def _walk_collect_body(node, parts: list[str], in_body_subtree: bool) -> None:
    if isinstance(node, str):
        if in_body_subtree:
            parts.append(node)
        return
    if isinstance(node, dict):
        for key, val in node.items():
            child_in_body = in_body_subtree or (
                isinstance(key, str) and key.lower() in BODY_TEXT_KEYS
            )
            _walk_collect_body(val, parts, child_in_body)
    elif isinstance(node, list):
        for item in node:
            _walk_collect_body(item, parts, in_body_subtree)


def _extract_mcp_body(tool_input: dict) -> str:
    """Recursive body extraction from MCP tool_input.

    Walks the entire payload tree. Once a key in BODY_TEXT_KEYS is entered,
    every descendant string is collected as body content. Non-body siblings
    (channel id, block id, subject lines) are ignored. Returns empty string
    when no body keys are present.
    """
    parts: list[str] = []
    _walk_collect_body(tool_input, parts, in_body_subtree=False)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Hypothesis marker scan
# ---------------------------------------------------------------------------

def _has_hypothesis_marker(body: str) -> bool:
    if not body:
        return False
    lower = body.lower()
    if any(marker in lower for marker in HYPOTHESIS_MARKERS_EN):
        return True
    return any(marker in body for marker in HYPOTHESIS_MARKERS_KO)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

ADVISORY_MESSAGE = (
    "REMINDER (External-Surface Write Falsification): hypothesis markers "
    "detected in body.\n"
    "Before posting, verify:\n"
    "  • Has each factual claim been verified by executed evidence "
    "(query output, test pass, log inspection)?\n"
    "  • Is your verification's own premise (key, filter, schema, "
    "dimensional layout) falsified?\n"
    "  • If the verification loop has not closed, write to /tmp/ or "
    ".omc/plans/ instead.\n"
    "Set PRAXIS_EXTERNAL_WRITE_STRICT=1 to convert this advisory into a "
    "hard block (exit 2).\n"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open on malformed stdin

    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}

    body: str | None = None

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        if not command.strip():
            return 0
        command = command.replace("\\\n", " ")
        tokens = safe_tokenize(command)
        if not tokens:
            return 0
        for argv in iter_command_starts(tokens):
            if _is_gh_external_write(argv):
                candidate = _extract_gh_body(argv)
                if candidate is not None and _has_hypothesis_marker(candidate):
                    body = candidate
                    break
                # No marker in this body — keep scanning later writes in the
                # same Bash command (chained via ;, &&, ||, |, newline).
    elif _is_mcp_external_write(tool_name):
        body = _extract_mcp_body(tool_input)

    if body is None:
        return 0

    if not _has_hypothesis_marker(body):
        return 0

    sys.stderr.write(ADVISORY_MESSAGE)
    if os.environ.get("PRAXIS_EXTERNAL_WRITE_STRICT") == "1":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
