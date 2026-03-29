#!/bin/bash
# PostToolUse (Bash): git commit 감지 시 worklog 기록 요청

# --- worklog-for-claude start ---
command -v jq &>/dev/null || exit 0
[ "${WORKLOG_TIMING:-stop}" = "manual" ] && exit 0

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# git commit 이 아니면 스킵 (git push, git pull 등 제외)
# 명령 구문 앞에 위치한 경우만 매칭 (heredoc/문자열 내 오탐 방지)
printf '%s' "$COMMAND" | grep -qE '(^|\n|;|&&|\|\|)\s*git\s+commit(\s|$)' || exit 0

jq -n '{
  "decision": "block",
  "reason": "/worklog 스킬을 실행해서 이번 작업을 워크로그로 기록해줘."
}'
# --- worklog-for-claude end ---
