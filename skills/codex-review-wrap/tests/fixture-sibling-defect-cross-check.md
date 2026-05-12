# Fixture: Sibling-Defect Cross-Check (Step 5d)

Demonstrates the dual-PR scenario where the same root-cause defect exists in
both a "primary" PR (A) and its sibling port (B). Running `codex-review-wrap`
on PR A surfaces the defect; Step 5d cross-applies the falsifiable test to PR B
and records `same defect` in the ledger.

---

## Setup

Two branches in the same repo represent a Python implementation (PR A) and its
shell port (PR B) of a commit-flag-override hook.

### Branch A — `issue-200-hook-python` (primary review target)

File: `hooks/verify_commit_flag.py`

```python
# BUG: value-bearing git globals advance the token index by one,
# letting the value token be misread as the subcommand.
# e.g. `git -C /tmp commit --no-verify -m "msg"` → exit 0 (bypass)
def is_blocked_commit(args):
    tokens = args.split()
    i = 0
    while i < len(tokens):
        if tokens[i] == "commit":
            return "--no-verify" in tokens[i:]
        i += 1
    return False
```

### Branch B — `issue-199-hook-shell` (sibling port)

File: `hooks/verify_commit_flag.sh`

```bash
# BUG: same root cause — value-bearing globals (-C <path>) advance i by one,
# leaving the value token to be matched as a subcommand candidate.
is_blocked_commit() {
  local args=("$@")
  local i=0
  while (( i < ${#args[@]} )); do
    if [[ "${args[$i]}" == "commit" ]]; then
      for a in "${args[@]:$i}"; do [[ "$a" == "--no-verify" ]] && return 0; done
    fi
    (( i++ ))
  done
  return 1
}
```

---

## Step-by-step execution trace

### Step 5 start — sibling identification

```
AskUserQuestion: "이 PR이 다른 PR/레포의 port · parallel hotfix · A/B 구현체인가요?"

User: "issue-199-hook-shell 이 이 PR의 shell port입니다."
→ sibling identified: branch issue-199-hook-shell
```

Auto-detect also fires: PR A body contains `Port of #199`.

### Step 5a — classify findings (Round 1)

Codex returned two findings on PR A:

| Finding | Type | Rationale |
|---|---|---|
| F1: value-bearing globals (`-C <path>`) advance token index → subcommand misread | Fact-modifying | Changes the filter predicate controlling bypass |
| F2: bare `--gpg-sign` (no `=keyid`) not detected | Fact-modifying | Changes the set of matched CLI flags |

Both are fact-modifying — premise check required.

### Step 5b — verify premises

**F1 verification:**

```bash
# Falsifiable test: if the bug exists, this exits 0 (bypass)
git -C /tmp commit --no-verify -m "msg"
# Result (pre-fix): exit 0  ← bypass confirmed
```

Premise verified: the bug exists in PR A. F1 is a genuine finding.

**F2 verification:**

```bash
git commit --gpg-sign -m "msg"
# Result (pre-fix): exit 0  ← bypass confirmed
```

Premise verified: the bug exists in PR A. F2 is a genuine finding.

Ledger after 5b:

```
applied:  (pending — edits not yet committed)
rejected: (none)
```

### Step 5d — cross-check sibling (PR B: issue-199-hook-shell)

For each verified finding, apply the **same falsifiable test** against the sibling branch.

**F1 cross-check against PR B:**

```bash
cd /path/to/repo-wt/issue-199-hook-shell
git -C /tmp commit --no-verify -m "msg"
# Result: exit 0  ← bypass — same defect confirmed in shell version
```

**F2 cross-check against PR B:**

```bash
cd /path/to/repo-wt/issue-199-hook-shell
git commit --gpg-sign -m "msg"
# Result: exit 0  ← bypass — same defect confirmed in shell version
```

Ledger after 5d:

```
sibling-applied: devseunggwan/praxis#199 | round=1 | finding=F1(-C path bypass) | result=same defect
sibling-applied: devseunggwan/praxis#199 | round=1 | finding=F2(--gpg-sign bypass) | result=same defect
```

### Step 5d-iii — surface to user

```
⚠ 형제 구현체 동일 결함 발견 (2건):
   현재 PR: #200 (hook-python) — F1, F2 모두 확인됨
   형제 PR:  #199 (hook-shell) — 동일 결함 확인 근거:
     F1: git -C /tmp commit --no-verify -m "msg" → exit 0 (bypass)
     F2: git commit --gpg-sign -m "msg" → exit 0 (bypass)

제안된 수정:
  hooks/verify_commit_flag.sh:
    - F1: value-bearing globals (-C, --git-dir, --work-tree) 처리 시 i += 2
    - F2: --gpg-sign (bare form) 를 blocked-flag 목록에 추가

형제 PR #199에 적용할까요? (이 PR과 별도의 승인이 필요합니다)
```

User approves. Ledger updated:

```
sibling-applied: devseunggwan/praxis#199 | round=1 | finding=F1(-C path bypass) | result=same defect | fix-applied: yes
sibling-applied: devseunggwan/praxis#199 | round=1 | finding=F2(--gpg-sign bypass) | result=same defect | fix-applied: yes
```

---

## Expected outcome

| Requirement | Met? |
|---|---|
| PR A defect surfaced by codex-review-wrap | Yes — F1 and F2 verified in 5b |
| Step 5d cross-applies falsifiable test to PR B | Yes — same git invocations run against sibling branch |
| Ledger records `same defect` for both findings | Yes — two `sibling-applied:` rows with `result=same defect` |
| Reviewer reports findings for BOTH A and B | Yes — sibling surface message lists both PRs before applying |
| Sibling fix requires separate user approval | Yes — AskUserQuestion gated, not auto-applied |

---

## Counter-example: `does not apply`

If PR B had been a SQL-layer port with no CLI flag handling, the cross-check
would record:

```
sibling-applied: devseunggwan/praxis#199 | round=1 | finding=F1(-C path bypass) | result=does not apply
```

No fix is proposed for the sibling. The ledger entry serves as evidence that
the cross-check was performed and the context was absent, not overlooked.
