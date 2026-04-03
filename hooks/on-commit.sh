#!/bin/bash
# PostToolUse (Bash): git commit 감지 시 worklog 기록 요청

# --- worklog-for-claude start ---
command -v jq &>/dev/null || exit 0
[ "${WORKLOG_TIMING:-each-commit}" = "manual" ] && exit 0

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# git commit 이 아니면 스킵 (git push, git pull 등 제외)
# 명령 구문 앞에 위치한 경우만 매칭 (heredoc/문자열 내 오탐 방지)
printf '%s' "$COMMAND" | grep -qE '(^|\n|;|&&|\|\|)\s*git\s+commit(\s|$)' || exit 0

# block 없이 exit — stop.sh가 세션 종료 시 pending 마커를 감지하여 /worklog 실행 요청
exit 0
# --- worklog-for-claude end ---
