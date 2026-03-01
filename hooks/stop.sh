#!/bin/bash
# Stop 훅: WORKLOG_TIMING=session-end 시 워크로그 미작성이면 block

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

cd "$CWD" 2>/dev/null || exit 0

# 타이밍 설정 읽기 (기본값)
WORKLOG_TIMING="${WORKLOG_TIMING:-each-commit}"

# --- 워크로그 필요 여부 ---
if [ "$WORKLOG_TIMING" = "session-end" ]; then
  WORKLOG_FILE="$CWD/.worklogs/$(date +%Y-%m-%d).md"
  if [ ! -f "$WORKLOG_FILE" ]; then
    echo '{"decision":"block","reason":"세션 종료 전 /worklog를 실행하세요."}'
    exit 0
  fi
fi

exit 0
