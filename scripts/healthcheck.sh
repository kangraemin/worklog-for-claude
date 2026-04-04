#!/bin/bash
# worklog-for-claude 건강 진단
# Usage: healthcheck.sh [--json]
#   --json: JSON 출력 (e2e 테스트용)
#   기본: 사람이 읽기 좋은 텍스트 출력
#
# 환경변수:
#   AI_WORKLOG_DIR: 설치 디렉토리 (기본: ~/.claude)
#   HEALTHCHECK_SETTINGS: settings.json 경로 오버라이드 (테스트용)
#   HEALTHCHECK_LOCAL_SETTINGS: 로컬 settings.json 경로 오버라이드 (테스트용)
#   HEALTHCHECK_SKIP_VERSION_CHECK: 1이면 GitHub API 호출 스킵

set -euo pipefail

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

AI_WORKLOG_DIR="${AI_WORKLOG_DIR:-$HOME/.claude}"
JSON_MODE=false

for arg in "$@"; do
  case $arg in
    --json) JSON_MODE=true ;;
  esac
done

# ── 설정 파일 경로 ──────────────────────────────────────────────────────────
SETTINGS="${HEALTHCHECK_SETTINGS:-$AI_WORKLOG_DIR/settings.json}"
LOCAL_SETTINGS="${HEALTHCHECK_LOCAL_SETTINGS:-}"

# ── JSON 결과 수집 ──────────────────────────────────────────────────────────
_result=""
_add_result() {
  local key="$1" val="$2"
  if [ -n "$_result" ]; then _result="$_result, "; fi
  _result="$_result\"$key\": $val"
}

_issues=()
_add_issue() { _issues+=("$1"); }

# ── 1. settings.json 파싱 ──────────────────────────────────────────────────
if [ ! -f "$SETTINGS" ]; then
  if [ "$JSON_MODE" = true ]; then
    echo "{\"status\": \"not_installed\", \"error\": \"settings.json not found\"}"
  else
    echo "❌ worklog-for-claude 미설치 (settings.json 없음)"
    echo "   설치: bash install.sh"
  fi
  exit 1
fi

# JSON 유효성 검사
if ! $PYTHON -c "import json; json.load(open('$SETTINGS'))" 2>/dev/null; then
  if [ "$JSON_MODE" = true ]; then
    echo "{\"status\": \"error\", \"error\": \"invalid JSON in settings.json\"}"
  else
    echo "❌ settings.json 파싱 에러 (유효하지 않은 JSON)"
  fi
  exit 1
fi

