#!/bin/bash
# Stop 훅: 자동 커밋/워크로그는 settings.json의 prompt type Stop hook이 처리

INPUT=$(cat)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

CWD=$(echo "$INPUT" | jq -r '.cwd')
cd "$CWD" 2>/dev/null || exit 0

# --- ai-worklog start ---
# 자동 커밋/푸시/워크로그는 prompt type Stop hook → /finish 스킬이 처리합니다.
# 이 스크립트는 하위 호환을 위해 유지됩니다.
# --- ai-worklog end ---

exit 0
