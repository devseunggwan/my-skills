# Claude Code 최적 스택 분석 (2026년 1월)

> **목적**: 데이터 엔지니어링 업무에 최적화된 Claude Code 환경 구성
> **대상**: Continuous-Claude-v3 + MCP 5개 + CC Usage

---

## 1. 스택 개요

| 구성 요소 | 역할 | 핵심 가치 |
|-----------|------|-----------|
| **Continuous-Claude-v3** | 메인 프레임워크 | 세션 연속성, 109 스킬, TLDR |
| **GitHub MCP** | 코드 저장소 통합 | PR/Issue 자동화 |
| **PostgreSQL MCP** | 데이터베이스 쿼리 | 스키마 분석, 읽기 전용 쿼리 |
| **Filesystem MCP** | 로컬 파일 관리 | 안전한 파일 접근 |
| **Sequential Thinking MCP** | 복잡한 문제 해결 | 단계별 사고 과정 |
| **Context7 MCP** | 최신 문서 제공 | Airflow, Trino 등 최신 API |
| **CC Usage** | 비용 모니터링 | 토큰 사용량 추적 |

---

## 2. Continuous-Claude-v3 상세

### 2.1 핵심 기능

| 카테고리 | 수량 | 설명 |
|----------|------|------|
| **Skills** | 109개 | 자연어 트리거 도구 |
| **Agents** | 32개 | scout, oracle, kraken, plan-agent 등 |
| **Hooks** | 30개 | 라이프사이클 이벤트 처리 |
| **TLDR** | 5-Layer | AST → CallGraph → CFG → DFG → PDG |

### 2.2 핵심 워크플로우

```
/build    - 빌드 자동화
/fix      - 버그 수정
/refactor - 리팩토링
/tdd      - 테스트 주도 개발
/review   - 코드 리뷰
/explore  - 코드베이스 탐색
/security - 보안 검사
/release  - 릴리스 관리
```

### 2.3 메모리 시스템

**Ledger (원장)**
- 의사결정, 아키텍처 선택, 세션 진행 기록
- 위치: `thoughts/ledgers/CONTINUITY_*.md`

**Handoff (인수인계)**
- YAML 형식의 컨텍스트 전달 파일
- 현재 목표, 진행 상황, 코드 변경 사항 인코딩
- 위치: `thoughts/shared/handoffs/*.yaml`

### 2.4 작동 방식

```
1. SessionStart → Ledger 로드, 메모리 복원, TLDR 캐시 워밍
2. Working      → 파일 편집 추적, 변경 인덱싱, 스킬 힌트 수집
3. PreCompact   → ~20개 dirty 파일 시 자동 handoff 생성
4. SessionEnd   → 상태 저장, 데몬이 archival 메모리 추출
5. NextSession  → /clear로 fresh context, 상태는 보존
```

**철학**: "Compound, don't compact" (압축하지 말고 누적하라)

### 2.5 설치 요구사항

| 요구사항 | 버전/설명 |
|----------|-----------|
| Python | 3.11+ |
| uv | 패키지 매니저 |
| Docker | PostgreSQL + pgvector |
| Claude Code CLI | 최신 버전 |

### 2.6 디렉토리 구조

```
Continuous-Claude-v3/
├── .claude/
│   ├── skills/        # 109개 스킬 정의
│   ├── agents/        # 32개 에이전트 설정
│   └── hooks/         # 30개 시스템 훅
├── opc/               # 메인 Python 프로젝트
│   └── scripts/setup/wizard.py
├── docker/            # PostgreSQL + pgvector
├── thoughts/          # 런타임 상태
│   ├── ledgers/       # 연속성 원장
│   └── shared/
│       ├── handoffs/  # YAML 컨텍스트 전달
│       └── plans/     # 계획 아티팩트
└── .tldr/             # TLDR 데몬 캐시
```

---

## 3. TLDR Code Analysis (llm-tldr)

### 3.1 5-Layer 분석 아키텍처

| Layer | 이름 | 분석 내용 | 사용 시점 |
|-------|------|-----------|-----------|
| L1 | AST | 함수/클래스 식별 | 코드 브라우징 |
| L2 | Call Graph | 함수 호출 관계 | 리팩토링 |
| L3 | Control Flow | 분기 패턴, 복잡도 | 복잡도 분석 |
| L4 | Data Flow | 값 이동 추적 | 변수 추적 |
| L5 | Program Dependence | 특정 라인 영향 분석 | null 디버깅 |

