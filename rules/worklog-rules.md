# Worklog Rules

## 언어 (`WORKLOG_LANG`)

| 값 | 동작 |
|---|---|
| `ko` | 섹션 헤더를 한국어로 작성 (기본): 요청사항, 작업 내용, 변경 파일, 토큰 사용량 |
| `en` | 섹션 헤더를 영어로 작성: Request, Summary, Changed Files, Token Usage |

설치 시 언어 선택으로 자동 설정됨.

## 생성 시점 (`WORKLOG_TIMING`)

| 값 | 동작 |
|---|---|
| `each-commit` | git post-commit hook이 커밋마다 자동 작성 (기본) |
| `manual` | `/worklog` 직접 실행할 때만 작성 |

## 저장 대상 (`WORKLOG_DEST`)

| 값 | 동작 |
|---|---|
| `git` | `.worklogs/YYYY-MM-DD.md`에 저장, WORKLOG_GIT_TRACK에 따라 git 추적 |
| `notion` | 로컬 저장 + Notion DB에 엔트리 생성 (`both`와 동일, 하위 호환) |
| `notion-only` | Notion에만 기록, 로컬 파일 없음 |

### 통합 모드 (WORKLOG_DEST + WORKLOG_GIT_TRACK 조합)

| 모드 | WORKLOG_DEST | WORKLOG_GIT_TRACK | 설명 |
|------|-------------|-------------------|------|
| `notion-only` | `notion-only` | `false` | Notion에만 기록 (로컬 파일 없음) |
| `git` | `git` | `true` | 파일만, git 추적 |
| `git-ignore` | `git` | `false` | 파일만, git 미추적 |
| `both` | `notion` | `true` | 파일 + Notion (기본) |

- `NOTION_TOKEN`: `AI_WORKLOG_DIR/.env` 또는 `~/.claude/.env`에 설정
- `NOTION_DB_ID`: `settings.json` env에 설정
- `notion-worklog.sh`가 `.env`를 자동 source하므로 별도 export 불필요
- Notion 전송 실패 시 로컬 저장은 유지, 에러 메시지 출력
- **`notion-only` 모드**: 로컬 파일 write 스킵. 스냅샷(`~/.claude/worklogs/.snapshot`)은 유지.
- Content 본문은 마크다운 → Notion 블록 자동 변환 (`###` → heading_3, `- ` → bulleted_list_item)
- Notion 페이지 아이콘: 📖 (notion-worklog.sh에서 자동 설정)
- **Notion DB 컬럼**: Title, Date, Project, Tokens, Cost, Duration, Model
- **Notion 구조: 작업별 개별 행**
  - Title: 작업 내용 한 줄 요약
  - Content (페이지 본문): 워크로그 상세 (요청사항, 작업내용, 변경파일, 토큰)
  - Cost: 소수점 3자리 반올림, 이번 작업 비용
  - Duration: 이번 작업 소요 시간(분)
  - Model: 해당 세션 모델

## Git 추적 (`WORKLOG_GIT_TRACK`)

| 값 | 동작 |
|---|---|
| `true` | `.worklogs/`를 git add (기본) |
| `false` | `.worklogs/`를 git add하지 않음 |

## 모드 체크

- `WORKLOG_TIMING=manual`이면 `/worklog` 스킬 시작 시 "워크로그 비활성화 상태" 출력 후 종료

## 저장 위치

- `<프로젝트>/.worklogs/YYYY-MM-DD.md` — 날짜별 단일 파일, append
- `~/.claude/worklogs/.snapshot` — 토큰/시간 스냅샷, 전역 단일 파일 (git 추적 안 함)

## 엔트리 포맷

```markdown
## HH:MM

### 요청사항
- 사용자 요청

### 작업 내용
- 작업 요약 (3줄 이내)

### 변경 파일
- `파일명`: 한 줄 설명

### 토큰 사용량
- 모델: claude-opus-4-6
- 이번 작업: $N.NNN
```

post-commit hook auto fallback: `## HH:MM (auto)` + 변경 파일 목록만 (`claude -p` 실패 시).

## 토큰 delta 계산

스냅샷: `{"timestamp":UNIX}`

1. `~/.claude/worklogs/.snapshot` 읽기 (없으면 timestamp=0)
2. 토큰/비용 = `python3 "${AI_WORKLOG_DIR}/scripts/token-cost.py" <스냅샷_timestamp> <프로젝트_cwd>`
   - 출력: `토큰수,비용` (프로젝트 JSONL 직접 파싱, 다른 프로젝트 오염 없음)
3. 소요 시간 = `python3 "${AI_WORKLOG_DIR}/scripts/duration.py" <스냅샷_timestamp> <프로젝트_cwd>`
   - 출력: `초,분` → 분 값 사용. 실제 Claude 작업 시간 (벽시계 시간 아님)
4. 워크로그 작성 후 스냅샷 갱신: `echo '{"timestamp":NOW}' > ~/.claude/worklogs/.snapshot`

- 스냅샷 없으면 timestamp=0으로 전체값 계산 후 생성
- JSONL 파싱 실패 시 "데이터 없음"

## 아키텍처

모든 워크로그 작성은 `scripts/worklog-write.sh`를 통해 수행:

- **each-commit**: `git post-commit hook` → `claude -p`로 요약 생성 → `worklog-write.sh`
- **manual**: `/worklog` 스킬 → 대화 컨텍스트에서 요약 생성 → `worklog-write.sh`

`worklog-write.sh`가 토큰 계산, 파일 저장, Notion 전송, 스냅샷 갱신을 모두 담당.

## 제한

- post-commit hook은 항상 `exit 0` (워크로그 실패 → 커밋 차단 금지)
- hook chaining: 레포별 기존 post-commit hook은 `.git/hooks/post-commit.local`로 보존/실행
