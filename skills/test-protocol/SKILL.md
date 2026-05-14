---
name: test-protocol
description: >
  Mandatory testing discipline during development. Unit tests + functional tests
  in real environments, self-mocking guard, Pre-Implementation Surface Enumeration
  for validators/classifiers/routers, and Bulk Operation Pre-Enumeration for
  100+-item iterations. Auto-loads when writing tests, implementing validators,
  or planning bulk operations.
  Triggers on "test", "테스트", "검증", "verify", "validate", "unit test",
  "functional test", "smoke test", "mock", "fixture", "regex validator",
  "sanitizer", "classifier", "bulk operation", "batch", "100개", "N items",
  "surface enumeration", "edge case", "self-mocking", "vendor doc".
---

# Test Protocol

> **Single source of truth for testing discipline during development. Auto-loads on test-authoring triggers; CLAUDE.md retains the 1-line entry point.**

## Mandatory Testing During Development

> **Testing is NOT a final step — it is part of the development loop.**
> **Unit tests alone are NEVER sufficient. Functional tests in real environments are MANDATORY.**

Implement → test immediately → fix if failing → next implementation. Repeat this loop.

### Step 1: Unit Tests — immediately after writing new code

- New function/class written → write test → run → show output
- Also run existing related tests to catch regressions
- Show actual output of test command — no skipping
- Unit tests with mocks/fakes verify **logic** only — they do NOT verify **real behavior**
- **Self-mocking guard**: mock fixture's field names / response shapes must be cited verbatim from vendor docs, an existing working baseline (e.g., V1 implementation), or a sandbox/staging response — never paraphrased or mirrored from the SUT under test. SUT-mirrored mocks produce tautological passes (test passes because mock matches SUT, not because SUT matches reality), and field-name regressions ship silent. Required falsification case: a mock containing only the vendor-absent field must trigger explicit failure (RuntimeError / HTTPException) — not a silent default branch.

### Step 2: Functional Tests — MANDATORY, never skip

- After unit tests pass, verify actual behavior in a real environment — no exceptions
- Test against real systems (Docker, APIs), NOT mocks/fakes
- **Unit test pass ≠ verified. Verification requires functional test completion.**

| Change Target | Functional Test Method |
|---------------|----------------------|
| API/Backend | Call real endpoint → verify response body content (HTTP 200 alone is NOT sufficient) |
| Compose/Volume | `docker inspect` → verify actual mount paths; check files inside container |
| Frontend | Browser or Playwright → verify actual UI behavior |
| CLI tool | Run actual command → verify output |

### Step 3: Functional tests are also required when reviewing PRs

- When reviewing someone else's PR: checkout → build → unit test → **functional test**
- Never approve with "unit tests pass, ready to merge" — verify real behavior first
- If no test environment exists, set one up or ask the user

## Pre-Implementation Surface Enumeration

> Code that validates, classifies, routes, or otherwise interprets variable input/state — enumerate the surface BEFORE implementing. Prevents multi-round review cycles where each round discovers a new case the previous fix missed.

Applies to all of these, not just security code:

- **Security / validation** (SQL filters, sanitizers, auth checks): keyword-in-literal, comment-marker-in-literal, literal-marker-in-comment, multi-statement via semicolon, quote type mismatch (single vs double).
- **NLP signal detection** (intent classifiers, command-signal hooks): affirmation variants, **negation forms** (`don't proceed`, `진행하지 마`), **status / question forms** (`진행 상황을 알려줘`), **continuation variants missing the headline token** (`계속해` ≠ `계속 진행`), substring-vs-word-boundary collisions (`Product plan` vs `production`, `prod` vs `prod-only`).
- **Regex in Korean/English mixed text**: Python `re.\w` is Unicode-aware, so `\bpush\b` does NOT separate `push` from `할까요` (no boundary between Hangul and ASCII word chars). When ASCII boundary is the intent in mixed text, use `(?<![a-z])foo(?![a-z])` and test on actual mixed input before committing.
- **Multi-PR / multi-worktree shared state**: when dispatching independent PRs in parallel, enumerate every file each PR touches that a sibling also touches. `hooks.json` is the obvious one; `AGENTS.md` / `CLAUDE.md` (and any symlink targets), `marketplace.json`, `plugin.json`, hook-index tables in `README` or `docs/` are equally shared. First PR to merge wins — subsequent PRs need rebase.

Required for every case above:

- Each enumerated variant becomes a required test case.
- After each fix (Bugbot, Codex, review comment): re-run the full enumerated list, not just unit tests. "Unit tests pass" ≠ "surface covered". When a reviewer finds a new case, add it to the list and re-run the full list before the next review round.
- Verify test inputs actually reproduce the intended case before accepting results (e.g., SQL `'--'` single-quote ≠ `"--"` double-quote; `push할까요?` does NOT match `\bpush\b` in Python — verify with `python3 -c 're.search(...)'` before relying on the pattern).

## Bulk Operation Pre-Enumeration

> 100+ 항목 반복 또는 외부 시스템 mutation 의 bulk 실행 전, 실패 모드를 명시적으로 enumerate 하라.

필수 enumerate 항목:

- **Connection lifecycle**: long-lived single client 인가 per-iteration 재연결인가? 서버측에서 한 항목의 예외로 connection close 가능한가?
- **Per-item failure isolation**: 한 항목 실패가 다음 항목에 cascade 되는가? (예: thrift transport 끊김 후 모든 호출이 같은 예외로 실패)
- **Reconnect / retry policy**: transport / connection 끊김 시 자동 복구하는가? retry 횟수 / backoff?
- **Partial-progress checkpointing**: N개 진행 후 중단 시 재시작 가능한가? (성공 목록 / 남은 목록 분리)

검증 절차: enumerate 한 시나리오마다 single-item smoke test 로 raise 시키고 복구 동작을 확인한 뒤 bulk 진입한다. 첫 항목이 성공한다고 N번째 이후도 성공한다는 보장은 없다.

## Quick Reference

| Phase | Required action |
|-------|----------------|
| Code-write loop | implement → unit test → functional test → next item (no batch defer) |
| Mock fixtures | cite verbatim from vendor doc / sandbox / V1 baseline (never SUT-mirrored) |
| Validator/classifier | enumerate surface BEFORE coding (literal+comment+quote+negation+boundary variants) |
| Reviewer fix loop | re-run full enumerated list after each fix (not just unit tests) |
| Bulk operation | single-item smoke test with raise → verify reconnect/retry/checkpoint → bulk enter |
| PR review | checkout + build + unit test + **functional test** (HTTP 200 ≠ verified) |

## Integration

- **Entry point**: triggered on testing/validation keywords; CLAUDE.md keeps a 1-line pointer.
- **Pairs with**: `Verification Before Completion` (always-loaded in CLAUDE.md — same-turn evidence contract), `pr-workflow` skill (PR Review Protocol shares Step 1 triage), `Information Accuracy Layer 1` (CLI Binary Verification — `--help` before relying on flags).
- **Project-level overrides**: project CLAUDE.md may add domain-specific test environments (e.g., `hubctl exec` for Airflow containers) — those apply on top of this skill.
