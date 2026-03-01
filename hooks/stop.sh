#!/bin/bash
# Stop 훅: 세션 종료 시 커밋/워크로그 필요 여부 확인

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

cd "$CWD" 2>/dev/null || exit 0

# --- ai-worklog start ---
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# --- 커밋 필요 여부 ---
NEED_COMMIT=false
CHANGED=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null | grep -v '^$')
[ -n "$CHANGED" ] && NEED_COMMIT=true

# --- block 메시지 결정 ---
if [ "$NEED_COMMIT" = "true" ]; then
  echo '{"decision":"block","reason":"커밋되지 않은 변경사항이 있습니다. /commit을 실행하세요."}'
fi
# --- ai-worklog end ---

exit 0
