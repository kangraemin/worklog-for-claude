#!/bin/bash
# PostToolUse: 세션별 임시 파일에 도구 사용 기록 수집

INPUT=$(cat)

# --- worklog-for-claude start ---
# WORKLOG_TIMING=manual이면 수집 불필요
[ "${WORKLOG_TIMING:-each-commit}" = "manual" ] && exit 0

# 자동 업데이트 체크 (24h throttle, 백그라운드)
if [ -n "${AI_WORKLOG_DIR:-}" ] && [ -f "$AI_WORKLOG_DIR/scripts/update-check.sh" ]; then
  UPDATE_MSG=$(bash "$AI_WORKLOG_DIR/scripts/update-check.sh" 2>/dev/null)
  [ -n "$UPDATE_MSG" ] && echo "$UPDATE_MSG"
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 세션별 임시 수집 파일
COLLECT_DIR="$HOME/.claude/worklogs/.collecting"
mkdir -p "$COLLECT_DIR"
COLLECT_FILE="$COLLECT_DIR/$SESSION_ID.jsonl"

echo "{\"ts\":\"$TIMESTAMP\",\"tool\":\"$TOOL_NAME\",\"input\":$TOOL_INPUT}" >> "$COLLECT_FILE"
# --- worklog-for-claude end ---

exit 0
