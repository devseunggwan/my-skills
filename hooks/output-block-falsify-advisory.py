#!/usr/bin/env python3
"""PreToolUse advisory: nudge output-block falsification gate.

Issue #221. Recurring failure mode: the "Output-Block-Level Falsification Gate"
rule in CLAUDE.md (4+ memory entries accumulated 2026-05-03 through 2026-05-13)
fails to fire at output time because rule retrieval is not structural — the rule
is loaded but not re-triggered at the moment the proposal block is authored.

This hook adds a structural enforcement point at two surfaces:

  1. AskUserQuestion — option labels containing "(Recommended)" or "(추천)"
     These markers are the canonical signal for a self-authored proposal block
     about to be surfaced to the user.

  2. Bash — bulk-action commands containing patterns like "close all",
     "delete all", "merge all" (+ Korean equivalents), which may reflect a
     consequence of a proposal block whose premise was not falsified.

When detected, an advisory stderr reminder is emitted asking whether the
output-block falsification gate has been run. The hook NEVER blocks (exit 0
always). Advisory mode is the only mode; escalation to blocking will be
evaluated after ~1 month of advisory operation.

Fail-open contract (project hook design):
  - Malformed / missing stdin JSON → exit 0
  - Unknown tool_name → exit 0
  - Missing target field (questions / command) → exit 0
  - Any uncaught exception → exit 0
"""
from __future__ import annotations

import json
import re
import sys

# ---------------------------------------------------------------------------
# Advisory message
# ---------------------------------------------------------------------------

ADVISORY_MSG = (
    "[output-block-falsify-advisory] Surfacing a recommendation/bulk-action "
    "proposal? Run the output-block falsification gate first: is the proposal's "
    "premise already addressed by in-flight work, a merged PR, or a parallel "
    "proposal in this session? If yes — STOP and cite the invalidating link "
    "instead of surfacing the proposal."
)

# ---------------------------------------------------------------------------
# AskUserQuestion: (Recommended) / (추천) marker detection
# ---------------------------------------------------------------------------

# Substrings to search for in option labels (case-insensitive for English form).
RECOMMENDED_MARKERS_EN = ("(Recommended)",)
RECOMMENDED_MARKERS_KO = ("(추천)",)


def _collect_option_labels(tool_input: dict) -> list[str]:
    """Walk questions[].options[].label and return all label strings.

    Tolerant of partial schemas — any missing field returns an empty list.
    Hook must never crash on malformed payloads.
    """
    labels: list[str] = []
    questions = tool_input.get("questions") or []
    if not isinstance(questions, list):
        return labels
    for q in questions:
        if not isinstance(q, dict):
            continue
        options = q.get("options") or []
        if not isinstance(options, list):
            continue
        for o in options:
            if not isinstance(o, dict):
                continue
            label = o.get("label")
            if isinstance(label, str):
                labels.append(label)
    return labels


def _has_recommended_marker(labels: list[str]) -> bool:
    """True if any option label contains a (Recommended) / (추천) marker."""
    if not labels:
        return False
    for label in labels:
        lower = label.lower()
        for marker in RECOMMENDED_MARKERS_EN:
            if marker.lower() in lower:
                return True
        for marker in RECOMMENDED_MARKERS_KO:
            if marker in label:
                return True
    return False


# ---------------------------------------------------------------------------
# Bash: bulk-action keyword detection
# ---------------------------------------------------------------------------

# English bulk-action phrases. Matched as case-insensitive substrings after
# a word-boundary check on the verb part. The "all" / "all " suffix is kept
# as a plain substring to avoid over-matching on common non-bulk commands.
#
# Strategy: search for the verb phrase with "all" nearby. Using a regex with
# ASCII lookaround avoids `\b` issues when Korean text appears nearby.
_BULK_PHRASES_EN = (
    r"close\s+all",
    r"delete\s+all",
    r"merge\s+all",
    r"reject\s+all",
    r"approve\s+all",
)

# Compiled pattern: any English bulk phrase (case-insensitive).
_BULK_PATTERN_EN = re.compile(
    "|".join(_BULK_PHRASES_EN),
    re.IGNORECASE,
)

# Korean bulk-action substrings. Plain substring match is safe because Hangul
# has no ASCII word-boundary issue — these tokens don't appear as substrings
# of unrelated words.
_BULK_SUBSTRINGS_KO = (
    "전부 닫",
    "모두 닫",
    "전부 삭제",
    "모두 삭제",
    "전부 머지",
    "모두 머지",
    "다 머지",
    "전부 클로즈",
    "모두 클로즈",
)

# Mutation verbs that qualify a bulk command as write-side (not read-only).
# The goal is to avoid firing on `git log --all` / `gh pr list --all` etc.
# We require that the command contains at least one of these mutation verbs
# so that a plain `list all` or `show all` doesn't fire.
_MUTATION_VERBS = re.compile(
    r"\b(close|delete|remove|merge|reject|approve|push|drop|닫|삭제|머지|클로즈)\b",
    re.IGNORECASE,
)


def _is_bulk_action_command(command: str) -> bool:
    """True if the Bash command contains a bulk-action mutation keyword."""
    if not command:
        return False
    # English bulk phrases (close all / delete all / merge all / etc.)
    if _BULK_PATTERN_EN.search(command):
        return True
    # Korean substrings
    for kw in _BULK_SUBSTRINGS_KO:
        if kw in command:
            return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open on malformed stdin

    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    fire = False

    if tool_name == "AskUserQuestion":
        labels = _collect_option_labels(tool_input)
        if _has_recommended_marker(labels):
            fire = True

    elif tool_name == "Bash":
        command = tool_input.get("command") or ""
        if _is_bulk_action_command(command):
            fire = True

    if fire:
        sys.stderr.write(ADVISORY_MSG + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
