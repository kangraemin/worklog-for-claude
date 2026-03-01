#!/bin/bash
# Stop 훅: 세션 종료 시 커밋/워크로그 필요 여부 확인

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

cd "$CWD" 2>/dev/null || exit 0

# --- ai-worklog start ---
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

WORKLOG_TIMING="${WORKLOG_TIMING:-each-commit}"
WORKLOG_GIT_TRACK="${WORKLOG_GIT_TRACK:-true}"
COMMIT_TIMING="${COMMIT_TIMING:-session-end}"

# --- 커밋 필요 여부 ---
NEED_COMMIT=false
if [ "$COMMIT_TIMING" = "session-end" ]; then
  CHANGED=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
  NON_WORKLOG=$(echo "$CHANGED" | grep -v '\.worklogs/' | grep -v '^$')
  if [ -n "$NON_WORKLOG" ]; then
    git diff --quiet 2>/dev/null || NEED_COMMIT=true
    git diff --cached --quiet 2>/dev/null || NEED_COMMIT=true
    [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ] && NEED_COMMIT=true
  fi
fi

# --- 워크로그 필요 여부 ---
NEED_WORKLOG=false
if [ "$WORKLOG_TIMING" = "session-end" ]; then
  WORKLOG_FILE="$CWD/.worklogs/$(date +%Y-%m-%d).md"
  [ ! -f "$WORKLOG_FILE" ] && NEED_WORKLOG=true
fi

# --- block 메시지 결정 ---
if [ "$NEED_COMMIT" = "true" ] && [ "$NEED_WORKLOG" = "true" ]; then
  echo '{"decision":"block","reason":"세션 종료 전 /worklog를 실행한 후 /commit을 실행하세요."}'
elif [ "$NEED_COMMIT" = "true" ]; then
  MSG="커밋되지 않은 변경사항이 있습니다. /commit을 실행하세요"
  [ "$WORKLOG_TIMING" = "each-commit" ] && [ "$WORKLOG_GIT_TRACK" = "true" ] && MSG="$MSG (워크로그 포함)."
  echo "{\"decision\":\"block\",\"reason\":\"$MSG\"}"
elif [ "$NEED_WORKLOG" = "true" ]; then
  echo '{"decision":"block","reason":"세션 종료 전 /worklog를 실행하세요."}'
fi
# --- ai-worklog end ---

exit 0
