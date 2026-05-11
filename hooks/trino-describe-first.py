#!/usr/bin/env python3
r"""Trino MCP DESCRIBE-first gate (PreToolUse + PostToolUse).

Issue #182. Recurring failure mode: Trino MCP queries reference column names
guessed from naming convention rather than verified via `DESCRIBE` first,
producing repeated `COLUMN_NOT_FOUND` / `TYPE_MISMATCH` errors. Memory-based
feedback (`loaded_not_retrieved`, `external_library_attribute_grep_first`)
was insufficient — the rules are loaded into context, but the habitual
inductive guess takes priority.

This hook acts as a structural attention-shift at MCP query construction
time:

  PreToolUse  → parse the outbound query, extract referenced tables, and
                warn (or block) if any of them lack a recorded `DESCRIBE`.
  PostToolUse → if the just-executed query was a `DESCRIBE <table>` or
                `SHOW COLUMNS FROM <table>`, record the table in the
                session-scoped history file so subsequent queries pass.

Invocation:

    python3 trino-describe-first.py pre   # PreToolUse hook
    python3 trino-describe-first.py post  # PostToolUse hook

Two shell wrappers (`trino-describe-first-pre.sh`, `-post.sh`) delegate to
this module so `hooks.json` can register each event independently.

Session state — design rationale
================================

Claude Code PreToolUse / PostToolUse hooks are invoked as independent
processes; there is no shared in-memory state across invocations. State
must be persisted to a file.

Resolution order:

  1. `PRAXIS_DESCRIBE_HISTORY_FILE` env var — explicit override, used by
     tests for isolation. When set, the path is used verbatim. Authors
     of long-running sessions can also set this to pin a known location.
  2. `session_id` from the hook payload (primary key — stable across
     PreToolUse / PostToolUse invocations within a single Claude Code
     session) → `${TMPDIR:-/tmp}/praxis-describe-history-<session_id>.json`.
     This is the canonical praxis hook session key, the same field
     consumed by `completion-verify.sh`, `retrospect-mix-check.sh`, and
     `strike-counter.sh`.
  3. `${TMPDIR:-/tmp}/praxis-describe-history-${PPID}.json` — last-resort
     back-compat fallback when the payload does not carry a `session_id`
     (e.g., direct CLI / test invocation without the field). PPID here
     is the hook process's parent.

The `$CLAUDE_PROJECT_DIR/.praxis/describe-history.json` branch was
intentionally removed (codex R2 P2 on PR #189): project-rooted state
persists across Claude Code sessions in the same workspace and would
silently satisfy a later session's gate with a DESCRIBE recorded by an
earlier session — breaking the "in this session" contract. This is the
same architectural fix applied to `session-intent.py` in PR #190.

Read failures (missing file, malformed JSON, OS errors) → empty history,
fail-open. Write failures → silently skip recording, never crash the hook.

MCP tool name detection
=======================

The Trino MCP tool is named `mcp__laplace-trino__trino_query` (per the
project's deferred-tool registry). Tool name matching is parameterized:

  - `PRAXIS_TRINO_TOOL_PATTERN` env var → custom regex (default below).
  - Default regex `^mcp__.*trino.*__(trino_)?query$` — matches Trino-like
    MCP query tools while excluding `_lock` / `_metadata` siblings.

Alias / CTE / subquery handling
================================

v1 is intentionally regex-light, not a full SQL parser:

  - Extract bare `FROM <table>` and `JOIN <table>` identifiers (with
    optional `<catalog>.<schema>.<table>` qualification). Trailing alias
    after the identifier is dropped (`FROM tbl t` → `tbl`).
  - Strip `WITH name AS (...)` CTE bodies before extracting FROM/JOIN, and
    treat each CTE name as a synthetic "described" table for the outer
    query. `WITH foo AS (SELECT * FROM real) SELECT * FROM foo` →
    `real` is checked, `foo` is treated as a CTE reference and skipped.
  - DESCRIBE / SHOW COLUMNS detection on the post-hook side uses a similar
    regex: `^\s*DESCRIBE\s+<table>` and `^\s*SHOW\s+COLUMNS\s+(IN|FROM)\s+<table>`.
  - If parsing fails or extracts zero candidate tables → fail-open (no
    warn). False-positive cost is higher than false-negative cost.

Multi-engine
============

v1 ships Trino as the only seed engine. Engine is parameterized via the
matched tool name + an `engine` field in the history file so future
extensions (BigQuery, Snowflake, ClickHouse) can co-exist without schema
churn. Engine-specific table-name parsing is not currently differentiated
— most warehouse SQL dialects use the same `FROM <name>` shape.

Default mode
============

Default mode = **warn** (stderr message, exit 0). Opt-in **block** mode
via `PRAXIS_DESCRIBE_FIRST_MODE=block` emits `permissionDecision: "deny"`
which Claude Code surfaces as a hard rejection.

Acceptance criteria mapping (issue #182)
========================================

  AC-1 alias/CTE/subquery resolution        → CTE strip + alias drop
  AC-2 configurable per-engine              → engine field + tool pattern
  AC-3 warn / block opt-in                  → PRAXIS_DESCRIBE_FIRST_MODE
  AC-4 cite memory rule paths               → WARNING_PREFIX includes them
  AC-5 documented as opt-in skill manifest  → AGENTS.md + hooks.json entry
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TOOL_PATTERN = r"^mcp__.*trino.*__(trino_)?query$"

# Trino MCP query tool arg name. Defaults to `query`; override via
# PRAXIS_TRINO_QUERY_ARG if a future MCP exposes a different field name.
DEFAULT_QUERY_ARG = "query"

WARN_PREFIX = (
    "[trino:describe-first] Query references table(s) without a recorded "
    "DESCRIBE / SHOW COLUMNS in this session: {tables}. "
    "Run `DESCRIBE {first}` first to verify the schema before referencing "
    "columns. "
    "Memory rules: loaded_not_retrieved, external_library_attribute_grep_first."
)

BLOCK_REASON_PREFIX = (
    "trino:describe-first — Query references table(s) without a recorded "
    "DESCRIBE in this session: {tables}. "
    "Run `DESCRIBE {first}` first. "
    "Memory rules: loaded_not_retrieved, external_library_attribute_grep_first. "
    "(Block mode active via PRAXIS_DESCRIBE_FIRST_MODE=block.)"
)

# ---------------------------------------------------------------------------
# Regex primitives
# ---------------------------------------------------------------------------

# A SQL identifier path: bare name, schema.table, or catalog.schema.table.
# Allows backticks/double-quotes, but the captured group strips them later.
_IDENT = r'(?:"[^"]+"|`[^`]+`|[A-Za-z_][\w$]*)'
TABLE_REF = rf"({_IDENT}(?:\.{_IDENT}){{0,2}})"

# FROM / JOIN extraction. Anchored on word boundary to avoid `CROSS JOIN` /
# `INNER JOIN` substring false positives where the keyword is split.
FROM_JOIN_RE = re.compile(
    rf"\b(?:FROM|JOIN)\s+{TABLE_REF}",
    re.IGNORECASE,
)

# Table-valued functions that legitimately appear in FROM/JOIN but have no
# table to DESCRIBE. Comparison is case-insensitive and applied to the
# unqualified, unquoted name.
TVF_NAMES = frozenset({"UNNEST", "JSON_TABLE", "TABLE", "LATERAL"})

# CTE body matcher: WITH name AS ( ... ) and chained `, name2 AS ( ... )`.
# Optional column list `(c1, c2, ...)` between the name and `AS` per
# Trino's `WITH foo(x, y) AS (...)` shape. Paren-balance walk follows to
# find the real matching `)` of the CTE body.
CTE_HEAD_RE = re.compile(
    rf"(?:\bWITH\b|,)\s+(?:RECURSIVE\s+)?({_IDENT})\s*(?:\([^)]*\))?\s+AS\s*\(",
    re.IGNORECASE,
)

# Post-hook: detect DESCRIBE / SHOW COLUMNS verification commands.
DESCRIBE_RE = re.compile(
    rf"^\s*DESCRIBE\s+{TABLE_REF}\b",
    re.IGNORECASE,
)
SHOW_COLUMNS_RE = re.compile(
    rf"^\s*SHOW\s+COLUMNS\s+(?:IN|FROM)\s+{TABLE_REF}\b",
    re.IGNORECASE,
)

# Comment strippers — single-line `--` and multi-line `/* */`.
SQL_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------


def _extract_session_id(payload: dict) -> str | None:
    """Return the trimmed `session_id` from the hook payload, or None.

    This is the canonical praxis hook session key — same field consumed by
    `completion-verify.sh`, `retrospect-mix-check.sh`, and
    `strike-counter.sh` via `jq -r '.session_id // ...'`.
    """
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return None


def resolve_history_path(session_id: str | None = None) -> str:
    """Resolve the session-scoped describe-history JSON path.

    See module docstring "Session state" for the resolution order.
    """
    override = os.environ.get("PRAXIS_DESCRIBE_HISTORY_FILE", "").strip()
    if override:
        return override

    tmp = os.environ.get("TMPDIR", "/tmp").rstrip("/") or "/tmp"
    if session_id:
        return os.path.join(tmp, f"praxis-describe-history-{session_id}.json")
    ppid = os.getppid()
    return os.path.join(tmp, f"praxis-describe-history-{ppid}.json")


def load_history(path: str) -> dict:
    """Return the parsed history dict, or an empty dict on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        return {}
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


