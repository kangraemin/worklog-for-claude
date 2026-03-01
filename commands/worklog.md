---
description: 워크로그 작성
---

# /worklog

로컬 `.claude/rules/worklog-rules.md`가 있으면 그걸, 없으면 `$AI_WORKLOG_DIR/rules/worklog-rules.md`를 따른다.

## 모드 체크

- `/commit` 플로우에서 호출 시: `WORKLOG_TIMING=each-commit`인 경우에만 실행, 아니면 스킵
- 사용자가 직접 `/worklog` 호출 시: `WORKLOG_TIMING` 값과 무관하게 항상 실행

## 환경변수 유효성 검사

- `WORKLOG_DEST`가 `notion` 또는 `notion-only`이면:
  - `NOTION_TOKEN` 없으면: "⚠ NOTION_TOKEN 환경변수가 필요합니다. git 모드로 fallback합니다." 출력, `git` 모드로 진행
  - `NOTION_DB_ID` 없으면: "⚠ NOTION_DB_ID 환경변수가 필요합니다. git 모드로 fallback합니다." 출력, `git` 모드로 진행

## 플로우

1. `git diff --cached --stat`으로 staged 변경 확인 (없으면 `git diff --stat`으로 unstaged 확인)
2. 대화 컨텍스트에서 **사용자 요청사항** 정리
3. 변경 내용 분석하여 **작업 내용** 요약
4. **토큰/시간 계산** (아래 참조)
5. **로컬 파일 저장** (`WORKLOG_DEST=notion-only`이면 스킵, 그 외는 항상 실행):
   - `.worklogs/YYYY-MM-DD.md`에 엔트리 append
6. **Notion 전송** (`WORKLOG_DEST=notion` 또는 `notion-only`일 때만):
   - 프로젝트명 = `basename $(git rev-parse --show-toplevel)`
   - **Title**: 작업 내용 한 줄 요약 (시간 포함하지 않음)
   - **Content**: 워크로그 상세 내용 (요청사항, 작업 내용, 변경 파일, 토큰 사용량) — git 워크로그와 동일 수준
   - **비용은 소숫점 그대로 전달** (반올림 금지)
   - 실행:
     ```bash
     bash "${AI_WORKLOG_DIR}/scripts/notion-worklog.sh" \
       "<작업 내용 한 줄 요약>" \
       "YYYY-MM-DD" \
       "<프로젝트명>" \
       <비용_delta (소수점 3자리 반올림)> \
       <소요시간_분> \
       "<모델명 (예: claude-opus-4-6)>" \
       <토큰_delta (정수)> \
       "YYYY-MM-DDTHH:MM:00+09:00" \
       "<워크로그 전체 본문 (요청사항 + 작업내용 + 변경파일 + 토큰)>"
     ```
   - 성공 시 "Notion 전송 완료" 출력
   - 실패 시 "Notion 전송 실패: (에러)" 출력, 로컬 저장은 유지
7. **스냅샷 갱신** (`.worklogs/.snapshot`)
8. `WORKLOG_GIT_TRACK`이 `true`(기본)이면 `git add .worklogs/`, `false`이면 스킵

## 토큰/시간 계산

### 스냅샷 파일: `<프로젝트>/.worklogs/.snapshot`

```json
{
  "timestamp": 1740100000,
  "totalTokens": 29760365,
  "totalCost": 17.87
}
```

### 계산 순서

1. `date +%s`로 현재 unix timestamp 가져오기
2. `ccusage session --json`으로 현재 세션 토큰 수집 (없으면 `npx ccusage@latest session --json`)
3. `cat .worklogs/.snapshot`으로 이전 스냅샷 읽기
4. **소요 시간 계산** (실제 Claude 작업 시간):
   ```bash
   python3 "${AI_WORKLOG_DIR}/scripts/duration.py" <스냅샷_timestamp> <프로젝트_cwd>
   # 출력: 초,분  (예: 584.9,10)
   ```
   - 프로젝트_cwd는 현재 프로젝트의 루트 경로
5. 토큰/비용 delta 계산:
   - **토큰 delta** = 현재 totalTokens - 스냅샷 totalTokens
   - **비용 delta** = 현재 totalCost - 스냅샷 totalCost
6. 워크로그에 delta 값 기록
7. 스냅샷 갱신: `echo '{"timestamp":NOW,"totalTokens":NOW,"totalCost":NOW}' > .worklogs/.snapshot`

스냅샷이 없으면 (첫 실행) delta 대신 전체값 표시하고 스냅샷 생성.

### 중요

- 소요 시간은 **JSONL의 durationMs 합산**으로 계산한다. 벽시계 시간(wall clock) 아님.
- 스냅샷 갱신은 **워크로그 작성 후** 반드시 실행한다.

## 엔트리 포맷

```markdown
---

## HH:MM

### 요청사항
- 사용자가 요청한 내용 (대화 컨텍스트에서 추출)

### 작업 내용
- 어떤 작업을 했는지 간결하게
- 주요 변경점 위주

### 변경 파일
- `파일명`: 이 파일에서 한 작업 한 줄 설명
- `파일명`: 이 파일에서 한 작업 한 줄 설명

### 토큰 사용량
- 모델: claude-opus-4-6
- 이번 작업: $1.234
```

## 규칙

- 파일이 없으면 헤더(`# Worklog: <프로젝트> — YYYY-MM-DD`) 먼저 생성
- 요청사항은 **사용자 관점**으로 작성 (기술 구현 디테일 X)
- 작업 내용은 **간결하게** (3줄 이내 권장)
- ccusage 실패 시 "데이터 없음"으로 표기
- `.worklogs/.snapshot`은 git 추적하지 않음 (`.gitignore`에 추가)
