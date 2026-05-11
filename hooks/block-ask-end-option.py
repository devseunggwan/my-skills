#!/usr/bin/env python3
"""PreToolUse(AskUserQuestion) guard: warn on mechanical end-option surfacing.

When AskUserQuestion is invoked with `options` whose labels match end-option
markers (e.g. "여기서 종료", "session end", "stop here"), check the most
recent user message in the transcript for an explicit stop signal. If no
signal is present, emit a stderr advisory pointing to the rule.

Background:
  Skill guides authoring "Step N: chaining" sections frequently include an
  "end here" boilerplate option. Agents mechanically transcribe this into
  AskUserQuestion call sites even when the conversation has a clearly
  chained intent or the user has expressed no desire to stop. This pattern
  has been observed 6+ times in a single session, fragmenting decisions
  and ignoring user intent.

  Text rules in CLAUDE.md or skill bodies alone cannot enforce this — the
  `loaded != retrieved` limit. This hook enforces the rule at the tool
  boundary, where the check runs mechanically regardless of retrieval state.

Default mode: advisory (exit 0 + stderr).
Strict mode: PRAXIS_ASK_END_STRICT=1 → block (exit 2 + stderr).

Allow conditions (no advisory emitted):
  1. tool_name != "AskUserQuestion"
  2. No options match any end marker
  3. Most recent user message contains an explicit stop signal
  4. transcript_path is missing or unreadable (graceful degrade — advisory
     is suppressed to avoid noise when transcript inspection is impossible)
"""
from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# End-option markers in option labels. Case-insensitive.
# Korean entries are unicode literals; English entries cover common phrasings.
END_OPTION_MARKERS_KO = (
    "여기서 종료",
    "세션 종료",
    "여기서 끝",
    "여기까지",
)
END_OPTION_MARKERS_EN = (
    "end here",
    "session end",
    "stop here",
    "end the session",
    "wrap up here",
)

# Stop signals in the most recent user message. Case-insensitive.
# Each entry must be a clear directive — substring matches in unrelated
# contexts (e.g., "end of the migration") are tolerated as false positives
# because the hook is advisory by default.
STOP_SIGNALS_KO = (
    "종료",
    "여기까지",
    "그만",
    "마무리",
    "스톱",
    "중단",
)
STOP_SIGNALS_EN = (
    "stop",
    "end",
    "quit",
    "done",
    "cancel",
    "finish",
    "wrap up",
    "that's all",
    "no more",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_markers() -> tuple[str, ...]:
    return END_OPTION_MARKERS_KO + END_OPTION_MARKERS_EN


def _all_stop_signals() -> tuple[str, ...]:
    return STOP_SIGNALS_KO + STOP_SIGNALS_EN


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


def _has_end_marker(labels: list[str]) -> bool:
    if not labels:
        return False
    markers = _all_markers()
    for label in labels:
        lower = label.lower()
        for marker in markers:
            if marker.lower() in lower:
                return True
    return False


def _read_last_user_message(transcript_path: str) -> str:
    """Return the text of the most recent user message in the transcript.

    Returns empty string if the file is missing, unreadable, or contains
    no user messages. The hook is advisory by default so silent failure
    here just means the stop-signal check is skipped — no false block.

    Transcript format: JSONL where each line is a JSON object with at
    least `type` ('user' / 'assistant' / 'system') and either `message`
    (an Anthropic API message dict with `role` + `content`) or a flatter
    `content` field. Both shapes are handled.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""

    # Walk in reverse to find the most recent user-role entry.
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

        # Extract text. Possible shapes:
        #   {"type": "user", "message": {"role": "user", "content": "text"}}
        #   {"type": "user", "message": {"role": "user", "content": [{"type":"text","text":"..."}]}}
        #   {"role": "user", "content": "text"}
        content = None
        if isinstance(message, dict):
            content = message.get("content")
        if content is None:
            content = entry.get("content")

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return ""

    return ""


def _has_stop_signal(user_message: str) -> bool:
    if not user_message:
        return False
    lower = user_message.lower()
    for signal in _all_stop_signals():
        if signal.lower() in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ADVISORY_MSG = """\
[advisory] AskUserQuestion includes an end-option ("end here" / "여기서 종료" type)
but the most recent user message has no stop signal.

Mechanical surfacing of "end here" options propagates from skill-guide
boilerplate even when conversation context has a chained intent. Verify
that the user actually wants a stop point before this surface — or remove
the end option.

Set PRAXIS_ASK_END_STRICT=1 to escalate this advisory to a hard block.
"""

BLOCK_MSG = """\
❌ BLOCKED: AskUserQuestion includes an end-option without user stop signal.

Markers detected in options[].label: "end here" / "session end" / "여기서 종료" type.
Most recent user message contains no stop signal (stop, end, quit, done,
cancel, finish, 종료, 여기까지, 그만, 마무리, etc.).

Why:
  Skill-guide "end here" boilerplate is being mechanically transcribed
  into AskUserQuestion call sites where the conversation has a chained
  intent. Remove the end-option, or wait for the user to express a
  stop signal explicitly.

Unset PRAXIS_ASK_END_STRICT to demote this to an advisory.
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
    if not _has_end_marker(labels):
        return 0

    transcript_path = payload.get("transcript_path") or ""
    user_message = _read_last_user_message(transcript_path)
    if _has_stop_signal(user_message):
        return 0

    strict = os.environ.get("PRAXIS_ASK_END_STRICT", "") not in ("", "0", "false", "False")
    if strict:
        sys.stderr.write(BLOCK_MSG)
        return 2

    sys.stderr.write(ADVISORY_MSG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
