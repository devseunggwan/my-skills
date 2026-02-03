---
name: pr-dev-to-prod
description: Create release PR from dev to prod branch with impact analysis. Use when releasing to production. Triggers on "dev to prod", "release PR", "pr-dev-to-prod".
---

# Dev to Prod Release PR

Automatically creates a PR to release changes from dev branch to prod.

## Prerequisites

**Reference PR** - Creates PR in the same format as the previous release PR.

- If provided: Use directly
- If not provided: Auto-search for recent release PR merged to prod branch

## When to Use

- When releasing changes from dev branch to prod
- When creating scheduled deployment PRs
- When user mentions "dev to prod", "release PR", "pr-dev-to-prod"

## Workflow

### Phase 0: Validate Required Inputs

1. **Check reference PR link**
   - If provided: Use it directly
   - If not provided: Auto-search for recent release PR

2. **Auto-search logic** (when reference not provided):
```bash
# Step 1: Search with release label (highest priority)
gh pr list --base prod --state merged --label release --limit 1 --json number,title

# Step 2: If not found, search by title pattern
gh pr list --base prod --state merged --limit 10 --json number,title | \
  jq '[.[] | select(.title | test("^release:|Production Deploy"))] | .[0]'

# Step 3: If still not found, get most recent merged PR to prod
gh pr list --base prod --state merged --limit 1 --json number,title
```

3. **Confirm with user**:
   - If found: "Found recent release PR #XXX as reference. Use this? (Y/n)"
   - If not found: "No recent release PR found. Please provide a reference PR link."

4. Analyze reference PR format:
```bash
gh pr view <reference_PR_number> --json title,body
```

### Phase 1: Gather Information

1. Sync latest information:
```bash
git fetch origin
```

2. Check commit differences:
```bash
git log origin/prod..origin/dev --oneline
```

3. Extract PR numbers from each commit:
   - Squash merge: `feat(scope): description (#1234)` → `#1234`
   - Merge commit: `Merge pull request #1234` → `#1234`

4. Fetch detailed PR information (run in parallel):
```bash
gh pr view <PR_number> --json title,body,number,labels
```

### Phase 2: Generate PR Body (Automatic)

1. Classify changes by type following reference PR format
2. Extract impact information from each PR body to auto-generate Impact Analysis table
3. Auto-generate detailed impact scope section
4. Auto-generate Related Issues section (extract Closes/Fixes/Refs from PR bodies)
5. Write Test Plan checklist

### Phase 3: Create PR

1. Present body preview to user
2. **After approval**, create PR:
```bash
gh pr create --base prod --head dev \
  --title "release: Production Deploy (YYYY-MM-DD)" \
  --body "$(cat <<'EOF'
[PR body]
EOF
)"
```

## PR Title Format

```
release: Production Deploy (YYYY-MM-DD)
```

Use the current date when creating the PR.

## PR Body Template

```markdown
## Summary of Changes

### Bug Fixes
<!-- fix type PRs -->
- #123 - PR title

### Features
<!-- feat type PRs -->
- #456 - PR title

### Chores
<!-- chore, refactor, ci, docs, etc. type PRs -->
- #789 - PR title

---

## Impact Analysis

### Impact Summary

| Change | Impact | Affected DAGs | Runtime Impact |
|--------|--------|---------------|----------------|
| #123 - title | Low | dag_a | None |
| #456 - title | Medium | dag_b, dag_c | Schedule change |

### Detailed Impact Scope

#### #123 - PR title
| Category | Details |
|----------|---------|
| **Affected DAGs** | dag_a |
| **Changed Files** | `path/to/file.py` |
| **Runtime Impact** | None |
| **External Systems** | - |
| **Rollback Impact** | Immediate rollback possible |

---

## Related Issues

- Closes #XXX, #YYY

## Test Plan

- [x] CI passed on all PRs
- [ ] Verify DAGs load correctly after prod deployment
- [ ] Airflow monitoring

Generated with [Claude Code](https://claude.ai/code)
```

## Impact Analysis Guide

### Impact Level Criteria

| Impact | Condition | Example |
|--------|-----------|---------|
| **High** | Changes existing behavior, Breaking change, Affects multiple DAGs | Schema change, API change |
| **Medium** | Changes specific DAG logic, External system integration changes | Query modification, Schedule change |
| **Low** | Only monitoring/logging changes, Documentation changes | Alert addition, Log improvement |
| **None** | Only file additions (not used by DAGs), Only affects dev environment | Test additions, CI changes |

### Information to Extract from PR Body

Search for the following keywords in each PR body for impact analysis:
- **Affected DAGs**: "Affected DAG", "DAG:", "Impact DAG", etc.
- **Changed Files**: File path list
- **Runtime Impact**: "runtime", "schedule", "execution time", etc.
- **External Systems**: Mentions of Slack, CloudWatch, S3, API, etc.

## Change Type Classification

Extract type from commit/PR title:

| Prefix | Classification |
|--------|----------------|
| `fix:`, `fix(` | Bug Fixes |
| `feat:`, `feat(` | Features |
| `chore:`, `refactor:`, `ci:`, `docs:`, `perf:`, `style:`, `test:` | Chores |

## Important Notes

1. **Never create PR without user approval**
2. **Follow reference PR format as closely as possible**
3. **Mark as "needs verification" if impact info is not in PR body**
4. **Always highlight breaking changes**

## Edge Cases

### No commits between branches

```bash
git log origin/prod..origin/dev --oneline
```

If result is empty, notify user:
> "There are no changes to deploy between dev and prod branches."

### PR information not found

If PR number cannot be extracted from commit or `gh pr view` fails:
- Mark the commit as "direct commit"
- Use commit message and changed files information instead

### Reference PR format mismatch

If reference PR format cannot be parsed:
- Use default template
- Notify user about format difference

## Example Usage

```
User: Create dev to prod PR
Assistant: Please provide a reference release PR link.

User: https://github.com/org/repo/pull/6700
Assistant: [Analyzes reference PR, checks commit diff, and presents PR body preview]
```