def save_history(path: str, history: dict) -> bool:
    """Atomically write the history dict. Return True on success."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(history, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except OSError:
        return False


def record_described(path: str, engine: str, table: str) -> None:
    """Record `table` as DESCRIBE'd for `engine` in the history file."""
    history = load_history(path)
    described = history.setdefault("described", {})
    engine_set = described.setdefault(engine, [])
    table_norm = normalize_table(table)
    if table_norm and table_norm not in engine_set:
        engine_set.append(table_norm)
    history["last_updated"] = int(time.time())
    save_history(path, history)


def get_described(path: str, engine: str) -> set[str]:
    """Return the set of normalized table names DESCRIBE'd for `engine`."""
    history = load_history(path)
    described = history.get("described", {})
    if not isinstance(described, dict):
        return set()
    tables = described.get(engine, [])
    if not isinstance(tables, list):
        return set()
    return {normalize_table(t) for t in tables if isinstance(t, str)}


# ---------------------------------------------------------------------------
# SQL parsing
# ---------------------------------------------------------------------------


def normalize_table(name: str) -> str:
    """Strip surrounding quotes/backticks and lowercase. Empty on bad input."""
    if not name:
        return ""
    parts = []
    for part in name.split("."):
        part = part.strip()
        if part.startswith('"') and part.endswith('"'):
            part = part[1:-1]
        elif part.startswith("`") and part.endswith("`"):
            part = part[1:-1]
        parts.append(part.lower())
    return ".".join(parts)


