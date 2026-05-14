#!/usr/bin/env python3
"""PreToolUse(Bash) guard: cross-boundary pre-flight for gh write operations.

Intercepts two patterns:

1. CROSS_REPO_WRITE — `gh pr create / issue create/comment/edit --repo <X>`
   Emits permissionDecision "ask" with a four-point checklist before the
   command executes. The user must confirm all contracts are satisfied.

2. HEREDOC_BODY — `gh pr create / issue create` with a `<<` heredoc operator
   in the same command segment. Hard-blocks (exit 2) and suggests --body-file.

Related hooks that cover adjacent scenarios:
  block-gh-state-all.sh            → gh search --state all
  block-pr-without-caller-evidence → gh pr create without Caller chain verified:
  pre-merge-approval-gate.sh       → gh pr merge without per-PR approval

Opt-out: embed `# cross-boundary:ack` in the shell command portion of the
invocation (e.g., as a trailing comment on the `gh` line or after the heredoc
terminator), NOT inside the heredoc body. The heredoc body becomes the
published artifact — a marker placed there leaks into the issue/PR text on
the remote surface. After manually confirming all checklist items, re-run
with the marker in the command shell portion only.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_utils import (  # type: ignore[import-not-found]  # noqa: E402
    iter_command_starts,
    safe_tokenize,
    strip_prefix,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GH_GLOBAL_FLAGS_WITH_ARG = frozenset({"-R", "--repo", "--hostname", "--color"})

# gh subcommand pairs that write to a repo
GH_WRITE_SUBCOMMANDS = frozenset({
    ("pr", "create"), ("pr", "new"),
    ("issue", "create"), ("issue", "new"),
    ("issue", "comment"), ("issue", "edit"),
    ("pr", "comment"), ("pr", "edit"),
})

OPT_OUT_MARKER = "# cross-boundary:ack"

HEREDOC_BLOCK_MSG = """\
❌ BLOCKED: heredoc (`<<`) in `gh pr/issue create`.

Inline heredoc bodies bypass the praxis PreToolUse hook chain — shlex
tokenization does not read heredoc content, so the caller-chain evidence
check and external-write falsify-check see an empty body.

Correct pattern:
  1. Write body to a temp file (Write tool):
       /tmp/pr-body.md  or  /tmp/issue-body.md

  2. Pass via --body-file:
       gh issue create --title "..." --body-file /tmp/issue-body.md
       gh pr create    --title "..." --body-file /tmp/pr-body.md

  3. If the Write-tool + --body-file path is itself blocked by another guard,
     use `# cross-boundary:ack` to bypass the ASK gate after manually
     confirming all checklist items. Place the marker in the shell command
     portion ONLY — on the same `gh` line or after the heredoc terminator,
     never inside the heredoc body. The heredoc body becomes the published
     artifact; a marker inside it leaks verbatim into the issue/PR text on
     the remote surface.
       gh pr create --title "..." --body-file /tmp/b.md  # cross-boundary:ack
