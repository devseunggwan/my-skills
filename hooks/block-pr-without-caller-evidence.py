#!/usr/bin/env python3
"""PreToolUse(Bash) guard: block `gh pr create` without caller-chain evidence.

Blocks `gh pr create/new` unless the effective PR body contains a
`Caller chain verified:` line, enforcing a pre-PR caller-chain grep habit.

Background:
  Five converging memory rules encode the same procedure (caller-chain grep
  before PR), but memory-only enforcement fails under cognitive load (praxis
  issue #158). This hook enforces the rule at the last checkpoint before
  shared-state mutation.

Allow conditions:
  1. --help / -h invocation (read-only introspection)
  2. --repo/-R targets a different project (cross-project PR)
  3. --template/-T without --body/-b (interactive fill-in; body filled after)
  4. Effective body contains /^Caller chain verified:[ \\t]*\\S/i
  5. --body-file - (stdin; cannot inspect — allow with passthrough)
  6. --body-file <path> where file does not exist (gh itself handles the error)

Accepted line forms (all satisfy condition 4):
  Caller chain verified: grep found 3 callers in src/providers/
  Caller chain verified: new symbol, no caller expected
  Caller chain verified: planned caller in #<followup>
  Caller chain verified: N/A — docs-only change

Body sources resolved (in order):
  --body / -b  →  literal value or $VAR from earlier assignment
  --body-file PATH  →  file read; missing file → passthrough (allow)

Note: env/sudo/command prefix wrappers are transparent via strip_prefix().
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_utils import (  # type: ignore[import-not-found]
    iter_command_starts,
    safe_tokenize,
    strip_prefix,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Horizontal-whitespace-only after the colon to prevent newline bypass:
#   "Caller chain verified:\n## Next section" must NOT pass.
CALLER_CHAIN_RE = re.compile(
    r"(?m)^Caller chain verified:[ \t]*\S",
    re.IGNORECASE,
)

# Closed fenced code blocks (``` or ~~~) — strip so markers inside don't count.
_FENCED_CLOSED_RE = re.compile(
    r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.DOTALL | re.MULTILINE
)
# Unclosed fence — strip from opener to end of body.
_FENCED_OPEN_RE = re.compile(r"^(`{3,}|~{3,}).*\Z", re.DOTALL | re.MULTILINE)

# $VAR or ${VAR} references (uppercase-snake convention).
_VAR_RE = re.compile(r"\$(?:\{([A-Z_][A-Z0-9_]*)\}|([A-Z_][A-Z0-9_]*))")

# VAR=$(cat <<TAG ... TAG) assignment heredoc extraction.
_HEREDOC_ASSIGN_RE = re.compile(
    r"([A-Z_][A-Z0-9_]*)\s*=\s*\$\(\s*cat\s+<<\s*['\"]?(\w+)['\"]?\s*\n"
    r"(.*?)\n\2\s*\)",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Body helpers
# ---------------------------------------------------------------------------

def _strip_fenced_blocks(body: str) -> str:
    body = _FENCED_CLOSED_RE.sub("", body)
    return _FENCED_OPEN_RE.sub("", body)


def _build_heredoc_map(command: str) -> dict[str, str]:
    return {m.group(1): m.group(3) for m in _HEREDOC_ASSIGN_RE.finditer(command)}


def _resolve_vars(s: str, hmap: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2)
        return hmap.get(name, m.group(0))
    return _VAR_RE.sub(sub, s)


_ALLOW: None = None  # sentinel: skip block check for this invocation


def _get_effective_body(argv: list[str], hmap: dict[str, str]) -> "str | None":
    """Return the effective PR body text, or _ALLOW if inspection must be skipped.

    _ALLOW is returned when --body-file - (stdin) is encountered, or when a
    --body-file path does not exist on disk.  In both cases the hook cannot
    inspect the content; the invocation is allowed and gh itself handles any
    subsequent error (e.g. missing file).
    """
    parts: list[str] = []
    for i, t in enumerate(argv):
        if t in ("--body", "-b") and i + 1 < len(argv):
            parts.append(_resolve_vars(argv[i + 1], hmap))
        elif t.startswith("--body="):
            parts.append(_resolve_vars(t.split("=", 1)[1], hmap))
        elif t == "--body-file" and i + 1 < len(argv):
            path = argv[i + 1]
            if path == "-":
                return _ALLOW  # stdin — cannot inspect
            p = Path(path).expanduser()
            if not p.exists():
                return _ALLOW  # file missing — let gh handle the error
            parts.append(p.read_text())
        elif t.startswith("--body-file="):
            path = t.split("=", 1)[1]
            if path == "-":
                return _ALLOW  # stdin — cannot inspect
            p = Path(path).expanduser()
            if not p.exists():
                return _ALLOW  # file missing — let gh handle the error
            parts.append(p.read_text())
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _is_pr_create(argv: list[str]) -> bool:
    """True if argv is `gh pr create/new` (not --help)."""
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return False
    if any(t in ("--help", "-h") or t.startswith(("--help=", "-h="))
           for t in argv):
        return False
    try:
        pr_idx = argv.index("pr")
    except ValueError:
        return False
    return pr_idx + 1 < len(argv) and argv[pr_idx + 1] in ("create", "new")


def _has_repo_flag(argv: list[str]) -> bool:
    """True if --repo/-R is explicitly set (cross-project PR)."""
    for i, t in enumerate(argv):
        if t in ("-R", "--repo") and i + 1 < len(argv):
            return True
        if t.startswith(("--repo=", "-R")) and len(t) > 2:
            return True
    return False


def _uses_template_without_body(argv: list[str]) -> bool:
    """True if --template/-T present but no explicit --body/-b."""
    has_template = any(
        t in ("--template", "-T") or t.startswith("--template=")
        for t in argv
    )
    if not has_template:
        return False
    return not any(
        t in ("--body", "-b", "--body-file")
        or t.startswith(("--body=", "--body-file="))
        for t in argv
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

BLOCK_MSG = """\
❌ BLOCKED: `gh pr create` without caller-chain evidence.

Add a `Caller chain verified:` line to the PR body first:

  Caller chain verified: grep found N callers in <path>
  Caller chain verified: new symbol, no caller expected
  Caller chain verified: planned caller in #<followup>
  Caller chain verified: N/A -- docs-only change

Why (praxis #158):
  Five converging memory rules encode "grep caller chain before PR" but
  memory-only enforcement fails under cognitive load. This hook is the
  hard gate at the last checkpoint before shared-state mutation.

Cross-project PRs (--repo other/org) are not blocked.

Note: if you used `cat <<EOF > /tmp/body.md && gh pr create --body-file \
/tmp/body.md` and got blocked, the heredoc redirect was also aborted — the \
file does NOT exist. Use Write tool first, then a separate Bash call.
"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = payload.get("tool_input", {}).get("command", "") or ""
    if not command.strip():
        return 0

    command = command.replace("\\\n", " ")
    tokens = safe_tokenize(command)
    if not tokens:
        return 0

    hmap = _build_heredoc_map(command)

    for argv in iter_command_starts(tokens):
        argv = list(argv)
        if not _is_pr_create(argv):
            continue
        if _has_repo_flag(argv):
            continue  # cross-project PR — skip
        if _uses_template_without_body(argv):
            continue  # interactive template fill-in
        body = _get_effective_body(argv, hmap)
        if body is None:
            continue  # uninspectable source (stdin / missing file) — passthrough
        if CALLER_CHAIN_RE.search(_strip_fenced_blocks(body)):
            continue  # evidence present
        sys.stderr.write(BLOCK_MSG)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
