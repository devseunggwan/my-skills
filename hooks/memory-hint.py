#!/usr/bin/env python3
"""PreToolUse(Bash) memory hint: surface relevant memory file descriptions.

Scans the user-scoped memory directory for `*.md` files whose YAML
frontmatter declares `hookable: true` plus a `hookKeywords: [...]` list,
tokenizes the inbound Bash command via the shared `safe_tokenize` /
`strip_prefix` / `iter_command_starts` pipeline, and emits up to 3
`[memory:hookable] {filename} — {description}` lines to stderr per match
(plus an `...and N more` summary line when truncated).

Always exits 0. Never blocks. Never asks. The signal is purely
attention-shifting for the LLM's next reasoning step. Co-firing with
`block-gh-state-all` (exit 2) and `side-effect-scan` (`ask`) is intentional
— PreToolUse hooks run in parallel; a memory hint may clarify why a
sibling hook blocked the command.

Memory directory discovery:
  1. `PRAXIS_MEMORY_DIR` env var (when set + exists)
  2. fallback to `~/.claude/projects/{slugified-cwd}/memory/`
     (slugify rule: replace `/` with `-` on the absolute cwd)
  3. missing dir → exit 0 silently

Frontmatter parser is pure regex (no PyYAML dependency). Supported shapes:
  - `hookable: true|True|TRUE|yes|Yes` (other values silently skip the file)
  - `hookKeywords: [a, b, "c d"]` (flat single-line list only;
                                  multi-line / flow-mapping NOT supported)
  - `description: anything` (optional; emitted after em-dash when present)
Any parse error within a memory skips that memory only — never the hook.
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


HIT_LIMIT = 3
TRUTHY_VALUES = {"true", "yes"}

FRONTMATTER_FENCE = re.compile(r"^---\s*$", re.MULTILINE)
HOOKABLE_RE = re.compile(r"^\s*hookable\s*:\s*(.+)$", re.MULTILINE)
KEYWORDS_RE = re.compile(r"^\s*hookKeywords\s*:\s*(.+)$", re.MULTILINE)
DESCRIPTION_RE = re.compile(r"^\s*description\s*:\s*(.+)$", re.MULTILINE)

# YAML inline comment: `#` preceded by whitespace (per YAML 1.2 spec). The
# `hookKeywords` list parser additionally tolerates anything after the first
# `]`, which covers comments without leading whitespace.
INLINE_COMMENT_RE = re.compile(r"\s+#.*$")

# Control bytes (incl. ESC for ANSI escape sequences) shouldn't reach stderr —
# memory filenames flow through to log viewers / terminals.
CONTROL_BYTES_RE = re.compile(r"[\x00-\x1f\x7f]")


def _strip_inline_comment(value: str) -> str:
    return INLINE_COMMENT_RE.sub("", value)


def _sanitize(text: str) -> str:
    return CONTROL_BYTES_RE.sub("?", text)


def parse_frontmatter(raw: str) -> dict | None:
    """Extract the first `---`-fenced block. Return None if absent."""
    matches = list(FRONTMATTER_FENCE.finditer(raw))
    if len(matches) < 2:
        return None
    start = matches[0].end()
    end = matches[1].start()
    block = raw[start:end]

    hookable_match = HOOKABLE_RE.search(block)
    if not hookable_match:
        return None
    hookable_value = (
        _strip_inline_comment(hookable_match.group(1))
        .strip()
        .lower()
        .strip('"\'')
    )
    if hookable_value not in TRUTHY_VALUES:
        return None

    keywords_match = KEYWORDS_RE.search(block)
    if not keywords_match:
        return None
    keywords_raw = keywords_match.group(1).strip()
    if not keywords_raw.startswith("["):
        # Scalar form (`hookKeywords: kubectl`) is rejected per AC-22.
        return None
    # Find the first `]` so a trailing inline comment doesn't break parse.
    # `[a, b] # comment` is the natural YAML shape — anything after the
    # closing bracket is treated as comment/garbage.
    close_idx = keywords_raw.find("]")
    if close_idx == -1:
        return None
    inner = keywords_raw[1:close_idx].strip()
    if not inner:
        return None
    keywords = [
        item.strip().strip('"\'')
        for item in inner.split(",")
    ]
    keywords = [k for k in keywords if k]
    if not keywords:
        return None

    description_match = DESCRIPTION_RE.search(block)
    description = ""
    if description_match:
        description = (
            _strip_inline_comment(description_match.group(1))
            .strip()
            .strip('"\'')
        )

    return {"keywords": keywords, "description": description}


def resolve_memory_dir() -> str | None:
    """Return the resolved memory directory path or None if missing."""
    env_dir = os.environ.get("PRAXIS_MEMORY_DIR", "").strip()
    if env_dir:
        return env_dir if os.path.isdir(env_dir) else None

    home = os.path.expanduser("~")
    cwd = os.getcwd()
    slug = cwd.replace("/", "-")
    fallback = os.path.join(home, ".claude", "projects", slug, "memory")
    return fallback if os.path.isdir(fallback) else None


def index_memories(directory: str) -> list[tuple[str, dict, float]]:
    """Return [(filename, parsed, mtime), ...] for every hookable memory."""
    out: list[tuple[str, dict, float]] = []
    try:
        entries = os.listdir(directory)
    except OSError:
        return out

    for name in entries:
        if not name.endswith(".md"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            parsed = parse_frontmatter(raw)
        except Exception:
            parsed = None
        if not parsed:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        out.append((name, parsed, mtime))
    return out


def collect_command_tokens(command: str) -> set[str]:
    """Flatten command tokens after splitting at shell separators + stripping prefixes."""
    tokens = safe_tokenize(command)
    if not tokens:
        return set()
    flat: set[str] = set()
    for argv in iter_command_starts(tokens):
        for tok in strip_prefix(argv):
            flat.add(tok)
    return flat


def find_hits(
    indexed: list[tuple[str, dict, float]],
    cmd_tokens: set[str],
) -> list[tuple[str, dict, float]]:
    """Return memories whose hookKeywords match any command token (whole-token)."""
    # Whole-token equality (case-sensitive). Quoted multi-word strings shlex
    # parses as a single token (e.g. `echo "use kubectl"` → `use kubectl`),
    # so `kubectl` keyword does NOT match — see AC-10. Substring matching
    # would create false positives across `kubectl-prod` vs `kubectl`.
    hits: list[tuple[str, dict, float]] = []
    for name, parsed, mtime in indexed:
        if any(keyword in cmd_tokens for keyword in parsed["keywords"]):
            hits.append((name, parsed, mtime))
    return hits


def emit_hits(hits: list[tuple[str, dict, float]]) -> None:
    """Print up to HIT_LIMIT hit lines + summary, sorted by mtime desc."""
    hits.sort(key=lambda h: h[2], reverse=True)
    for name, parsed, _ in hits[:HIT_LIMIT]:
        safe_name = _sanitize(name)
        description = _sanitize(parsed["description"])
        if description:
            sys.stderr.write(f"[memory:hookable] {safe_name} — {description}\n")
        else:
            sys.stderr.write(f"[memory:hookable] {safe_name}\n")
    extra = len(hits) - HIT_LIMIT
    if extra > 0:
        sys.stderr.write(f"[memory:hookable] ...and {extra} more\n")


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

    directory = resolve_memory_dir()
    if not directory:
        return 0

    indexed = index_memories(directory)
    if not indexed:
        return 0

    cmd_tokens = collect_command_tokens(command)
    if not cmd_tokens:
        return 0

    hits = find_hits(indexed, cmd_tokens)
    if hits:
        emit_hits(hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