def strip_sql_comments(sql: str) -> str:
    """Drop `-- line comments` and `/* block comments */`."""
    sql = SQL_BLOCK_COMMENT_RE.sub(" ", sql)
    sql = SQL_LINE_COMMENT_RE.sub("", sql)
    return sql


def extract_ctes(sql: str) -> tuple[set[str], str]:
    """Return (cte_names, sql_with_cte_headers_neutralized).

    Walks `WITH name AS (...)` and chained `, next AS (...)` segments,
    using paren-balance to find each matching `)`. Returns:

      - the set of CTE names (so the caller can skip them when extracting
        FROM/JOIN targets — they are local aliases, not real tables),
      - a sanitized SQL string where each `WITH name AS` /
        `, name AS` header keyword has been replaced with whitespace so
        the outer-query regex does not interpret `WITH` as part of an
        identifier path. CTE bodies themselves are KEPT inline so their
        FROM/JOIN references are also scanned — tables referenced inside
        a CTE body still need a DESCRIBE.
    """
    cte_names: set[str] = set()
    out_parts: list[str] = []
    cursor = 0

    while True:
        m = CTE_HEAD_RE.search(sql, cursor)
        if not m:
            out_parts.append(sql[cursor:])
            break
        cte_names.add(normalize_table(m.group(1)))

        # Append everything up to the CTE-head match start verbatim.
        out_parts.append(sql[cursor:m.start()])
        # Replace the CTE header (`WITH foo AS (` or `, foo AS (`) with
        # whitespace of equal length so positions stay roughly stable,
        # but neutralize the keyword so a downstream FROM/JOIN scan does
        # not pick up `foo` as a table reference here.
        header_len = m.end() - m.start()
        out_parts.append(" " * header_len)
        # Find the matching `)` so we can also neutralize it (it does
        # not carry semantic load once the header is gone).
        depth = 1
        i = m.end()
        while i < len(sql) and depth > 0:
            ch = sql[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth != 0:
            # Unbalanced — keep the remainder as-is.
            out_parts.append(sql[m.end():])
            cursor = len(sql)
            break
        # Append the body verbatim (so its FROM/JOIN refs get scanned),
        # then a space in place of the closing `)`.
        out_parts.append(sql[m.end():i - 1])
        out_parts.append(" ")
        cursor = i  # past the matching `)`

    return cte_names, "".join(out_parts)


def extract_referenced_tables(sql: str) -> tuple[set[str], set[str]]:
    """Return (real_tables, cte_aliases) referenced in `sql`.

    Real tables are FROM/JOIN identifiers that are NOT CTE aliases.
    CTE aliases are returned for diagnostic purposes (currently unused).
    """
    cleaned = strip_sql_comments(sql)
    cte_names, outer_sql = extract_ctes(cleaned)

    found: set[str] = set()
    for m in FROM_JOIN_RE.finditer(outer_sql):
        raw = m.group(1)
        norm = normalize_table(raw)
        if not norm:
            continue
        if norm in cte_names:
            continue
        # Skip table-valued functions (UNNEST, JSON_TABLE, ...). The TVF
        # name has no schema qualifier and matches the whitelist
        # case-insensitively. Quoted forms (`"unnest"`) are also covered
        # because normalize_table strips quotes.
        unqualified = norm.rsplit(".", 1)[-1]
        if unqualified.upper() in TVF_NAMES:
            continue
        found.add(norm)

    return found, cte_names


def is_describe_or_show(sql: str) -> tuple[bool, str]:
    """Return (True, table) if sql is a DESCRIBE/SHOW COLUMNS, else (False, '')."""
    cleaned = strip_sql_comments(sql).strip()
    # Drop trailing semicolons.
    cleaned = cleaned.rstrip(";").strip()
    m = DESCRIBE_RE.match(cleaned)
    if m:
        return True, normalize_table(m.group(1))
    m = SHOW_COLUMNS_RE.match(cleaned)
    if m:
        return True, normalize_table(m.group(1))
    return False, ""


# ---------------------------------------------------------------------------
# Engine / tool detection
# ---------------------------------------------------------------------------


def get_tool_pattern() -> re.Pattern:
    pattern = os.environ.get("PRAXIS_TRINO_TOOL_PATTERN", "").strip()
    if not pattern:
        pattern = DEFAULT_TOOL_PATTERN
    try:
        return re.compile(pattern)
    except re.error:
        return re.compile(DEFAULT_TOOL_PATTERN)


def get_query_arg() -> str:
    arg = os.environ.get("PRAXIS_TRINO_QUERY_ARG", "").strip()
    return arg or DEFAULT_QUERY_ARG


def tool_matches(tool_name: str) -> bool:
    if not tool_name:
        return False
    return bool(get_tool_pattern().match(tool_name))


def engine_for_tool(_tool_name: str) -> str:
    """Return the engine label for the history file. v1 → always 'trino'."""
    # Future: parse vendor name out of mcp__<vendor>__... and map to engine.
    return "trino"


def _tool_response_indicates_error(tool_response: object) -> bool:
    """Return True iff `tool_response` clearly signals a failed call.

    PostToolUse payloads for MCP tools typically include `tool_response`
    shaped like `{"isError": true, "content": [...]}` on failure. Older
    payloads / non-MCP sources may omit the field entirely.

    Conservative rule:
      - `tool_response is None` (field missing entirely) → not an error
        (fail-open: preserve back-compat with payloads that lack the
        response). The caller distinguishes "missing" vs. "present-and-OK"
        before invoking this helper.
      - dict with `isError: True` → error.
      - any other shape → not an error.
    """
    if isinstance(tool_response, dict):
        if tool_response.get("isError") is True:
            return True
    return False


# ---------------------------------------------------------------------------
# Hook entry points
# ---------------------------------------------------------------------------


def emit_deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def run_pre() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open on malformed input

    tool_name = payload.get("tool_name", "") or ""
    if not tool_matches(tool_name):
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    query = tool_input.get(get_query_arg(), "") or ""
    if not isinstance(query, str) or not query.strip():
        return 0

    try:
        referenced, _ = extract_referenced_tables(query)
    except Exception:
        return 0  # fail-open on parse error

    if not referenced:
        return 0

    # A DESCRIBE/SHOW COLUMNS query itself is not subject to the gate.
    is_describe, _ = is_describe_or_show(query)
    if is_describe:
        return 0

    engine = engine_for_tool(tool_name)
    history_path = resolve_history_path(_extract_session_id(payload))
    described = get_described(history_path, engine)

    missing = sorted(referenced - described)
    if not missing:
        return 0

    mode = os.environ.get("PRAXIS_DESCRIBE_FIRST_MODE", "warn").strip().lower()
    tables_csv = ", ".join(missing)
    first = missing[0]

    if mode == "block":
        emit_deny(BLOCK_REASON_PREFIX.format(tables=tables_csv, first=first))
        return 0

    sys.stderr.write(
        WARN_PREFIX.format(tables=tables_csv, first=first) + "\n"
    )
    return 0


def run_post() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "") or ""
    if not tool_matches(tool_name):
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    query = tool_input.get(get_query_arg(), "") or ""
    if not isinstance(query, str) or not query.strip():
        return 0

    is_describe, table = is_describe_or_show(query)
    if not is_describe or not table:
        return 0

    # Skip recording when the DESCRIBE actually failed. If the payload
    # carries no `tool_response` at all (older event shape, non-MCP
    # source), fail-open and still record — back-compat with payloads
    # that lack the response field.
    if "tool_response" in payload:
        if _tool_response_indicates_error(payload.get("tool_response")):
            return 0

    engine = engine_for_tool(tool_name)
    history_path = resolve_history_path(_extract_session_id(payload))
    record_described(history_path, engine, table)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    mode = argv[1]
    if mode == "pre":
        return run_pre()
    if mode == "post":
        return run_post()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
