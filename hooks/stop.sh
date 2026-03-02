#!/bin/bash
# Stop hook: 미커밋 변경사항이 있으면 Claude에게 /finish 실행 지시

INPUT=$(cat)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지: 이미 stop hook으로 계속 진행 중이면 통과
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd')
cd "$CWD" 2>/dev/null || exit 0

# git repo가 아니면 통과
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# --- worklog-for-claude start ---
# 미커밋 변경사항 확인 (.worklogs/ 제외 — 워크로그 아티팩트)
DIRTY=$(git status --porcelain 2>/dev/null | grep -v ' \.worklogs/' || true)

if [ -n "$DIRTY" ]; then
  jq -n '{
    decision: "block",
    reason: "/finish 스킬을 실행해서 커밋, 푸시, 워크로그를 작성해줘."
  }'
else
  exit 0
fi
# --- worklog-for-claude end ---
