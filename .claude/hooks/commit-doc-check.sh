#!/bin/bash
# PostToolUse(Bash) hook: git commit 감지 → PROJECT.md 업데이트 체크
# Claude Code settings.json의 PostToolUse Bash matcher에 등록

set -euo pipefail

# git commit 명령어가 아니면 스킵
COMMAND="${TOOL_INPUT:-}"
if ! echo "$COMMAND" | grep -q "git commit"; then
    exit 0
fi

# PROJECT.md 없으면 스킵
if [ ! -f "PROJECT.md" ]; then
    exit 0
fi

# git repo 아니면 스킵
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    exit 0
fi

THRESHOLD="${PROJECT_DOC_CHECK_INTERVAL:-5}"

# PROJECT.md 마지막 수정 커밋 hash
LAST_HASH=$(git log -1 --format="%H" -- PROJECT.md 2>/dev/null || echo "")

if [ -z "$LAST_HASH" ]; then
    # PROJECT.md 수정 기록 없음 → 전체 커밋 수
    COMMITS_SINCE=$(git log --oneline 2>/dev/null | wc -l | tr -d ' ')
else
    COMMITS_SINCE=$(git log --oneline "${LAST_HASH}..HEAD" 2>/dev/null | wc -l | tr -d ' ')
fi

if [ "$COMMITS_SINCE" -ge "$THRESHOLD" ]; then
    echo "📝 PROJECT.md 업데이트 필요: 마지막 업데이트 이후 ${COMMITS_SINCE}개 커밋 쌓임. analyze_gaps를 실행해서 반영할 내용 확인을 권장합니다."
fi
