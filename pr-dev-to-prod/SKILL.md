---
name: pr-dev-to-prod
description: Create release PR from dev to prod branch with impact analysis. Use when releasing to production. Triggers on "dev to prod", "release PR", "릴리스 PR", "배포 PR", "pr-dev-to-prod".
---

# Dev to Prod Release PR

dev 브랜치의 변경사항을 prod로 릴리스하는 PR을 자동으로 생성합니다.

## Prerequisites

**참고 PR 링크 필수** - 이전 릴리스 PR을 참고하여 동일한 형식으로 생성합니다.

사용자가 참고 PR을 제공하지 않으면 반드시 요청하세요:
> "참고할 이전 릴리스 PR 링크를 제공해주세요. (예: https://github.com/org/repo/pull/123)"

## When to Use

- dev 브랜치의 변경사항을 prod로 릴리스할 때
- 정기 배포 PR 생성 시
- "dev to prod", "release PR", "릴리스 PR", "배포 PR" 키워드 사용 시

## Workflow

### Phase 0: 필수 입력 확인

1. **참고 PR 링크 확인** - 없으면 반드시 요청
2. 참고 PR 형식 분석:
```bash
gh pr view <참고PR번호> --json title,body
```

### Phase 1: 정보 수집

1. 최신 정보 동기화:
```bash
git fetch origin
```

2. 커밋 차이 확인:
```bash
git log origin/prod..origin/dev --oneline
```

3. 각 커밋에서 PR 번호 추출:
   - Squash merge: `feat(scope): description (#1234)` → `#1234`
   - Merge commit: `Merge pull request #1234` → `#1234`

4. 각 PR의 상세 정보 조회 (병렬 실행):
```bash
gh pr view <PR번호> --json title,body,number,labels
```

### Phase 2: PR 본문 생성 (자동)

1. 참고 PR 형식에 맞춰 변경사항 타입별 분류
2. 각 PR body에서 영향도 정보 추출하여 Impact Analysis 테이블 자동 생성
3. 상세 영향 범위 섹션 자동 작성
4. Related Issues 섹션 자동 작성 (PR body에서 Closes/Fixes/Refs 추출)
5. Test Plan 체크리스트 작성

### Phase 3: PR 생성

1. 사용자에게 본문 미리보기 제시
2. **승인 후** PR 생성:
```bash
gh pr create --base prod --head dev \
  --title "release: Production Deploy (YYYY-MM-DD)" \
  --body "$(cat <<'EOF'
[PR 본문]
EOF
)"
```

## PR Title Format

```
release: Production Deploy (YYYY-MM-DD)
```

날짜는 PR 생성 당일 날짜를 사용합니다.

## PR Body Template

```markdown
## 주요 변경사항

### Bug Fixes
<!-- fix 타입 PR들 -->
- #123 - PR 제목

### Features
<!-- feat 타입 PR들 -->
- #456 - PR 제목

### Chores
<!-- chore, refactor, ci, docs 등 타입 PR들 -->
- #789 - PR 제목

---

## Impact Analysis (영향 범위)

### 영향도 요약

| 변경사항 | 영향도 | 영향 DAG | 런타임 영향 |
|---------|--------|----------|------------|
| #123 - 제목 | Low | dag_a | 없음 |
| #456 - 제목 | Medium | dag_b, dag_c | 스케줄 변경 |

### 상세 영향 범위

#### #123 - PR 제목
| 구분 | 내용 |
|------|------|
| **영향 DAG** | dag_a |
| **변경 파일** | `path/to/file.py` |
| **런타임 영향** | 없음 |
| **외부 시스템** | - |
| **롤백 영향** | 즉시 롤백 가능 |

---

## Related Issues

- Closes #XXX, #YYY

## Test Plan

- [x] 모든 PR에서 CI 통과 확인
- [ ] prod 배포 후 DAG 정상 로드 확인
- [ ] Airflow 모니터링

Generated with [Claude Code](https://claude.ai/code)
```

## Impact Analysis Guide

### 영향도 판단 기준

| 영향도 | 조건 | 예시 |
|--------|------|------|
| **High** | 기존 동작 변경, Breaking change, 다수 DAG 영향 | 스키마 변경, API 변경 |
| **Medium** | 특정 DAG 로직 변경, 외부 시스템 연동 변경 | 쿼리 수정, 스케줄 변경 |
| **Low** | 모니터링/로깅만 변경, 문서 변경 | 알림 추가, 로그 개선 |
| **None** | 파일 추가만 (DAG에서 미사용), 개발환경만 영향 | 테스트 추가, CI 변경 |

### PR Body에서 추출할 정보

각 PR의 body에서 다음 키워드를 찾아 영향도 분석에 활용:
- **영향 DAG**: "영향 DAG", "Affected DAG", "DAG:" 등
- **변경 파일**: 파일 경로 목록
- **런타임 영향**: "런타임", "스케줄", "실행 시간" 등
- **외부 시스템**: Slack, CloudWatch, S3, API 등 언급 여부

## Change Type Classification

커밋/PR 타이틀에서 타입 추출:

| Prefix | 분류 |
|--------|------|
| `fix:`, `fix(` | Bug Fixes |
| `feat:`, `feat(` | Features |
| `chore:`, `refactor:`, `ci:`, `docs:`, `perf:`, `style:`, `test:` | Chores |

## Important Notes

1. **사용자 승인 없이 PR 생성하지 않음**
2. **참고 PR 형식을 최대한 따름**
3. **영향도 정보가 PR body에 없으면 "확인 필요"로 표시**
4. **Breaking change가 있으면 반드시 강조**

## Edge Cases

### 커밋 차이가 없는 경우

```bash
git log origin/prod..origin/dev --oneline
```

결과가 비어있으면 사용자에게 알림:
> "dev와 prod 브랜치 사이에 배포할 변경사항이 없습니다."

### PR 정보를 찾을 수 없는 경우

커밋에서 PR 번호를 추출할 수 없거나 `gh pr view`가 실패하면:
- 해당 커밋은 "직접 커밋"으로 표시
- 커밋 메시지와 변경 파일 정보를 대신 사용

### 참고 PR과 형식이 다른 경우

참고 PR의 형식을 파싱할 수 없으면:
- 기본 템플릿 사용
- 사용자에게 형식 차이 알림

## Example Usage

```
User: dev to prod PR 만들어줘
Assistant: 참고할 이전 릴리스 PR 링크를 제공해주세요.

User: https://github.com/org/repo/pull/6700
Assistant: [참고 PR 분석 후 커밋 차이 확인 및 PR 본문 미리보기 제시]
```
