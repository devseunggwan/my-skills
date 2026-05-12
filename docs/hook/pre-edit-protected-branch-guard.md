# PreToolUse Pre-Edit Protected-Branch Guard

`hooks/pre-edit-protected-branch-guard.py` fires on every PreToolUse event
for `Edit`, `Write`, and `NotebookEdit` tools. It blocks the edit when the
current branch is a protected branch and the working tree is dirty with files
not yet associated with an issue-driven worktree.

### Why this exists

The global `CLAUDE.md` rule "Issue-Driven Worktree Workflow (MANDATORY)"
requires every code change to live in a dedicated issue + branch + worktree.
Existing hooks (e.g. `block-pr-without-caller-evidence`) catch violations at
PR creation time — but the window between "first file edit" and "PR creation"
was unguarded. Work could start directly on `main` / `dev` / `prod`, only
getting caught after the diff was already committed (requiring a stash →
issue → worktree → stash-pop → commit → PR recovery cycle).

This hook closes the timing gap by firing **at the moment a file is first
opened for editing**, before any character is written.

### Relationship to existing hooks (dual-gate)

| Hook | Gate timing | Signal |
|------|-------------|--------|
| `pre-edit-protected-branch-guard` | Before first write | Dirty branch + new target file |
| `block-pr-without-caller-evidence` | At `gh pr create` | Missing caller-chain evidence in PR body |

The two gates are complementary, not redundant. This hook prevents the
mistake from starting; the PR gate is a backstop for cases this hook doesn't
cover (e.g. starting work on an unprotected branch then renaming it to main).

### What is blocked

| Scenario | Action |
|----------|--------|
| Protected branch + dirty tree + NEW file target | `permissionDecision: "deny"` |
| Protected branch + dirty tree + file ALREADY in diff (in-flight) | silent pass-through |
| Protected branch + clean tree | silent pass-through |
| Non-protected branch (`feature/…`, `issue-N-…`) + dirty tree | silent pass-through |
| Edit target in `/tmp/` (no repo root found) | silent pass-through (fail-open) |
| Edit target in `.omc/plans/` or `.claude/projects/` | silent pass-through (planning artifact) |
| Edit target is README/CHANGELOG/docs file (unless `PRAXIS_PBGUARD_BLOCK_DOCS=1`) | silent pass-through (docs skip) |
| Edit target inside `CLAUDE_PLUGIN_ROOT` (praxis plugin self-edit) | silent pass-through |
| `PRAXIS_PBGUARD_SKIP=1` set in environment | silent pass-through |
| `git` not installed / subprocess timeout | silent pass-through (fail-open) |
| Malformed stdin JSON | silent pass-through (fail-open) |
| Detached HEAD | silent pass-through (fail-open) |

### Trigger conditions (ALL must be true to block)

1. `tool_name ∈ {Edit, Write, NotebookEdit}`
2. No skip rule matches (see table above)
3. `git rev-parse --abbrev-ref HEAD` returns a protected branch name
4. `git status --porcelain` is non-empty (dirty working tree)
5. The edit target's repo-relative path is NOT present in the dirty-file set

### Protected branches

Default set: `main`, `dev`, `prod`, `master`.

Override via:
- `PRAXIS_PROTECTED_BRANCHES=release,stable` (comma-separated env var)
- `.claude/hook-config.json` key `"protected_branches": ["release", "stable"]`

### Issue tracker URL

The block message includes an issue tracker URL. Configure via:
- `PRAXIS_ISSUE_TRACKER_URL=https://github.com/yourorg/yourrepo/issues/new`
- `.claude/hook-config.json` key `"issue_tracker_url": "https://…"`

Default (if not set): a placeholder string instructing the user to configure.

### `.claude/hook-config.json` example

```json
{
  "issue_tracker_url": "https://github.com/yourorg/yourrepo/issues/new",
  "protected_branches": ["main", "dev", "prod"]
}
```

### Registration in consuming project's `.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-edit-protected-branch-guard.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

The hook is also registered in the praxis plugin's own `hooks/hooks.json` and
fires automatically when the plugin is loaded.

### Response (deny)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "[pre-edit:protected-branch-guard] Edit blocked: you are on protected branch 'main' with a dirty working tree..."
  }
}
```

### Parsing guarantees

- `tool_input.file_path` (Edit/Write) or `tool_input.notebook_path` (NotebookEdit)
  is read as-is — no shell tokenization. Paths with spaces are handled
  correctly because Python's `os.path` functions operate on raw strings.
- Git commands are run via `subprocess.run` with `cwd` derived from the edit
  target's directory. The hook never touches a shell; no injection risk.
- All `subprocess.run` calls use `timeout=5`. A slow git (network mount, cold
  index) will time out and fail-open rather than block Claude Code.
- Rename entries in `git status --porcelain` (`new -> old` and `\t`-separated
  forms) are parsed: both old and new paths are added to the dirty-file set.

### Test overrides (for CI / unit tests without a real repo)

| Env var | Effect |
|---------|--------|
| `PRAXIS_PBGUARD_TEST_REPO_ROOT=<path>` | Override `get_repo_root`. Use `"NONE"` to simulate not-in-a-repo. |
| `PRAXIS_PBGUARD_TEST_BRANCH=<name>` | Override current branch. Use `"HEAD"` to simulate detached HEAD. |
| `PRAXIS_PBGUARD_TEST_STATUS=<porcelain>` | Override `git status --porcelain` output. Empty string = clean tree. |

### Tests

```bash
bash hooks/test-pre-edit-protected-branch-guard.sh
```

Covers:
- **DENY paths**: dirty + protected + new target (Edit/Write/NotebookEdit), all
  four default protected branches, docs target with `PRAXIS_PBGUARD_BLOCK_DOCS=1`,
  custom protected branch list via `PRAXIS_PROTECTED_BRANCHES`.
- **PASS paths**: clean tree, non-protected branch, edit target already in dirty
  diff (in-flight continuation), untracked file in status (counts as in-flight),
  `/tmp/` target (fail-open: not in repo), `.omc/plans/` artifact,
  `.claude/projects/` memory file, README.md / CHANGELOG.md / `docs/` directory
  (docs skip), `PRAXIS_PBGUARD_SKIP=1`, non-scoped tool (Bash, Read),
  `PRAXIS_PBGUARD_TEST_REPO_ROOT=NONE` (not a git repo), detached HEAD,
  malformed stdin, empty `file_path`.
