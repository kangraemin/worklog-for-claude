#!/bin/bash
# git post-commit hook — 커밋 후 자동 워크로그 작성
# install.sh에서 git hooks 경로에 설치됨 (전역 또는 로컬)

# ── Claude Code 세션 내에서는 스킵 ───────────────────────────────────────────
# 세션 내에서는 /finish 또는 /commit 스킬이 워크로그를 처리한다.
# post-commit hook은 터미널에서 직접 git commit 할 때만 동작.
[ -n "${CLAUDECODE:-}" ] && exit 0

# ── WORKLOG_TIMING 체크 ──────────────────────────────────────────────────────
# manual이면 스킵 (each-commit이 기본)
[ "${WORKLOG_TIMING:-each-commit}" = "manual" ] && exit 0

# ── hook chaining: 기존 레포 hook 먼저 실행 ──────────────────────────────────
# core.hooksPath로 전역 설치 시, 레포별 .git/hooks/post-commit이 무시되므로
# 여기서 명시적으로 실행해준다.
REPO_HOOK="$(git rev-parse --git-dir 2>/dev/null)/hooks/post-commit.local"
[ -x "$REPO_HOOK" ] && "$REPO_HOOK"

# ── AI_WORKLOG_DIR 탐색 ─────────────────────────────────────────────────────
AI_WORKLOG_DIR="${AI_WORKLOG_DIR:-$HOME/.claude}"
WRITE_SCRIPT="$AI_WORKLOG_DIR/scripts/worklog-write.sh"

if [ ! -f "$WRITE_SCRIPT" ]; then
  # ai-worklog 미설치
  exit 0
fi

# ── 환경변수 로드 ────────────────────────────────────────────────────────────
# settings.json의 env를 읽어서 export
SETTINGS_FILE="$AI_WORKLOG_DIR/settings.json"
if [ -f "$SETTINGS_FILE" ]; then
  eval "$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$SETTINGS_FILE'))
    for k, v in cfg.get('env', {}).items():
        print(f'export {k}=\"{v}\"')
except:
    pass
" 2>/dev/null || true)"
fi

# ── 컨텍스트 수집 ────────────────────────────────────────────────────────────
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
LANG_OPT="${WORKLOG_LANG:-ko}"

# 변경 파일 목록: 파일명만 추출
CHANGED_FILES=$(git diff HEAD~1 HEAD --name-only 2>/dev/null || echo "")

# ── .worklogs/ 만 변경된 커밋이면 스킵 (무한루프 방지) ────────────────────────
NON_WORKLOG=$(echo "$CHANGED_FILES" | grep -v '^\.worklogs/' | grep -v '^$')
[ -z "$NON_WORKLOG" ] && exit 0

# ── claude -p 로 요약 생성 시도 ──────────────────────────────────────────────
# 터미널에서 직접 git commit 할 때만 도달 (CLAUDECODE 미설정)
SUMMARY=""
if command -v claude &>/dev/null; then
  if [ "$LANG_OPT" = "en" ]; then
    PROMPT="Based on this git commit, write a brief worklog entry.

Commit message: $COMMIT_MSG

Changed files:
$CHANGED_FILES

Write in this EXACT format (no code fences, no extra text):
### Request
- What was requested (infer from commit message)

### Summary
- What was done (2-3 lines max, be specific about the actual changes)

### Changed Files
- \`filename\`: one-line description of what changed in this file
(Write a description for EACH file listed above)
"
  else
    PROMPT="이 git 커밋을 기반으로 워크로그 엔트리를 작성해줘.

커밋 메시지: $COMMIT_MSG

변경 파일:
$CHANGED_FILES

아래 형식으로 정확히 작성 (코드 펜스 없이, 추가 텍스트 없이):
### 요청사항
- 커밋 메시지에서 요청 의도를 추론하여 작성

### 작업 내용
- 실제 변경한 내용을 구체적으로 2-3줄 이내 작성

### 변경 파일
- \`파일명\`: 이 파일에서 변경한 내용 한 줄 설명
(위에 나열된 모든 파일에 대해 각각 설명을 작성)
"
  fi

  SUMMARY=$(claude -p "$PROMPT" 2>/dev/null) || SUMMARY=""
fi

# ── fallback: auto 포맷 ─────────────────────────────────────────────────────
if [ -z "$SUMMARY" ]; then
  if [ "$LANG_OPT" = "en" ]; then
    SUMMARY="### Summary
- $COMMIT_MSG

### Changed Files
$(echo "$CHANGED_FILES" | grep -v '^$' | sed 's|.*|&: (auto)|' | sed 's/^/- `/' | sed 's/: /`: /')"
  else
    SUMMARY="### 작업 내용
- $COMMIT_MSG

### 변경 파일
$(echo "$CHANGED_FILES" | grep -v '^$' | sed 's|.*|&: (auto)|' | sed 's/^/- `/' | sed 's/: /`: /')"
  fi
fi

# ── worklog-write.sh 호출 ────────────────────────────────────────────────────
TMPFILE=$(mktemp)
echo "$SUMMARY" > "$TMPFILE"

bash "$WRITE_SCRIPT" "$TMPFILE" 2>/dev/null || true

rm -f "$TMPFILE"
exit 0
