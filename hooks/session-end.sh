#!/bin/bash
# SessionEnd: 수집 파일 정리 (워크로그는 stop.sh에서 처리)

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
COLLECT_FILE="$HOME/.claude/worklogs/.collecting/$SESSION_ID.jsonl"

# stop.sh에서 이미 정리했으면 스킵
[ -f "$COLLECT_FILE" ] && rm -f "$COLLECT_FILE"

exit 0
