---
name: cmux-browser
description: "cmux 브라우저 자동화 기반 E2E 테스트. cmux browser CLI로 내비게이션, 폼 입력, 클릭, 상태 검증을 수행합니다. SPA hydration wait 프로토콜 포함. Triggers on \"cmux browser\", \"cmux 브라우저\"."
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# cmux Browser E2E Test

cmux 터미널 내장 브라우저의 자동화 CLI를 사용하여 E2E 테스트를 수행합니다.
Playwright MCP 대신 `cmux browser` 명령어를 직접 호출하여 브라우저를 제어합니다.

## 사용자 입력

- `$ARGUMENTS` — 테스트 대상 URL 또는 테스트 시나리오 설명. 비어 있으면 질문합니다.

---

## Iron Law — DOM 의존 액션 전 SPA Hydration Wait

```
snapshot --interactive 포함, DOM에 의존하는 첫 액션(click/fill/is/get) 직전에
반드시 SPA Hydration Wait Protocol을 1회 실행할 것.
wait --load-state complete 단독 사용은 SPA에서 충분하지 않다.
```

`wait --load-state complete`는 HTML·CSS·스크립트 로드 완료(network level)를 의미하지만,
React·Vue·Next.js 같은 SPA는 그 이후에 JS가 DOM을 client-side render한다.
이 JS 실행이 끝나기 전에 snapshot이나 DOM 조작을 시도하면 빈 트리(shell/skeleton)만 반환되거나
존재하지 않는 요소를 대상으로 하게 된다.

---

## SPA Hydration Wait Protocol

snapshot 전 **항상** 이 순서로 실행한다:

### Step 1 — Load State Wait

```bash
cmux browser wait --load-state complete --timeout 15
```

네트워크 레벨 로드 완료. SPA 단독으로는 불충분하나 필수 선행 조건.

### Step 2 — SPA 자동 감지

```bash
cmux browser eval "!!(window.__NEXT_DATA__||window.__NUXT__||window.__remixContext||window.__SVELTEKIT_DATA__||window.___gatsby||window.__INITIAL_STATE__||window.ng||document.querySelector('[data-reactroot],[data-v-app],[data-server-rendered],[ng-version],[data-svelte-h],[q\\\\:container]'))"
```

출력이 `true`이면 SPA 프레임워크 감지됨 → Step 3A 또는 3B 진행.
출력이 `false`/`null`이거나 감지 자체가 실패해도 → Step 3A를 짧은 timeout(3초)로 실행 후 Step 4.
SPA marker가 없더라도 정적 페이지에서는 Step 3A가 즉시 통과하므로 cost가 거의 없다.

### Step 3A — 콘텐츠 밀도 기반 Hydration 대기 (기본값)

DOM에 실질적인 콘텐츠가 렌더링될 때까지 대기한다:

```bash
# single-quote 사용 — 내부 JS에 double-quote를 escape 없이 사용 가능
cmux browser wait --function 'document.readyState==="complete" && document.body.innerText.length>200 && document.querySelectorAll("a[href],button").length>5 && !document.querySelector("[aria-busy=true],[data-loading=true]")' --timeout 10
```

- `innerText.length > 200`: 실제 텍스트 콘텐츠가 있음 (DOM node count는 loading skeleton이 포함될 수 있어 부정확)
- `a[href],button > 5`: 인터랙티브 요소가 렌더링되었음 (nav/sidebar 포함 신호)
- `aria-busy`, `data-loading`: 로딩 상태가 해소되었음을 확인
- attribute selector 따옴표 없는 형태(`[aria-busy=true]`)는 CSS 스펙상 valid

### Step 3B — 명시적 Selector 대기 (정밀 제어)

특정 요소가 화면에 나타날 때까지 대기한다:

```bash
# 네비게이션이 렌더링될 때까지 대기
cmux browser wait --selector "nav, aside, [role='navigation']" --timeout 10

# 또는 콘텐츠 컨테이너가 비어 있지 않을 때까지
cmux browser wait --selector "main article, .content > *:not(:empty)" --timeout 10

# 또는 특정 텍스트 출현 대기
cmux browser wait --text "API Reference" --timeout 10
```

Step 3B는 대상 사이트의 DOM 구조를 알고 있을 때 가장 정확하다.
모르면 Step 3A + snapshot 결과 검증 → 비어 있으면 Step 3B로 재시도.

### Step 4 — Snapshot

```bash
cmux browser snapshot --interactive
```

### Snapshot 결과 검증 (필수)

snapshot 직후 콘텐츠 밀도를 정량 확인한다:

```bash
# 링크·헤딩·버튼 개수로 hydration 완료 여부 판정
cmux browser eval 'document.querySelectorAll("a[href],h1,h2,h3,button,nav,article").length'
```

- **10 미만** → hydration 미완료 가능성 높음 → Step 3B로 재시도
- **10 이상** → hydration 완료로 간주하고 진행

**빈 트리 징후**: "Jump to Content", "Welcome" 같은 2~5개 노드만 있고
nav/article/h2 등이 없으면 hydration 미완료 → Step 3B로 재시도하거나 timeout을 늘린다.

### 프레임워크별 Hydration 마커

| 프레임워크 | 감지 신호 | 권장 대기 |
|-----------|----------|----------|
| Next.js | `window.__NEXT_DATA__` 존재 | Step 3A |
| Nuxt.js | `window.__NUXT__` 존재 | Step 3A |
| Remix | `window.__remixContext` 존재 | Step 3A |
| React (CRA) | `[data-reactroot]` 속성 | Step 3A |
| Vue 3 | `[data-v-app]` 속성 | Step 3A |
| ReadMe.io / 사이드바 SPA | `[class*="Sidebar"]` 존재 | Step 3B `--selector "[class*='Sidebar'],[class*='rm-Sidebar'],nav.sidebar"` |
| Gatsby | `window.___gatsby` 존재 | Step 3A |
| SvelteKit | `window.__SVELTEKIT_DATA__` 존재 | Step 3A |
| Angular | `[ng-version]` 속성 | Step 3A |

---

## cmux browser 명령어 레퍼런스

### 내비게이션

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `open <url>` | 브라우저에서 URL 열기 | `cmux browser open https://example.com` |
| `open-split <url>` | 분할 뷰로 URL 열기 | `cmux browser open-split https://example.com` |
| `navigate <url>` | 현재 탭에서 URL 이동 | `cmux browser navigate /dashboard` |
| `back` | 뒤로 가기 | `cmux browser back` |
| `forward` | 앞으로 가기 | `cmux browser forward` |
| `reload` | 페이지 새로고침 | `cmux browser reload` |
| `url` | 현재 URL 조회 | `cmux browser url` |

### DOM 상호작용

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `click <selector>` | 요소 클릭 | `cmux browser click "button:has-text('Submit')"` |
| `dblclick <selector>` | 더블클릭 | `cmux browser dblclick ".editable-cell"` |
| `hover <selector>` | 마우스 호버 | `cmux browser hover ".tooltip-trigger"` |
| `focus <selector>` | 요소 포커스 | `cmux browser focus "#email"` |
| `check <selector>` | 체크박스 선택 | `cmux browser check "#agree"` |
| `uncheck <selector>` | 체크박스 해제 | `cmux browser uncheck "#newsletter"` |

### 텍스트 입력

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `type <selector> <text>` | 키 입력 시뮬레이션 | `cmux browser type "#search" "query"` |
| `fill <selector> <value>` | 필드 값 설정 (기존 값 대체) | `cmux browser fill "#email" "test@example.com"` |
| `press <key>` | 키보드 키 누르기 | `cmux browser press Enter` |
| `scroll` | 페이지 스크롤 | `cmux browser scroll --dy 300` |

### 페이지 검사

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `snapshot [--interactive\|-i]` | 접근성 트리 캡처 | `cmux browser snapshot --interactive` |
| `screenshot [--out <path>]` | 스크린샷 파일 저장 | `cmux browser screenshot --out /tmp/test.png` |
| `get <prop> [--selector <css>]` | 요소 속성 조회 | `cmux browser get text --selector "#status"` |
| `is <state> [--selector <css>]` | 요소 상태 확인 | `cmux browser is visible --selector "#modal"` |
| `find <role\|text\|...>` | 요소 검색 | `cmux browser find role button` |
| `highlight [--selector <css>]` | 요소 하이라이트 | `cmux browser highlight ".error"` |

### 대기 (Wait)

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `wait --selector <css>` | 셀렉터 출현 대기 | `cmux browser wait --selector ".loaded"` |
| `wait --text <text>` | 텍스트 출현 대기 | `cmux browser wait --text "완료"` |
| `wait --url <pattern>` | URL 변경 대기 | `cmux browser wait --url "/dashboard"` |
| `wait --load-state complete` | document.readyState 완료 대기 | `cmux browser wait --load-state complete` |
| `wait --load-state interactive` | DOM 파싱 완료 대기 | `cmux browser wait --load-state interactive` |
| `wait --function <js>` | JS 조건 만족 대기 | `cmux browser wait --function "!!window.__APP_READY__"` |
| `wait --timeout <sec>` | 대기 최대 시간 지정 | `cmux browser wait --selector ".btn" --timeout 20` |