### 3.2 주요 명령어

```bash
# 탐색
tldr tree [path]                    # 파일 구조
tldr structure [path] --lang py     # 함수/클래스 목록
tldr extract <file>                 # 전체 파일 분석

# 분석
tldr context <func> --project <path>  # LLM용 요약 (95% 토큰 절약)
tldr cfg <file> <function>            # 제어 흐름 시각화
tldr dfg <file> <function>            # 데이터 흐름 분석
tldr slice <file> <func> <line>       # 프로그램 슬라이싱

# 크로스-파일
tldr calls [path]                   # 호출 그래프
tldr impact <func> [path]           # 역방향 호출 그래프
tldr dead [path]                    # 미사용 코드 탐지

# 시맨틱 검색
tldr warm <path>                    # 인덱스 빌드
tldr semantic "<query>" [path]      # 자연어 코드 검색
```

### 3.3 지원 언어 (16개)

Python, TypeScript, JavaScript, Go, Rust, Java, C, C++, Ruby, PHP, C#, Kotlin, Scala, Swift, Lua, Elixir

---

## 4. MCP 서버 상세

### 4.1 GitHub MCP

**기능**:
- 저장소 관리 (생성, 포크, 검색)
- 파일 작업 (생성/수정, 다중 파일 커밋)
- 브랜치/PR/이슈 관리
- 검색 기능

**설정**:
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_TOKEN>"
      }
    }
  }
}
```

**필요 권한**: repo, read:org, read:user (최소)

### 4.2 PostgreSQL MCP

**기능**:
- 읽기 전용 데이터베이스 접근
- 스키마 검사 (컬럼명, 데이터 타입)
- SQL 쿼리 실행 (읽기 전용 트랜잭션)

**설정**:
```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres",
        "postgresql://user:pass@localhost:5432/mydb"
      ]
    }
  }
}
```

**보안 권장사항**:
- 읽기 전용 전용 계정 사용
- SSL 연결 활성화
- IP 제한 설정

### 4.3 Filesystem MCP

**기능**:
- 안전한 파일 읽기/쓰기
- 디렉토리 탐색
- 설정 가능한 접근 제어

**설정**:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/Users/username/projects",
        "/Users/username/data"
      ]
    }
  }
}
```

**주의**: 허용할 디렉토리만 명시적으로 지정

### 4.4 Sequential Thinking MCP

**기능**:
- 복잡한 문제를 단계별로 분해
- 사고 과정 수정 및 개선
- 대안적 추론 경로 분기

**설정**:
```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
  }
}
```

**사용 시점**: 복잡한 아키텍처 설계, 디버깅, 의사결정

### 4.5 Context7 MCP

**기능**:
- 최신 버전별 문서 제공
- 코드 예제 직접 삽입
- 할루시네이션 방지

**설정 (CLI)**:
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest
```

**설정 (API 키 포함)**:
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp --api-key YOUR_API_KEY
```

**사용법**: 프롬프트에 `use context7` 포함

**제공 도구**:
- `resolve-library-id`: 라이브러리 이름 → Context7 ID
- `get-library-docs`: 라이브러리 문서 가져오기 (기본 5000 토큰)

---

## 5. CC Usage (토큰 모니터링)

### 5.1 설치

```bash
# 직접 실행 (설치 없이)
npx ccusage@latest

# 또는
bunx ccusage
pnpm dlx ccusage
```

### 5.2 주요 명령어

```bash
# 리포트 모드
npx ccusage daily      # 일별 집계
npx ccusage monthly    # 월별 요약
npx ccusage session    # 세션별 분석
npx ccusage blocks     # 5시간 빌링 윈도우

# 필터링
--since 20260125 --until 20260130
--json              # JSON 출력
--breakdown         # 모델별 비용 분석
--instances         # 프로젝트 그룹화
--timezone UTC
--compact           # 컴팩트 출력
```

### 5.3 추적 항목

- 일별/월별 토큰 사용량
- 세션별 그룹화
- 5시간 빌링 윈도우
- 모델 식별
- USD 비용 계산
- 캐시 토큰 분리

---

## 6. 설치 순서 (권장)

### Phase 1: 기본 환경

```bash
# 1. Node.js 확인 (v18+ 권장)
node --version

# 2. Python 3.11+ 확인
python3 --version

# 3. Docker 확인
docker --version

# 4. uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Phase 2: Continuous-Claude-v3

```bash
# 1. 클론
git clone https://github.com/parcadei/Continuous-Claude-v3.git
cd Continuous-Claude-v3

