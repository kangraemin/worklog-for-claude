---
description: 워크로그 작성
---

# /worklog

로컬 `.claude/rules/worklog-rules.md`가 있으면 그걸, 없으면 `$AI_WORKLOG_DIR/rules/worklog-rules.md`를 따른다.

## 모드 체크

- 사용자가 직접 `/worklog` 호출 시: `WORKLOG_TIMING` 값과 무관하게 항상 실행

## 환경변수 유효성 검사

- `WORKLOG_DEST`가 `notion` 또는 `notion-only`이면:
  - `NOTION_TOKEN` 없으면: "⚠ NOTION_TOKEN 환경변수가 필요합니다. git 모드로 fallback합니다." 출력, `git` 모드로 진행
  - `NOTION_DB_ID` 없으면: "⚠ NOTION_DB_ID 환경변수가 필요합니다. git 모드로 fallback합니다." 출력, `git` 모드로 진행

## 플로우

1. 대화 컨텍스트에서 **사용자 요청사항** 정리
2. `git diff --cached --stat`으로 staged 변경 확인 (없으면 `git diff --stat`으로 unstaged 확인)
3. 변경 내용 분석하여 **작업 내용** 요약
4. **요약 텍스트 생성** (아래 포맷 참조)
5. **`worklog-write.sh` 호출**:
   ```bash
   TMPFILE=$(mktemp)
   cat > "$TMPFILE" <<'EOF'
   <요약 텍스트>
   EOF
   bash "${AI_WORKLOG_DIR}/scripts/worklog-write.sh" "$TMPFILE"
   rm -f "$TMPFILE"
   ```
6. `WORKLOG_GIT_TRACK`이 `true`(기본)이면 `git add .worklogs/`, `false`이면 스킵

## 요약 텍스트 포맷

`WORKLOG_LANG=ko` (기본):

```markdown
### 요청사항
- 사용자가 요청한 내용 (대화 컨텍스트에서 추출)

### 작업 내용
- 어떤 작업을 했는지 간결하게
- 주요 변경점 위주

### 변경 파일
- `파일명`: 이 파일에서 한 작업 한 줄 설명
```

`WORKLOG_LANG=en`:

```markdown
### Request
- What the user asked for (extracted from conversation context)

### Summary
- What was done, concisely
- Key changes

### Changed Files
- `filename`: one-line description
```

## 규칙

- `WORKLOG_LANG` 환경변수에 따라 섹션 헤더 언어 결정 (`ko` 기본, `en` 영어)
- 요청사항/Request는 **사용자 관점**으로 작성 (기술 구현 디테일 X)
- 작업 내용/Summary는 **간결하게** (3줄 이내 권장)
- 토큰 계산, 스냅샷 갱신, Notion 전송은 `worklog-write.sh`가 담당 — 스킬에서 직접 하지 않음
- `~/.claude/worklogs/.snapshot`은 전역 파일이므로 git 추적하지 않음