"""


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _skip_flags(argv: list[str], i: int) -> int:
    """Advance i past any flags (and their values) in argv, return new i."""
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            return i + 1
        if not tok.startswith("-"):
            break
        i += 1
        if "=" not in tok and tok in GH_GLOBAL_FLAGS_WITH_ARG and i < len(argv):
            i += 1  # consume value token for known flag-with-arg
    return i


def _gh_write_subcommand(argv: list[str]) -> tuple[str, str] | None:
    """Return (object, verb) if argv is a gh write subcommand, else None.

    Handles flags between object and verb, e.g.:
      gh issue --repo owner/repo create   → ('issue', 'create')
      gh --repo X issue --flag create     → ('issue', 'create')
    """
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return None
    # Skip gh-level global flags to find the object word (e.g., 'issue', 'pr').
    i = _skip_flags(argv, 1)
    if i >= len(argv):
        return None
    obj = argv[i]
    # Skip flags between object and verb (e.g., `gh issue --repo X create`).
    i = _skip_flags(argv, i + 1)
    if i >= len(argv):
        return None
    verb = argv[i]
    pair = (obj, verb)
    return pair if pair in GH_WRITE_SUBCOMMANDS else None


def _has_repo_flag(argv: list[str]) -> tuple[bool, str]:
    """Return (True, repo_value) if --repo/-R flag is present, else (False, '')."""
    for i, tok in enumerate(argv):
        if tok in ("-R", "--repo") and i + 1 < len(argv):
            return True, argv[i + 1]
        if tok.startswith("--repo="):
            return True, tok.split("=", 1)[1]
        if tok.startswith("-R") and len(tok) > 2:
            return True, tok[2:]
    return False, ""


def _has_heredoc(argv: list[str]) -> bool:
    """Return True if argv contains a << heredoc redirect operator.

    Two tokenization forms handled (both invalid in gh write commands):

    1. Space-separated (whitespace between command and redirect):
         gh issue create <<EOF  →  token '<<EOF'  (starts with '<<')

    2. Attached to preceding word (no space before redirect):
         gh issue create --title foo<<EOF  →  token 'foo<<EOF'
         Shell parses this as stdin-redirect on the command; '<<' does
         not become part of the --title value.

    False-positive guard: body content with '<<' inside quoted strings
    (e.g. --body "comparison: a << b") tokenizes as 'comparison: a << b'
    where '<<' is surrounded by spaces on both sides. We skip such tokens.

    Separate-line guard: VAR=$(cat <<EOF\\n...\\nEOF\\n)\\ngh pr create
    has the heredoc on a different newline, which safe_tokenize separates
    into a different segment with a synthetic ';'. The heredoc token does
    NOT appear in the gh write argv slice.
    """
    for tok in argv:
        if "<<" not in tok:
            continue
        # Case 1: token starts with '<<' (space-separated redirect)
        if tok.startswith("<<"):
            return True
        # Case 2: '<<' embedded in token without surrounding spaces
        # (attached redirect like 'foo<<EOF').
        # Skip occurrences that are surrounded by spaces on both sides
        # (literal comparison operator inside a formerly-quoted string).
        idx = tok.find("<<")
        while idx != -1:
            left = tok[idx - 1] if idx > 0 else ""
            right = tok[idx + 2] if idx + 2 < len(tok) else ""
            if not (left == " " and right == " "):
                return True
            idx = tok.find("<<", idx + 1)
    return False


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _build_checklist(subcommand: tuple[str, str], repo: str) -> str:
    obj, verb = subcommand
    is_pr = obj == "pr"
    parts = [
        f"⚠️  Cross-boundary pre-flight: `gh {obj} {verb} --repo {repo}`",
        "",
        "Confirm ALL contracts before proceeding:",
        "",
        "  ① Per-action authorization gate (CLAUDE.md §External-repo write)",
        "     Explicit approval required for THIS specific action.",
        "     General 'proceed' / 'ok' / 'continue' does NOT count.",
        "",
    ]
    if is_pr:
        parts += [
            "  ② Caller chain verified (block-pr-without-caller-evidence hook)",
            "     PR body must contain: `Caller chain verified: <source>`",
            "     Without this line the hook hard-blocks the command.",
            "",
        ]
    parts += [
        "  ③ Body delivery format",
        "     Use --body-file /tmp/<slug>.md (write body via Write tool first).",
        "     Heredoc (`<<EOF`) is blocked by the praxis hook chain.",
        "",
        "  ④ Language & content rules (CLAUDE.md §External-repo content isolation)",
        "     English only. No internal identifiers (laplace-*, Hub #N,",
        "     internal Slack/Notion links, hubctl). No absolute local paths.",
        "",
        "If all are satisfied, re-run with `# cross-boundary:ack` appended.",
    ]
    return "\n".join(parts)


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
        return 0  # fail-open on malformed input

    if payload.get("tool_name") != "Bash":
        return 0

    command = payload.get("tool_input", {}).get("command", "") or ""
    if not command.strip():
        return 0
    if OPT_OUT_MARKER in command:
        return 0

    tokens = safe_tokenize(command.replace("\\\n", " "))
    if not tokens:
        return 0

    for argv in iter_command_starts(tokens):
        argv = list(argv)
        subcommand = _gh_write_subcommand(argv)
        if subcommand is None:
            continue

        # Check 1: heredoc in same segment → hard block
        if _has_heredoc(argv):
            sys.stderr.write(HEREDOC_BLOCK_MSG)
            return 2

        # Check 2: --repo flag present → surface pre-flight checklist
        has_repo, repo_val = _has_repo_flag(argv)
        if has_repo:
            _emit_ask(_build_checklist(subcommand, repo_val))
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