### JavaScript 실행

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `eval <code>` | JS 코드 실행 | `cmux browser eval "document.title"` |
| `addscript <url\|js>` | 외부 스크립트 로드 | `cmux browser addscript "https://cdn.example.com/lib.js"` |
| `addstyle <css>` | CSS 스타일 추가 | `cmux browser addstyle "body { outline: 1px solid red; }"` |

### 탭 관리

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `tab list` | 열린 탭 목록 | `cmux browser tab list` |
| `tab new <url>` | 새 탭으로 URL 열기 | `cmux browser tab new https://example.com` |
| `tab switch <id>` | 탭 전환 | `cmux browser tab switch 2` |
| `tab close` | 현재 탭 닫기 | `cmux browser tab close` |

### 세션 상태 관리

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `cookies get` | 쿠키 조회 | `cmux browser cookies get` |
| `storage local get` | 로컬 스토리지 조회 | `cmux browser storage local get` |
| `state save <file>` | 브라우저 상태 저장 | `cmux browser state save /tmp/session.json` |
| `state load <file>` | 브라우저 상태 복원 | `cmux browser state load /tmp/session.json` |

### 디버깅

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `console list` | 콘솔 로그 조회 | `cmux browser console list` |
| `errors list` | 에러 목록 조회 | `cmux browser errors list` |
| `dialog accept` | 다이얼로그 수락 | `cmux browser dialog accept` |

### Surface 지정

여러 브라우저가 열려 있을 때 대상을 지정한다:

```bash
cmux browser --surface surface:2 snapshot --interactive
```

---

## 테스트 워크플로우

### Phase 0: CSP 사전 체크 (MUST)

`cmux browser`는 내부적으로 `eval()`을 사용하므로 CSP 차단이 전면 영향을 준다.
HTTP 헤더와 meta 태그 두 곳을 모두 확인한다:

```bash
# 1. HTTP 응답 헤더 확인
curl -sI <target-url> | grep -i content-security-policy

# 2. meta 태그 CSP 확인 (SPA는 JS 번들에 포함되는 경우가 많음)
cmux browser open <target-url>
cmux browser wait --load-state complete --timeout 10
cmux browser eval 'document.querySelector("meta[http-equiv=\"Content-Security-Policy\"]")?.content || "no meta CSP"'
```

`'unsafe-eval'` 없이 `script-src`가 있으면 ⚠️ eval/click 불가 → Playwright 전환 필요.
두 곳 모두에 CSP가 없거나 `unsafe-eval`이 포함되어 있으면 진행 가능.

### Phase 1: 환경 준비 (SPA Hydration Wait 포함)

```bash
# 1. URL 열기
cmux browser open <target-url>

# 2. SPA Hydration Wait Protocol (위 "Iron Law" 섹션 참조)

# Step 1: 네트워크 레벨 로드 완료 대기
cmux browser wait --load-state complete --timeout 15

# Step 2: SPA 감지 (출력: "true" 또는 "false")
IS_SPA=$(cmux browser eval '!!(window.__NEXT_DATA__||window.__NUXT__||window.__remixContext||window.__SVELTEKIT_DATA__||window.___gatsby||window.__INITIAL_STATE__||window.ng||document.querySelector("[data-reactroot],[data-v-app],[data-server-rendered],[ng-version],[data-svelte-h]"))' 2>/dev/null | tr -d '"' | tr -d ' \n')

# Step 3A: SPA이면 콘텐츠 밀도 대기, 아니면 3초 짧은 대기 (정적 페이지는 즉시 통과)
if [ "$IS_SPA" = "true" ]; then
  cmux browser wait --function 'document.readyState==="complete" && document.body.innerText.length>200 && document.querySelectorAll("a[href],button").length>5 && !document.querySelector("[aria-busy=true],[data-loading=true]")' --timeout 10 || true
else
  cmux browser wait --function 'document.readyState==="complete"' --timeout 3 || true
fi

# 3. Snapshot (결과 검증 필수)
cmux browser snapshot --interactive

# 결과 검증: 링크·헤딩·버튼 개수 확인 (10 미만이면 hydration 미완료)
cmux browser eval 'document.querySelectorAll("a[href],h1,h2,h3,button,nav,article").length'

# 4. eval 동작 확인
cmux browser eval "1+1"
# "2" 출력 시 정상. CSP 차단이면 → Playwright 전환
```

### Phase 2: 시나리오 실행

