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


def _extract_gh_body(argv: list[str]) -> str | None:
    """Pull body text from --body / --body-file in a gh argv. None if absent.

    `gh issue/pr comment` and friends only accept body via flags (--body / -b
    / --body-file / -F per `gh <subcmd> --help`); positional form
    `gh issue comment <num> "body"` is rejected by gh itself with
    `accepts 1 arg(s)`. Detecting positional shape would only add noise on
    already-invalid invocations, so this extractor is flag-only.
    """
    for i, tok in enumerate(argv):
        if "=" in tok:
            key, _, val = tok.partition("=")
            if key in GH_BODY_FLAGS_WITH_ARG:
                return _resolve_body(key, val)
            continue
        if tok in GH_BODY_FLAGS_WITH_ARG and i + 1 < len(argv):
            return _resolve_body(tok, argv[i + 1])
    return None


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


# Leaf keys whose value is body content (collect descendant strings).
BODY_LEAF_KEYS = frozenset({
    "text", "content", "body", "message", "page_content",
})

# Container keys that wrap block/rich-text lists. Inside a container we
# traverse wrapper dicts (paragraph, heading_1, section, ...) until we hit
# a body leaf or another container.
BODY_CONTAINER_KEYS = frozenset({
    "children", "blocks", "rich_text",
})


# [PR #179] P2: MCP payloads nest body text under shapes like Notion's
# `children[].paragraph.rich_text[].text.content` (3 levels deep) and Slack's
# `blocks[].text.text`. A flat top-level scan missed both. An unconstrained
# recursive walk (earlier revision) over-collected siblings — page property
# titles like `properties.Name.title[].text.content` would surface and trip
# markers like "potential" / "likely" inside legitimate titles. So entry into
# body subtrees is gated: top level accepts BODY_LEAF_KEYS or BODY_CONTAINER_KEYS;
# inside containers, wrapper dicts (paragraph / section / heading_X) are
# transparent — recursion continues until a leaf is reached.
def _collect_under_leaf(node, parts: list[str]) -> None:
    """Collect every string descendant. Called once a leaf key is entered."""
    if isinstance(node, str):
        parts.append(node)
    elif isinstance(node, list):
        for item in node:
            _collect_under_leaf(item, parts)
    elif isinstance(node, dict):
        for val in node.values():
            _collect_under_leaf(val, parts)


def _walk_in_container(node, parts: list[str]) -> None:
    """Inside `children` / `blocks` / `rich_text`: traverse wrapper dicts
    (paragraph / section / heading_X) and nested containers transparently,
    switching to leaf-collection only at body keys."""
    if isinstance(node, list):
        for item in node:
            _walk_in_container(item, parts)
    elif isinstance(node, dict):
        for key, val in node.items():
            if isinstance(key, str) and key.lower() in BODY_LEAF_KEYS:
                _collect_under_leaf(val, parts)
            else:
                _walk_in_container(val, parts)


def _extract_mcp_body(tool_input: dict) -> str:
    """Body extraction from MCP tool_input gated by recognized entry points.

    At the top level only BODY_LEAF_KEYS and BODY_CONTAINER_KEYS are
    entered — sibling keys like `properties`, `parent`, `channel`, `title`
    are ignored so that property metadata (e.g. Notion page property
    titles under `properties.Name.title`) does not surface as body.
    """
    parts: list[str] = []
    for key, val in tool_input.items():
        if not isinstance(key, str):
            continue
        kl = key.lower()
        if kl in BODY_LEAF_KEYS:
            _collect_under_leaf(val, parts)
        elif kl in BODY_CONTAINER_KEYS:
            _walk_in_container(val, parts)
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
