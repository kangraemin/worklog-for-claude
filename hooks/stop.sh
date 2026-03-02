#!/bin/bash
# Stop 훅: 작업 완료 시 미커밋 변경사항 자동 커밋

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# 재진입 방지
[ "$STOP_HOOK_ACTIVE" = "true" ] && exit 0

cd "$CWD" 2>/dev/null || exit 0

# --- ai-worklog start ---
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# 미커밋 변경사항 확인
CHANGED=$(git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
CHANGED=$(echo "$CHANGED" | grep -v '^$')
[ -z "$CHANGED" ] && exit 0

# 커밋 규칙 파일 탐색 (우선순위)
RULES_FILE=""
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AI_WORKLOG_DIR="${AI_WORKLOG_DIR:-$HOME/.claude}"

for candidate in \
  "$REPO_ROOT/.claude/rules/git-rules.md" \
  "$AI_WORKLOG_DIR/rules/git-rules.md" \
  "$AI_WORKLOG_DIR/rules/auto-commit-rules.md"; do
  if [ -f "$candidate" ]; then
    RULES_FILE="$candidate"
    break
  fi
done

# claude -p 로 커밋 (CLAUDECODE unset으로 중첩 세션 차단 우회)
if command -v claude &>/dev/null && [ -n "$RULES_FILE" ]; then
  unset CLAUDECODE
  claude --dangerously-skip-permissions -p "$(cat <<PROMPT
$RULES_FILE 를 읽고 그 규칙을 따라서 미커밋 변경사항을 커밋하고 푸시해줘.
.worklogs/ 파일은 같이 staging 해.
PROMPT
)" 2>/dev/null || true
elif command -v claude &>/dev/null; then
  unset CLAUDECODE
  claude --dangerously-skip-permissions -p "$(cat <<'PROMPT'
미커밋 변경사항을 커밋하고 푸시해줘.
규칙:
- type 영어 (feat/fix/refactor/chore/docs), 설명 한글, 50자 이내
- 파일 개별 git add (git add . 금지)
- .worklogs/ 파일은 같이 staging 해
- HEREDOC으로 커밋
- 커밋 후 push
PROMPT
)" 2>/dev/null || true
fi
# --- ai-worklog end ---

exit 0