**예시 — 로그인 폼 테스트:**

```bash
cmux browser navigate /login
cmux browser wait --selector "#email"
cmux browser fill "#email" "test@example.com"
cmux browser fill "#password" "password123"
cmux browser click "button:has-text('로그인')"
cmux browser wait --url "/dashboard"
cmux browser snapshot --interactive
```

**예시 — ReadMe.io SPA 문서 탐색:**

```bash
cmux browser open https://developers.example.com/reference

# Step 1: 로드 대기
cmux browser wait --load-state complete --timeout 15

# Step 2: ReadMe.io 사이드바 렌더링 대기 (Step 3B 패턴)
cmux browser wait --selector "nav.sidebar, .rm-Sidebar, [class*='sidebar']" --timeout 15

# Step 3: Snapshot — 이제 사이드바·본문 포함된 결과가 나옴
cmux browser snapshot --interactive
```

**예시 — API 엔드포인트 목록 추출:**

```bash
cmux browser open https://developers.example.com/reference
cmux browser wait --load-state complete --timeout 15
cmux browser wait --selector "[data-testid='endpoint-list'], .api-endpoints" --timeout 15

# eval로 직접 추출
cmux browser eval "Array.from(document.querySelectorAll('h2,h3')).map(h => h.textContent.trim()).join('\n')"
```

### Phase 3: 검증

```bash
cmux browser is visible --selector "#success-message"
cmux browser get text --selector "#result"
cmux browser url
cmux browser errors list
cmux browser console list
```

### Phase 4: 정리

```bash
cmux browser state save /tmp/test-session.json
cmux browser tab close
```

---

## 에러 핸들링

### Snapshot이 비어 있을 때 — SPA Hydration 재시도

```bash
# 증상: snapshot 결과에 2~5개 노드, 내비게이션·콘텐츠 없음
# 원인: client-side rendering 미완료

# 재시도 1 — 더 구체적인 selector 대기
cmux browser wait --selector "main > section, article, .page-content" --timeout 15
cmux browser snapshot --interactive

# 재시도 2 — 특정 텍스트 출현 대기
cmux browser wait --text "API Reference" --timeout 15
cmux browser snapshot --interactive

# 재시도 3 — eval로 직접 DOM 쿼리
cmux browser eval "Array.from(document.querySelectorAll('a[href]')).map(a => a.textContent + ' → ' + a.href).join('\n')"
```

### 일반적인 실패 패턴

| 증상 | 원인 | 해결 |
|------|------|------|
| Snapshot 빈 트리 | SPA hydration 미완료 | Hydration Wait Protocol 적용 (위 참조) |
| Selector 찾을 수 없음 | 미로드 / 잘못된 selector | `wait --selector` 후 재시도, snapshot으로 DOM 확인 |
| 클릭 미동작 | 요소가 가려져 있음 | `scroll-into-view --selector`, `is visible` 확인 |
| eval 오류 | CSP 차단 | CSP 헤더 확인, Playwright 전환 고려 |
| 타임아웃 | 네트워크 지연 / SPA 렌더링 | `--timeout` 값 증가, Step 3B selector 시도 |
| 텍스트 입력 안 됨 | 포커스 미설정 / readonly | `focus` 후 `fill`, `get attr` 으로 readonly 확인 |
| 다이얼로그 블로킹 | alert/confirm 팝업 | `dialog accept` 또는 `dialog dismiss` |

---

## 실행 규칙

1. **Snapshot 전 항상 SPA Hydration Wait Protocol 실행** (Iron Law)
2. **매 단계마다 상태 확인**: 명령 실행 후 `snapshot --interactive` 또는 `is` 로 결과를 검증한다
3. **대기 우선**: 클릭/입력 전에 반드시 `wait --selector` 또는 `wait --load-state complete`를 사용한다
4. **Snapshot 결과 검증**: 콘텐츠가 실질적으로 포함되어 있는지 확인 후 다음 단계 진행
5. **실패 시 디버깅**: 실패 즉시 `snapshot --interactive` + `console list` + `errors list`로 상태 수집
6. **스크린샷 증거**: 주요 검증 포인트마다 `screenshot --out /tmp/step-N.png` 저장
7. **Surface 구분**: 여러 브라우저가 열려 있으면 Phase 1 시작 시 surface를 변수로 캡처하고 모든 후속 명령에 `--surface $SURFACE` 플래그를 명시한다
   ```bash
   SURFACE="surface:2"
   cmux browser --surface $SURFACE wait --load-state complete --timeout 15
   cmux browser --surface $SURFACE snapshot --interactive
   ```
