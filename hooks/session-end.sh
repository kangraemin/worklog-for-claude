#!/bin/bash
# SessionEnd: 수집 파일 정리

INPUT=$(cat)

# --- ai-worklog start ---
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
COLLECT_FILE="$HOME/.claude/worklogs/.collecting/$SESSION_ID.jsonl"

[ -f "$COLLECT_FILE" ] && rm -f "$COLLECT_FILE"
# --- ai-worklog end ---

exit 0
