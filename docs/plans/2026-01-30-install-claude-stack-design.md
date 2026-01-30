# install-claude-stack 스킬 설계 (v2 - Plugin-based)

> **작성일**: 2026-01-30
> **수정일**: 2026-01-30
> **상태**: 구현 완료

---

## 1. 개요

### 1.1 목적

Claude Code 플러그인 기반 최적 스택을 자동으로 설치하는 스킬.

### 1.2 설치 대상 (v2)

| 플러그인 | 마켓플레이스 | 역할 |
|----------|--------------|------|
| **superpowers** | `claude-plugins-official` | TDD/워크플로우, brainstorming, writing-plans |
| **oh-my-claudecode** | `omc` | HUD, 32 에이전트, autopilot/ralph/ultrawork |
| **context7** | `claude-plugins-official` | 최신 라이브러리 문서 |
| **serena** | `claude-plugins-official` | 시맨틱 코드 분석 |

### 1.3 v1 → v2 변경사항

| v1 (이전) | v2 (현재) |
|-----------|-----------|
| Continuous-Claude-v3 (git clone) | 제거 |
| MCP 서버 5개 | 제거 |
| CC Usage (npx) | 제거 |
| Superpowers (플러그인) | 유지 |
| - | oh-my-claudecode (추가) |
| - | context7 (추가) |
| - | serena (추가) |

---

## 2. 스킬 메타데이터

```yaml
name: install-claude-stack
description: >
  Install optimal Claude Code plugin stack (superpowers + oh-my-claudecode + context7 + serena).
  Verifies existing installations, installs only missing plugins.
triggers:
  - "install claude stack"
  - "setup claude"
  - "install-claude-stack"
  - "claude 환경 설치"
```

---

## 3. 사용법

```bash
/install-claude-stack                     # 검증 → 누락분 인터랙티브 설치
/install-claude-stack --auto              # 전체 자동 설치
/install-claude-stack --check             # 검증만 (설치 안함)
/install-claude-stack --module <name>     # 특정 모듈만 설치
```

### 모듈 옵션

| 모듈 | 설명 |
|------|------|
| `superpowers` | Superpowers 플러그인만 |
| `omc` | oh-my-claudecode 플러그인만 |
| `context7` | Context7 플러그인만 |
| `serena` | Serena 플러그인만 |

---

## 4. 설치 흐름

### Phase 1: Prerequisites 검증

- Claude Code CLI 설치 확인

### Phase 2: 플러그인 검증

- `~/.claude/settings.json`에서 enabledPlugins 확인
- 각 플러그인 활성화 상태 확인

### Phase 3: 설치

누락된 플러그인만 설치:

```bash
# 마켓플레이스 추가
/plugin marketplace add claude-plugins-official
/plugin marketplace add omc

# 플러그인 설치
/plugin install superpowers@claude-plugins-official
/plugin install oh-my-claudecode@omc
/plugin install context7@claude-plugins-official
/plugin install serena@claude-plugins-official
```

### Phase 4: 후속 설정

```bash
/oh-my-claudecode:omc-setup
```

### Phase 5: 검증

설치 완료 리포트 출력

---

## 5. 플러그인별 기능

### 5.1 superpowers

- TDD 강제 (`test-driven-development`)
- 브레인스토밍 (`brainstorming`)
- 계획 작성 (`writing-plans`)
- 계획 실행 (`executing-plans`)
- 체계적 디버깅 (`systematic-debugging`)
- 완료 전 검증 (`verification-before-completion`)

### 5.2 oh-my-claudecode

- HUD (실시간 상태 표시)
- 32개 에이전트
- autopilot (자율 실행)
- ralph (완료까지 반복)
- ultrawork (병렬 실행)
- plan (계획 세션)

### 5.3 context7

- `resolve-library-id` - 라이브러리 ID 조회
- `get-library-docs` - 최신 문서 가져오기
- 사용법: 프롬프트에 "use context7" 포함

### 5.4 serena

- 시맨틱 코드 분석
- 심볼 탐색/수정
- 프로젝트 메모리 시스템

---

## 6. 에러 처리

| 에러 유형 | 처리 방식 |
|-----------|-----------|
| 마켓플레이스 추가 실패 | 재시도 |
| 플러그인 설치 실패 | 네트워크 확인 → 재시도 |
| 플러그인 충돌 | 충돌 플러그인 비활성화 안내 |

---

## 7. 참고 문서

- `docs/plugin-study-1.md` - 4개 도구 비교 분석
- `docs/plugin-study-2.md` - 스택 최적화 분석
- `docs/recommended-stack-analysis.md` - (v1 기준, 참고용)

---

## 8. 구현 체크리스트

- [x] SKILL.md 재작성 (플러그인 기반)
- [x] README 업데이트
- [x] 설계 문서 업데이트
- [x] GitHub 이슈 업데이트 (#6)
- [ ] 테스트
- [ ] 커밋