# 2. 설치 위자드 실행
cd opc
uv run python -m scripts.setup.wizard

# 위자드가 수행하는 12단계:
# - 기존 설정 백업
# - 필수 요소 검증
# - DB/API 키 설정
# - Docker 스택 시작
# - 마이그레이션 실행
# - Claude 통합 설치
# - 선택적 수학 기능 (SymPy, Z3, Pint)
# - TLDR 도구 설치
# - 진단 실행
```

### Phase 3: MCP 서버

```bash
# 1. GitHub MCP
claude mcp add github -- npx -y @modelcontextprotocol/server-github
# 환경변수 설정: GITHUB_PERSONAL_ACCESS_TOKEN

# 2. PostgreSQL MCP
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres "postgresql://localhost/mydb"

# 3. Filesystem MCP
claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/projects ~/data

# 4. Sequential Thinking MCP
claude mcp add sequential-thinking -- npx -y @modelcontextprotocol/server-sequential-thinking

# 5. Context7 MCP
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest
```

### Phase 4: 검증

```bash
# MCP 서버 목록 확인
claude mcp list

# CC Usage 테스트
npx ccusage@latest daily

# TLDR 테스트 (프로젝트 디렉토리에서)
tldr warm .
tldr tree .
```

---

## 7. 데이터 엔지니어링 활용 시나리오

### 7.1 Airflow DAG 개발

```bash
# 1. Context7로 최신 Airflow 문서
"use context7: Airflow 3.x TaskFlow API"

# 2. TLDR로 기존 DAG 분석
tldr structure dags/ --lang python
tldr calls dags/

# 3. Sequential Thinking으로 설계
"use sequential thinking: Design ETL pipeline for user events"

# 4. PostgreSQL로 스키마 확인
"Check existing schema in analytics DB"
```

### 7.2 Trino 쿼리 최적화

```bash
# 1. 기존 쿼리 분석
tldr extract queries/slow_query.sql

# 2. 데이터 흐름 추적
tldr dfg queries/slow_query.sql main_query

# 3. Context7로 Trino 문서
"use context7: Trino query optimization partition pruning"
```

### 7.3 디버깅 워크플로우

```bash
# 1. Sequential Thinking으로 문제 분해
"use sequential thinking: Debug memory spike in daily_etl DAG"

# 2. TLDR로 영향 분석
tldr impact process_daily_data dags/

# 3. 프로그램 슬라이싱
tldr slice dags/daily_etl.py process_data 45
```

---

## 8. 토큰 절약 전략

| 기법 | 절약률 | 설명 |
|------|--------|------|
| **TLDR 분석** | 95% | 전체 코드 대신 구조 정보만 전달 |
| **Ledger 시스템** | 70%+ | 반복 정보 제거, 누적 학습 |
| **MCP Lazy Loading** | 95% | 필요 시에만 도구 로드 |
| **CC Usage 모니터링** | - | 낭비 식별 및 최적화 |

**예상 총 절약**: 70-80% 토큰 감소

---

## 9. 참고 자료

### GitHub 리포지토리

- [Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) - 3.4k stars
- [llm-tldr](https://github.com/parcadei/llm-tldr) - TLDR 코드 분석
- [ccusage](https://github.com/ryoppippi/ccusage) - 토큰 사용량 분석
- [MCP Servers](https://github.com/modelcontextprotocol/servers) - 공식 MCP 서버

### MCP 문서

- [Model Context Protocol](https://modelcontextprotocol.io/) - 공식 문서
- [Context7](https://context7.com/) - API 키 발급

### 관련 뉴스

- [Meta의 Manus AI $2B 인수 (2025.12.29)](https://techcrunch.com/2025/12/29/meta-just-bought-manus-an-ai-startup-everyone-has-been-talking-about/) - planning-with-files 패턴의 기원

---

## 10. 버전 정보

| 구성 요소 | 버전/날짜 |
|-----------|-----------|
| 문서 작성일 | 2026-01-30 |
| Continuous-Claude-v3 | 최신 (3.4k stars) |
| PostgreSQL MCP | 0.6.2 |
| Context7 MCP | @latest |

---

*이 문서는 docs/plugin-study-1.md, plugin-study-2.md의 분석을 기반으로 작성되었습니다.*
