#!/usr/bin/env python3
"""PreToolUse(AskUserQuestion) guard: warn on manufactured action-menu surfacing.

When AskUserQuestion is invoked with `options` whose labels match
manufactured-menu markers (e.g. "진행할까요", "계속할까요", "proceed",
"continue", "go ahead"), check the most recent user message in the
transcript for a command-intent signal. If a command-intent signal is
present, the user has already given direction — re-asking via menu is
redundant manufactured friction.

Background:
  2026-05-13 retrospect Strike 1: agent completed an action then automatically
  emitted an AskUserQuestion 4-option menu ("다음 액션 진행할까요?") even when
  the user's immediately prior message was a direct command ("진행", "go ahead",
  "실행"). This pattern fragments decisions, ignores established user intent, and
  adds roundtrip latency on simple continuations.

  The existing `block-ask-end-option` hook catches *termination* menu misuse.
  This hook is its sibling: it catches *continuation* menu misuse — surfacing
  "shall we proceed?" confirmation when the user has already said "yes, proceed".

Default mode: advisory (exit 0 + stderr warning).
Strict mode (PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT=1): block (exit 2).

Allow conditions (no block/advisory emitted):
  1. tool_name != "AskUserQuestion"
  2. No options match any manufactured-menu marker
  3. Most recent user message does NOT contain a command-intent signal
  4. transcript_path is missing or unreadable (graceful degrade — suppress to
     avoid noise when transcript inspection is impossible)
"""
from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Manufactured-menu markers in option labels. Case-insensitive.
# These are "shall we proceed?" style option labels that are typically
# redundant when the user has already issued a command.
MANUFACTURED_MARKERS_KO = (
    "진행할까요",
    "계속할까요",
    "다음 액션",
    "머지할까요",
    "push할까요",
)
MANUFACTURED_MARKERS_EN = (
    "proceed",
    "continue",
    "go ahead",
)

# Command-intent signals in the most recent user message. Case-insensitive.
#
# Korean entries are substring-matched (CJK has low collision risk for these
# specific action tokens). English entries are phrase- or token-matched to
# avoid false positives from substrings (e.g. "continuing" in an explanation
# vs "continue" as a command).
COMMAND_SIGNALS_KO = (
    "진행",
    "실행",
    "머지",
    "커밋",
    "push",
    "푸시",
)
COMMAND_SIGNALS_EN_TOKENS = (
    "go",
    "go ahead",
    "proceed",
    "continue",
    "merge",
    "commit",
    "push",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_markers() -> tuple[str, ...]:
    return MANUFACTURED_MARKERS_KO + MANUFACTURED_MARKERS_EN


def _collect_option_labels(tool_input: dict) -> list[str]:
    """Walk questions[].options[].label and return all label strings.

    Tolerant of partial schemas — any missing field results in an empty
    return rather than an exception. Hook must never crash on malformed
    payloads.
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


def _has_manufactured_marker(labels: list[str]) -> bool:
    if not labels:
        return False
    markers = _all_markers()
    for label in labels:
        lower = label.lower()
        for marker in markers:
            if marker.lower() in lower:
                return True
    return False


def _read_last_user_message(transcript_path: str) -> str | None:
    """Return the text of the most recent user-authored message in the transcript.

    Returns None when the transcript is missing or unreadable — the caller
    must fail open per the project hook design contract (`Fail-open on
    infrastructure errors`). Returns empty string when the transcript was
    read successfully but no user message contained extractable human
    text — that is a real "no command-signal" answer and may be acted on.

    Transcript format: JSONL where each line is a JSON object with at
    least `type` ('user' / 'assistant' / 'system') and either `message`
    (an Anthropic API message dict with `role` + `content`) or a flatter
    `content` field. Both shapes are handled.

    tool_result handling: an Anthropic user role message may carry only
    `tool_result` content blocks when the assistant invoked tools in the
    same turn before invoking AskUserQuestion. Such entries are NOT human
    authored — they are the runtime's bridge for tool outputs. We must
    skip them and keep walking backward until we find a user entry that
    contains actual `type: text` content.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None

    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        role = entry.get("type") or entry.get("role")
        message = entry.get("message")
        if isinstance(message, dict) and not role:
            role = message.get("role")

        if role != "user":
            continue

        content = None
        if isinstance(message, dict):
            content = message.get("content")
        if content is None:
            content = entry.get("content")

        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type and item_type != "text":
                        continue
                    t = item.get("text")
                    if isinstance(t, str):
                        parts.append(t)
                elif isinstance(item, str):
                    parts.append(item)
            text = "\n".join(parts)

        if text.strip():
            return text
        continue

    return ""


def _has_command_signal(user_message: str) -> bool:
    """True if the user message contains a command-intent directive.

    Korean tokens: substring match (CJK has low collision risk for these
    specific action verbs). English tokens: whole-word match (prevents
    "continuing" → "continue", "progress" → "go", etc.).
    """
    if not user_message:
        return False

    # Korean: substring match.
    for ko in COMMAND_SIGNALS_KO:
        if ko in user_message:
            return True

    # English: whole-word match (case-insensitive).
    lower = user_message.lower()
    import re
    for token in COMMAND_SIGNALS_EN_TOKENS:
        pattern = r"\b" + re.escape(token.lower()) + r"\b"
        if re.search(pattern, lower):
            return True

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ADVISORY_MSG = """\
[advisory] AskUserQuestion includes a manufactured action-menu option ("진행할까요",
"proceed", "go ahead", etc.) but the most recent user message already contains
a command-intent signal ("진행", "실행", "go ahead", "proceed", etc.).

Re-asking "shall we proceed?" when the user has already said "proceed" is
manufactured friction — it fragments decisions and adds an unnecessary
confirmation roundtrip.

Remove the manufactured-menu option or replace with a substantive decision
point (multiple real alternatives with trade-offs, or a destructive/irreversible
action requiring explicit confirmation).

Strict mode disabled. Set PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT=1 to block.
"""

BLOCK_MSG = """\
BLOCKED: AskUserQuestion includes a manufactured action-menu option without
a substantive decision point.

Manufactured-menu markers detected in options[].label:
  Korean: "진행할까요", "계속할까요", "다음 액션", "머지할까요", "push할까요"
  English: "proceed", "continue", "go ahead"

Most recent user message already contains a command-intent signal
("진행", "실행", "go", "proceed", "continue", "merge", "commit", "push",
"머지", "커밋", "푸시").

Why:
  Re-asking confirmation when the user has already given a directive is
  manufactured friction. The user's prior "proceed" / "진행" / "go ahead"
  covers the continuation. Surface only genuine decision points: multiple
  real alternatives with trade-offs, or destructive / irreversible actions
  requiring explicit confirmation.

To opt out: unset PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT (default is advisory).
"""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "AskUserQuestion":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    labels = _collect_option_labels(tool_input)
    if not _has_manufactured_marker(labels):
        return 0

    transcript_path = payload.get("transcript_path") or ""
    user_message = _read_last_user_message(transcript_path)
    if user_message is None:
        # Fail open per project hook design contract — transcript missing
        # or unreadable, cannot verify command-signal presence.
        return 0
    if not _has_command_signal(user_message):
        # No command-intent in prior message — manufactured menu may be
        # legitimate (first interaction, genuine multiple-choice). Pass.
        return 0

    # Mode resolution.
    strict_env = os.environ.get("PRAXIS_BLOCK_MANUFACTURED_MENU_STRICT", "")
    strict_set = strict_env not in ("", "0", "false", "False")

    if strict_set:
        sys.stderr.write(BLOCK_MSG)
        return 2

    sys.stderr.write(ADVISORY_MSG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