# 글로벌 + 로컬 머지
MERGED_ENV=$($PYTHON -c "
import json, sys, os

settings_path = sys.argv[1]
local_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ''

with open(settings_path) as f:
    cfg = json.load(f)

env = dict(cfg.get('env', {}))

if local_path and os.path.isfile(local_path):
    with open(local_path) as f:
        local_cfg = json.load(f)
    env.update(local_cfg.get('env', {}))

json.dump(env, sys.stdout)
" "$SETTINGS" "$LOCAL_SETTINGS" 2>/dev/null)

# ── 2. 파일 무결성 ─────────────────────────────────────────────────────────
EXPECTED_FILES=(
  "scripts/worklog-write.sh"
  "scripts/notion-worklog.sh"
  "scripts/duration.py"
  "scripts/token-cost.py"
  "scripts/update-check.sh"
  "hooks/worklog.sh"
  "hooks/on-commit.sh"
  "hooks/session-end.sh"
  "hooks/post-commit.sh"
  "hooks/commit-doc-check.sh"
  "hooks/stop.sh"
  "git-hooks/post-commit"
  "commands/worklog.md"
  "commands/worklog-config.md"
  "commands/worklog-update.md"
  "commands/worklog-migrate.md"
  "rules/worklog-rules.md"
)

TOTAL_FILES=${#EXPECTED_FILES[@]}
FOUND_FILES=0
MISSING_FILES=()
for f in "${EXPECTED_FILES[@]}"; do
  if [ -f "$AI_WORKLOG_DIR/$f" ]; then
    FOUND_FILES=$((FOUND_FILES + 1))
  else
    MISSING_FILES+=("$f")
  fi
done

_add_result "files_total" "$TOTAL_FILES"
_add_result "files_found" "$FOUND_FILES"
if [ ${#MISSING_FILES[@]} -gt 0 ]; then
  missing_json=$(printf '%s\n' "${MISSING_FILES[@]}" | $PYTHON -c "import json,sys; print(json.dumps(sys.stdin.read().strip().split('\n')))")
  _add_result "files_missing" "$missing_json"
  _add_issue "파일 누락: ${MISSING_FILES[*]}"
fi

# ── 3. Hook 등록 상태 ──────────────────────────────────────────────────────
# hook별 (filename, event, matcher_or_empty)
HOOK_CHECKS=(
  "worklog.sh:PostToolUse:"
  "on-commit.sh:PostToolUse:Bash"
  "commit-doc-check.sh:PostToolUse:"
  "update-check.sh:SessionStart:"
  "session-end.sh:SessionEnd:"
  "stop.sh:Stop:"
)

HOOKS_TOTAL=${#HOOK_CHECKS[@]}
HOOKS_FOUND=0
HOOKS_MISSING=()
HOOKS_FILE_MISSING=()

for entry in "${HOOK_CHECKS[@]}"; do
  IFS=':' read -r hook_file hook_event hook_matcher <<< "$entry"

  # settings.json에서 해당 hook 등록 여부 확인
  registered=$($PYTHON -c "
import json, sys
sf = sys.argv[1]
hook_file = sys.argv[2]
event = sys.argv[3]

with open(sf) as f:
    cfg = json.load(f)

hooks = cfg.get('hooks', {})
entries = hooks.get(event, [])
for group in entries:
    for h in group.get('hooks', []):
        cmd = h.get('command', '')
        if hook_file in cmd:
            print('found')
            sys.exit(0)
print('missing')
" "$SETTINGS" "$hook_file" "$hook_event" 2>/dev/null)

  if [ "$registered" = "found" ]; then
    HOOKS_FOUND=$((HOOKS_FOUND + 1))
    # 등록됐는데 파일이 없는 경우
    if [ ! -f "$AI_WORKLOG_DIR/hooks/$hook_file" ] && [ ! -f "$AI_WORKLOG_DIR/scripts/$hook_file" ]; then
      HOOKS_FILE_MISSING+=("$hook_file")
    fi
  else
    HOOKS_MISSING+=("$hook_file")
  fi
done

_add_result "hooks_total" "$HOOKS_TOTAL"
_add_result "hooks_found" "$HOOKS_FOUND"
if [ ${#HOOKS_MISSING[@]} -gt 0 ]; then
  missing_json=$(printf '%s\n' "${HOOKS_MISSING[@]}" | $PYTHON -c "import json,sys; print(json.dumps(sys.stdin.read().strip().split('\n')))")
  _add_result "hooks_missing" "$missing_json"
  _add_issue "Hook 미등록: ${HOOKS_MISSING[*]}"
fi
if [ ${#HOOKS_FILE_MISSING[@]} -gt 0 ]; then
  missing_json=$(printf '%s\n' "${HOOKS_FILE_MISSING[@]}" | $PYTHON -c "import json,sys; print(json.dumps(sys.stdin.read().strip().split('\n')))")
  _add_result "hooks_file_missing" "$missing_json"
  _add_issue "Hook 파일 누락: ${HOOKS_FILE_MISSING[*]}"
fi

# ── 4. Git Hook ────────────────────────────────────────────────────────────
GIT_HOOK_STATUS="ok"
GIT_HOOK_DETAIL=""

HOOKS_PATH="${HEALTHCHECK_GIT_HOOKS_PATH:-$(git config --global core.hooksPath 2>/dev/null || echo "")}"

if [ -z "$HOOKS_PATH" ]; then
  GIT_HOOK_STATUS="missing"
  GIT_HOOK_DETAIL="core.hooksPath 미설정"
  _add_issue "Git Hook: core.hooksPath 미설정"
elif [ ! -f "$HOOKS_PATH/post-commit" ]; then
  GIT_HOOK_STATUS="warn"
  GIT_HOOK_DETAIL="post-commit 파일 없음"
  _add_issue "Git Hook: post-commit 파일 없음 ($HOOKS_PATH)"
elif ! grep -q "post-commit.sh" "$HOOKS_PATH/post-commit" 2>/dev/null; then
  GIT_HOOK_STATUS="warn"
  GIT_HOOK_DETAIL="post-commit 내용 불일치"
  _add_issue "Git Hook: post-commit이 post-commit.sh로 위임하지 않음"
elif [ ! -x "$HOOKS_PATH/post-commit" ]; then
  GIT_HOOK_STATUS="warn"
  GIT_HOOK_DETAIL="post-commit 실행 권한 없음"
  _add_issue "Git Hook: post-commit 실행 권한 없음"
fi

_add_result "git_hook" "\"$GIT_HOOK_STATUS\""
[ -n "$GIT_HOOK_DETAIL" ] && _add_result "git_hook_detail" "\"$GIT_HOOK_DETAIL\""

# ── 5. MCP 서버 ────────────────────────────────────────────────────────────
MCP_STATUS=$($PYTHON -c "
import json, sys
sf = sys.argv[1]
with open(sf) as f:
    cfg = json.load(f)
servers = cfg.get('mcpServers', {})
wl = servers.get('worklog-for-claude')
if wl is None:
    print('missing')
else:
    cmd = wl.get('command', '')
    args = wl.get('args', [])
    full = cmd + ' ' + ' '.join(args) if args else cmd
    if 'worklog-for-claude' in full:
        print('ok')
    else:
        print('mismatch')
" "$SETTINGS" 2>/dev/null || echo "missing")

_add_result "mcp" "\"$MCP_STATUS\""
if [ "$MCP_STATUS" = "missing" ]; then
  _add_issue "MCP 서버: worklog-for-claude 미등록"
elif [ "$MCP_STATUS" = "mismatch" ]; then
  _add_issue "MCP 서버: command 불일치"
fi

# ── 6. 환경변수 ────────────────────────────────────────────────────────────
ENV_ISSUES=()

_get_env_val() {
  $PYTHON -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get(sys.argv[2],''))" "$MERGED_ENV" "$1" 2>/dev/null
}

_check_env() {
  local key="$1" required="$2" label="$3"
  local val=$(_get_env_val "$key")
  if [ -z "$val" ]; then
    if [ "$required" = "required" ]; then
      ENV_ISSUES+=("$label")
    elif [ "$required" = "warn" ]; then
      ENV_ISSUES+=("$label (경고)")
    fi
  fi
}

WORKLOG_TIMING=$(_get_env_val "WORKLOG_TIMING")
WORKLOG_DEST=$(_get_env_val "WORKLOG_DEST")

_check_env "WORKLOG_TIMING" "required" "WORKLOG_TIMING"
_check_env "WORKLOG_DEST" "required" "WORKLOG_DEST"
_check_env "WORKLOG_LANG" "warn" "WORKLOG_LANG"
_check_env "AI_WORKLOG_DIR" "warn" "AI_WORKLOG_DIR"

# Notion 관련: dest에 notion이 포함될 때만 필수
NEEDS_NOTION=false
if [ "$WORKLOG_DEST" != "missing" ] && [ "$WORKLOG_DEST" != "git" ]; then
  NEEDS_NOTION=true
fi

if [ "$NEEDS_NOTION" = true ]; then
  _check_env "NOTION_DB_ID" "required" "NOTION_DB_ID" >/dev/null

  # .env 파일에서 NOTION_TOKEN 확인
  ENV_FILE="$AI_WORKLOG_DIR/.env"
  if [ ! -f "$ENV_FILE" ]; then
    ENV_ISSUES+=("NOTION_TOKEN (.env 파일 없음)")
  elif ! grep -q "NOTION_TOKEN" "$ENV_FILE" 2>/dev/null; then
    ENV_ISSUES+=("NOTION_TOKEN")
  fi
fi

ENV_STATUS="ok"
if [ ${#ENV_ISSUES[@]} -gt 0 ]; then
  ENV_STATUS="warn"
  env_json=$(printf '%s\n' "${ENV_ISSUES[@]}" | $PYTHON -c "import json,sys; print(json.dumps(sys.stdin.read().strip().split('\n')))")
  _add_result "env_issues" "$env_json"
  _add_issue "환경변수: ${ENV_ISSUES[*]}"
fi
_add_result "env" "\"$ENV_STATUS\""

# ── 7. 버전 ────────────────────────────────────────────────────────────────
VERSION_FILE="$AI_WORKLOG_DIR/.version"
INSTALLED_VERSION=""
if [ -f "$VERSION_FILE" ]; then
  INSTALLED_VERSION=$(cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]')
fi

if [ -z "$INSTALLED_VERSION" ]; then
  _add_result "version" "\"unknown\""
else
  _add_result "version" "\"$INSTALLED_VERSION\""
fi

# ── 종합 판정 ──────────────────────────────────────────────────────────────
ISSUE_COUNT=${#_issues[@]}
if [ "$ISSUE_COUNT" -eq 0 ]; then
  OVERALL="pass"
elif [ "$ISSUE_COUNT" -ge 3 ]; then
  OVERALL="fail"
else
  OVERALL="warn"
fi

_add_result "status" "\"$OVERALL\""
_add_result "issue_count" "$ISSUE_COUNT"

if [ ${#_issues[@]} -gt 0 ]; then
  issues_json=$(printf '%s\n' "${_issues[@]}" | $PYTHON -c "import json,sys; print(json.dumps(sys.stdin.read().strip().split('\n')))")
  _add_result "issues" "$issues_json"
fi

# ── 출력 ───────────────────────────────────────────────────────────────────
if [ "$JSON_MODE" = true ]; then
  echo "{$_result}"
  exit 0
fi

# 텍스트 출력
echo ""
echo "건강 진단"
echo "━━━━━━━━"

# 파일
if [ "$FOUND_FILES" -eq "$TOTAL_FILES" ]; then
  echo "  파일 무결성: ✅ $FOUND_FILES/$TOTAL_FILES"
else
  echo "  파일 무결성: ⚠️ $FOUND_FILES/$TOTAL_FILES"
  for m in "${MISSING_FILES[@]}"; do
    echo "    누락: $m"
  done
fi

# Hook
if [ "$HOOKS_FOUND" -eq "$HOOKS_TOTAL" ] && [ ${#HOOKS_FILE_MISSING[@]} -eq 0 ]; then
  echo "  Hook 등록:   ✅ $HOOKS_FOUND/$HOOKS_TOTAL"
else
  echo "  Hook 등록:   ⚠️ $HOOKS_FOUND/$HOOKS_TOTAL"
  for m in "${HOOKS_MISSING[@]}"; do
    echo "    ❌ $m — 미등록"
  done
  for m in "${HOOKS_FILE_MISSING[@]}"; do
    echo "    ⚠️ $m — 등록됨, 파일 없음"
  done
fi

# Git Hook
case "$GIT_HOOK_STATUS" in
  ok)   echo "  Git Hook:    ✅ core.hooksPath + post-commit" ;;
  warn) echo "  Git Hook:    ⚠️ $GIT_HOOK_DETAIL" ;;
  *)    echo "  Git Hook:    ❌ $GIT_HOOK_DETAIL" ;;
esac

# MCP
case "$MCP_STATUS" in
  ok)       echo "  MCP 서버:    ✅ worklog-for-claude 등록됨" ;;
  mismatch) echo "  MCP 서버:    ⚠️ command 불일치" ;;
  *)        echo "  MCP 서버:    ❌ worklog-for-claude 미등록" ;;
esac

# 환경변수
if [ "$ENV_STATUS" = "ok" ]; then
  echo "  환경변수:    ✅ 필수값 설정됨"
else
  echo "  환경변수:    ⚠️"
  for e in "${ENV_ISSUES[@]}"; do
    echo "    누락: $e"
  done
fi

# 버전
if [ -z "$INSTALLED_VERSION" ]; then
  echo "  버전:        알 수 없음"
else
  echo "  버전:        $INSTALLED_VERSION"
fi

# 종합
echo ""
if [ "$OVERALL" = "pass" ]; then
  echo "  ✅ 전체 정상"
elif [ "$OVERALL" = "warn" ]; then
  echo "  ⚠️ 일부 문제 발견"
  echo "  💡 문제 해결: /worklog-update 실행"
else
  echo "  ❌ 심각한 문제"
  echo "  💡 문제 해결: install.sh 재설치 권장"
fi
echo ""
