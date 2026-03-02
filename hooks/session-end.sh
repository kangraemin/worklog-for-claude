#!/bin/bash
# SessionEnd: 수집 파일 정리

INPUT=$(cat)

# --- worklog-for-claude start ---
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
COLLECT_FILE="$HOME/.claude/worklogs/.collecting/$SESSION_ID.jsonl"

[ -f "$COLLECT_FILE" ] && rm -f "$COLLECT_FILE"
# --- worklog-for-claude end ---

exit 0
