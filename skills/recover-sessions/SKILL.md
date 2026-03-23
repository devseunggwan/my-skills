---
name: recover-sessions
description: Claude Code 세션 일괄 복구. 전원 손실/tmux 중단 후 최근 세션을 스캔하여 Ghostty 탭 + tmux 2분할로 복구합니다. Triggers on "recover", "세션 복구", "session recovery", "전원 복구".
---

# Recover Sessions

## Overview

전원 손실이나 tmux 세션 중단 후 Claude Code 세션을 일괄 복구합니다.

**Core principle:** Claude Code 대화는 디스크에 안전하게 저장되어 있다. 복구 = 저장된 세션을 찾아서 tmux에 배치하는 것.

## When to Use

- 맥 전원이 꺼진 후 Claude Code 세션 복구가 필요할 때
- tmux 서버가 죽어서 모든 세션이 날아갔을 때
- 재부팅 후 이전 작업 세션을 복원하고 싶을 때
- "recover", "세션 복구", "session recovery", "전원 복구"

## Prerequisites

- `~/.local/bin/claude-recover` 스크립트가 설치되어 있어야 함
- tmux가 설치되어 있어야 함 (`brew install tmux`)
- Ghostty 터미널 사용 (탭 기반 워크플로우)

## Process

### Step 1: 스크립트 존재 확인

```bash
which claude-recover || echo "NOT INSTALLED"
```

스크립트가 없으면 사용자에게 안내:

> `claude-recover` 스크립트가 설치되어 있지 않습니다.
> 설치가 필요합니다. 설치를 진행할까요?

설치가 필요한 경우 `~/.local/bin/claude-recover` 에 스크립트를 생성하고 `chmod +x` 를 실행합니다.

### Step 2: 복구 대상 스캔

사용자에게 복구 범위를 확인:

```
어느 기간의 세션을 복구할까요?
1. 최근 1일 (기본)
2. 최근 3일
3. 최근 7일
4. 직접 지정
```

선택 후 스캔 실행:

```bash
claude-recover --list --days <N>
```

출력을 사용자에게 보여주고, 복구할 세션을 확인받습니다.

### Step 3: tmux 세션 생성

사용자가 복구를 확인하면:

```bash
claude-recover --days <N>
```

이 명령은:
1. 최근 세션을 스캔 (schedule/auto 세션 자동 필터링)
2. 2개씩 페어링하여 tmux 세션 생성 (`cr-1`, `cr-2`, ...)
3. 각 tmux 세션: 세로 2분할, 상단/하단에 `claude --resume <session-id>` 배치

### Step 4: Ghostty 탭 분배 안내

tmux 세션 생성 후 사용자에게 안내:

```
═══════════════════════════════════════════════
 tmux 세션이 생성되었습니다.

 각 Ghostty 탭(Cmd+T)에서 다음을 실행하세요:

   tmux a -t cr-1
   tmux a -t cr-2
   tmux a -t cr-3
   ...

 또는 자동으로 Ghostty 윈도우 열기:
   claude-recover --days <N> --windows
═══════════════════════════════════════════════
```

### Step 5: 검증

복구 후 상태 확인:

```bash
tmux ls 2>/dev/null | grep "^cr-"
```

## 모드 레퍼런스

| 모드 | 명령 | 동작 |
|------|------|------|
| 조회 | `claude-recover --list --days N` | 복구 대상만 출력 (tmux 미생성) |
| 생성 | `claude-recover --days N` | tmux 세션 생성 + attach 안내 |
| 자동 attach | `claude-recover --days N --attach` | tmux 생성 후 cr-1에 자동 attach |
| 자동 윈도우 | `claude-recover --days N --windows` | Ghostty 윈도우로 모든 세션 열기 |

## 세션 식별 방법

스크립트는 다음 기준으로 세션을 식별합니다:

- **경로**: jsonl 내부의 `progress.cwd` 필드에서 실제 프로젝트 경로 추출
- **내용**: 첫 번째 user 메시지 (`type=user`, `message.content`)로 세션 목적 표시
- **필터링**: 50K 이하 세션 + 알려진 schedule 패턴 ("SLA deep analysis", "Collect today" 등) 자동 제외
- **크기**: 파일 크기가 클수록 대화량이 많은 중요 세션

## 예방: 세션 네이밍 습관화

복구보다 중요한 것은 예방입니다. 세션 시작 시 항상 이름을 붙이세요:

```bash
claude --name "hub-700-feat-xyz"
claude --name "dag-v3-kakao-moment"
```

이름이 있으면 `claude --resume "hub-700"` 으로 즉시 복구 가능합니다.

## Troubleshooting

| 증상 | 원인 | 해결 |
|------|------|------|
| "복구할 세션이 없습니다" | 기간 내 세션 없음 | `--days` 값 늘리기 |
| tmux 세션 생성 실패 | tmux 서버 미실행 | tmux가 설치되어 있는지 확인 |
| 잘못된 경로로 세션 시작 | cwd 추출 실패 | jsonl 파일 내 progress.cwd 확인 |
| Ghostty 윈도우 안 열림 | Ghostty 미실행 | Ghostty를 먼저 실행한 뒤 `--windows` 사용 |

## Integration

**워크플로우 위치:** 시스템 복구 시점 (다른 스킬보다 먼저 실행)

```
[전원 복구 / 재부팅] → [recover-sessions] → [일상 작업 재개]
```
