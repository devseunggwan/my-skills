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

Opt-out: embed `# cross-boundary:ack` anywhere in the command after manually
confirming all checklist items.
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
"""


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _gh_write_subcommand(argv: list[str]) -> tuple[str, str] | None:
    """Return (object, verb) if argv is a gh write subcommand, else None."""
    argv = strip_prefix(argv)
    if not argv or argv[0] != "gh":
        return None
    # Skip gh global flags to find the first positional subcommand token.
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
            i += 1  # consume value token for flag-with-arg
    if i + 1 >= len(argv):
        return None
    pair = (argv[i], argv[i + 1])
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
    """Return True if argv contains a << heredoc operator token.

    safe_tokenize with whitespace_split=True produces '<<EOF' as a single
    token (whitespace-split, not operator-split). We detect any token that
    starts with '<<' within the same command segment as a gh write command.

    False-positive guard: VAR=$(cat <<EOF\\n...\\nEOF\\n)\\n gh pr create
    patterns have the heredoc on a separate line, which safe_tokenize puts
    in a different segment (newlines become ';' separators). The heredoc
    token therefore does NOT appear in the gh write argv slice.
    """
    return any(tok.startswith("<<") for tok in argv)


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
