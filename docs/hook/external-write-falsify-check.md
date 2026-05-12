# PreToolUse External-Write Falsify Check (opt-in)

`hooks/external-write-falsify-check.py` is an **opt-in** PreToolUse advisory
that warns before posting hypothesis-stage text to external surfaces (PR
comments, issue bodies, Slack messages, Notion pages). It enforces the
global CLAUDE.md rule `External-Surface Write Requires Falsification`
(retraction-cost / downstream-reader-training framing).

### Why this exists — and why opt-in

The four production praxis hooks (`block-gh-state-all`, `side-effect-scan`,
`memory-hint`, `codex-review-route`) each followed the canonical adoption
path: feedback-memo → ≥5 recurrences → structural hook. The
`External-Surface Write Requires Falsification` rule does not yet have
that recurrence trail (zero memory entries, zero issues at adoption time
— see issue #173). Shipping default-on would skip the established
evidence bar; shipping with the code unavailable would discard already-
written infrastructure (245 LOC + 151 LOC tests, ported `_hook_utils`
patterns).

Compromise: the code lands in `main`, **but `hooks/hooks.json` does not
register it**. Users who want the advisory enable it explicitly. This
preserves the option without changing default behavior, and gives
evidence collection a defined opt-in cohort instead of forcing the
question.

### What is warned

| Tool call shape | Warned when body contains hypothesis marker |
|----------------|----------------------------------------------|
| `gh issue comment --body <text>` | yes |
| `gh pr comment -b <text>` | yes |
| `gh pr review --comment --body <text>` (or `--approve` / `--request-changes`) | yes |
| `gh issue create --body-file <path>` | yes (file contents read) |
| `gh pr edit -F <path>` | yes |
| `mcp__*slack*__*send*` / `*post*message*` | yes (body field) |
| `mcp__*notion*__*create_page*` / `*update_page*` | yes (text fields concatenated) |
| `gh issue list` / `gh search issues` / Read tool | passthrough silent |

Hypothesis markers (whole-segment substring match): English 16 —
`might`, `could be`, `could fail`, `could break`, `potentially`,
`potential `, `appears to`, `seems to`, `likely `, `suspected`,
`hypothesis`, `is failing`, `is broken`, `may have`, `may be `; Korean 6 —
`가설`, `추정`, `추측`, `가능성`, `의심됨`, `의심된다`.

### Response

```text
REMINDER (External-Surface Write Falsification): hypothesis markers
detected in body. Verify each factual claim with executed evidence
before posting...
```

Default mode emits the reminder to stderr and **exits 0** (advisory,
not block). Set `PRAXIS_EXTERNAL_WRITE_STRICT=1` to convert into a hard
block (exit 2) — useful in CI or session-pinned workflows where you
want the gate to fire on the user's behalf.

### How to enable

Add an entry to your `~/.claude/settings.json` or `.claude/settings.json`
under `hooks.PreToolUse`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|mcp__.*slack.*|mcp__.*notion.*",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/external-write-falsify-check.sh" }
        ]
      }
    ]
  }
}
```

For strict mode (hard block):

```bash
export PRAXIS_EXTERNAL_WRITE_STRICT=1
```

Strict-mode env var accepts the **literal value `1` only** — `true` / `yes` / `on`
do NOT activate strict mode (defaults to advisory).

Restart Claude Code after adding the entry.

### Heuristic limits

The marker check is purely lexical. It cannot tell internal-team-DM
Slack from a customer-facing channel, nor can it tell a verified-fact
"could break" (an evidenced consequence) from a hypothesis "could break"
(an unverified guess). The CLAUDE.md rule's `Applies to` / `Does NOT
apply to` carveouts are NOT replicable in marker detection — the user
remains responsible for interpreting the reminder in context.

Known specific gaps (acknowledged; preconditions for any future
default-on flip — see follow-up tracking issue):

- **`likely` / `potential ` markers prone to false positives.** Phrases
  like "Most likely cause: stale cache" (a verified RCA write-up) or
  "Potential customers list: 5 brands" (business term) trip the warning.
- **Literal `\n` inside a quoted `--body` value splits the body.** The
  shared `_hook_utils.safe_tokenize` treats literal `\n` characters as
  command separators inside quoted strings. Use `--body-file` or a
  heredoc when content contains newlines and you want the full body
  scanned as one unit.
- **`--body-file -` / `-F -` (stdin) silent-passes.** `gh` accepts `-` as
  the file path placeholder for stdin (`gh issue create -F -`). The hook
  treats `-` as a literal file path; `open("-")` fails and the body is
  recorded as empty, so any hypothesis content streamed via stdin is not
  scanned. Use `--body-file <real-path>` when you want the body scanned.

### Parsing guarantees

Inherited from `_hook_utils.safe_tokenize` (same primitive as
`side-effect-scan.sh` and `block-gh-state-all.sh`):

- Quoted strings, comments, and `echo` arguments do not match markers.
- Env prefixes (`FOO=1 gh ...`), wrapper commands (`sudo`, `env`,
  `time`), shell control-flow keywords are peeled before scanning.
- Subshells (`$(...)`) are opaque to shlex — not decomposed (same
  acknowledged limitation as the sibling hooks).

### Tests

```bash
bash tests/test_external_write_falsify_check.sh
```

Covers 25 cases across the warn / silent / strict-block dimensions:
`gh` write subcommands (`comment`, `create`, `edit`, `review`) with each
body flag form (`--body`, `-b`, `--body-file`, `-F`, `--body=value`),
MCP slack / notion writes including nested shapes (Notion
`children[].paragraph.rich_text[].text.content`, Slack
`blocks[].text.text`) gated to recognized container/leaf entry points so
that property metadata (`properties.{name}.title[].text.content`) does
not surface as body, Korean marker, verified-claim silent paths,
non-write commands (`gh list` / `gh search`), chained Bash writes,
strict env toggle, and malformed-JSON fail-open.

### Evidence-trail follow-up

Memory entry for this rule + recurrence tracking will be filed as a
separate issue. The decision to flip default-on (or to roll back this
opt-in hook entirely) is gated on that trail.

Code-level preconditions for any future default-on flip are tracked in
issue #174. P2 (MCP nested-body extraction, gated to recognized
container/leaf entry points) has shipped. P3 (positional `gh` body
detection) was dropped after `gh --help` confirmed positional body is
not a supported gh CLI shape (`gh issue comment` accepts a single
positional, rejecting `<num> <body>` with `accepts 1 arg(s)`). P1
(false-positive frequency data accumulation) remains open and gates
the default-on flip.
