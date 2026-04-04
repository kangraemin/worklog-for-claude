#!/bin/bash
# Stop hook: 세션 종료 시 미커밋/미기록 작업 감지

# jq 필수
command -v jq &>/dev/null || exit 0

INPUT=$(cat)

# --- worklog-for-claude start ---
# WORKLOG_TIMING=manual이면 스킵
[ "${WORKLOG_TIMING:-stop}" = "manual" ] && exit 0

# 재진입 방지: 이미 stop hook 처리 중이면 통과
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd')
cd "$CWD" 2>/dev/null || exit 0

# git repo가 아니면 통과
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# 1) 미커밋 변경사항 확인 (untracked ??, .worklogs/ 제외)
DIRTY=$(git status --porcelain 2>/dev/null | grep -v '^??' | grep -v ' \.worklogs/' || true)

if [ -n "$DIRTY" ]; then
  jq -n '{
    "decision": "block",
    "reason": "변경사항을 커밋하고 푸시해줘."
  }'
  exit 0
fi

# 2) pending worklog 마커 확인 (세션 내 커밋 후 /worklog 미실행)
PENDING_DIR="$HOME/.claude/worklogs/.pending"
PENDING_INFO=""
if [ -d "$PENDING_DIR" ]; then
  for f in "$PENDING_DIR"/*.json; do
    [ -f "$f" ] || continue
    pcwd=$(jq -r '.project_cwd // ""' "$f" 2>/dev/null)
    if [ "$pcwd" = "$CWD" ]; then
      cmsg=$(jq -r '.commit_msg // ""' "$f" 2>/dev/null | head -1)
      PENDING_INFO="${PENDING_INFO}- ${cmsg}\n"
    fi
  done
fi

if [ -n "$PENDING_INFO" ]; then
  REASON=$(printf "/worklog 스킬을 실행해서 워크로그를 작성해줘.\n\n미처리 커밋:\n%s" "$PENDING_INFO")
  jq -n --arg reason "$REASON" '{"decision": "block", "reason": $reason}'
  exit 0
fi

exit 0
# --- worklog-for-claude end ---
