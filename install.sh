#!/bin/bash
# worklog-for-claude install wizard
# Usage: ./install.sh [--reconfigure]

set -euo pipefail

# ── 색상 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
err()   { echo -e "${RED}✗${NC}  $*" >&2; }
header(){ echo -e "\n${BOLD}${CYAN}── $* ──${NC}\n"; }

# ── 패키지 루트 감지 ─────────────────────────────────────────────────────────
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# curl 실행 모드: 패키지 파일이 없으면 임시 디렉토리에 clone
_CURL_TMPDIR=""
if [ ! -f "$PACKAGE_DIR/hooks/post-commit.sh" ]; then
  _CURL_TMPDIR=$(mktemp -d)
  trap 'rm -rf "$_CURL_TMPDIR"' EXIT
  echo "Downloading worklog-for-claude..."
  if ! git clone --depth 1 https://github.com/kangraemin/worklog-for-claude.git "$_CURL_TMPDIR/worklog-for-claude" 2>/dev/null; then
    err "git clone failed. Check your network connection."
    exit 1
  fi
  PACKAGE_DIR="$_CURL_TMPDIR/worklog-for-claude"
fi

# ── 언어 선택 / Language selection ───────────────────────────────────────────
printf "Language / 언어:\n  1) 한국어\n  2) English\n\n"
printf "Select / 선택 [1]: "
read -r _LANG_CHOICE
_LANG_CHOICE="${_LANG_CHOICE:-1}"
[ "$_LANG_CHOICE" = "2" ] && WORKLOG_LANG="en" || WORKLOG_LANG="ko"

# Bilingual text helper: t "한국어" "English"
t() { [ "$WORKLOG_LANG" = "en" ] && echo "$2" || echo "$1"; }

# ── 사전 조건 체크 ───────────────────────────────────────────────────────────
header "$(t '사전 조건 체크' 'Prerequisites')"

check_cmd() {
  if command -v "$1" &>/dev/null; then
    ok "$1 $(command -v "$1")"
    return 0
  else
    return 1
  fi
}

MISSING=()
check_cmd "claude"  || MISSING+=("claude (Claude Code CLI)")
# python3 또는 python 감지 (Windows는 python만 있음)
if command -v python3 &>/dev/null; then
  PYTHON=python3; ok "python3 $(command -v python3)"
elif command -v python &>/dev/null; then
  PYTHON=python; ok "python $(command -v python)"
else
  MISSING+=("python3 (or python)")
fi
check_cmd "curl"    || MISSING+=("curl")

if [ ${#MISSING[@]} -gt 0 ]; then
  err "$(t '필수 도구가 없습니다:' 'Required tools are missing:')"
  for m in "${MISSING[@]}"; do
    echo "   - $m"
  done
  exit 1
fi


# ── 설치 범위 ────────────────────────────────────────────────────────────────
header "$(t '설치 범위' 'Installation Scope')"

echo "  1) $(t '전역 (~/.claude/) — 모든 프로젝트에 적용' 'Global (~/.claude/) — applies to all projects')"
echo "  2) $(t '로컬 (.claude/)  — 현재 프로젝트에만 적용' 'Local (.claude/)   — current project only')"
echo ""
printf "$(t '선택' 'Select') [1]: "
read -r SCOPE_CHOICE
SCOPE_CHOICE="${SCOPE_CHOICE:-1}"

if [ "$SCOPE_CHOICE" = "2" ]; then
  # 자체 repo 안에서 실행 감지
  if [ "$(pwd)" = "$PACKAGE_DIR" ]; then
    warn "$(t 'worklog-for-claude 디렉토리 안에서 실행 중입니다.' \
            'Running inside worklog-for-claude directory.')"
    info "$(t '대상 프로젝트 루트에서 실행해주세요.' \
            'Please run from your target project root.')"
    info "$(t '예: cd /your/project && '"$PACKAGE_DIR"'/install.sh' \
            'e.g.: cd /your/project && '"$PACKAGE_DIR"'/install.sh')"
    exit 1
  fi
  TARGET_DIR="$(pwd)/.claude"
  SCOPE="local"
else
  TARGET_DIR="$HOME/.claude"
  SCOPE="global"
fi

info "$(t '설치 대상' 'Install target'): $TARGET_DIR"
mkdir -p "$TARGET_DIR"

# ── 저장 방식 ────────────────────────────────────────────────────────────────
header "$(t '워크로그 저장 방식' 'Storage Mode')"

echo "  1) $(t 'Notion + 로컬 파일 (both)  — 추천' 'Notion + local files (both)  — recommended')"
echo "  2) $(t 'Notion만 (notion-only)' 'Notion only (notion-only)')"
echo "  3) $(t '로컬 파일만 (git)' 'Local files only (git)')"
echo ""
printf "$(t '선택' 'Select') [1]: "
read -r DEST_CHOICE
DEST_CHOICE="${DEST_CHOICE:-1}"

case "$DEST_CHOICE" in
  2) WORKLOG_DEST="notion-only"; WORKLOG_GIT_TRACK="false" ;;
  3) WORKLOG_DEST="git" ;;
  *) WORKLOG_DEST="notion" ;;
esac

# ── Notion 설정 ──────────────────────────────────────────────────────────────
NOTION_TOKEN=""
NOTION_DB_ID=""

if [ "$WORKLOG_DEST" != "git" ]; then
  header "$(t 'Notion 설정' 'Notion Setup')"

  # 기존 토큰 탐색
  NOTION_TOKEN="${NOTION_TOKEN:-}"
  if [ -z "$NOTION_TOKEN" ] && [ -f "$TARGET_DIR/.env" ]; then
    NOTION_TOKEN=$(grep "^NOTION_TOKEN=" "$TARGET_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  fi
  if [ -z "$NOTION_TOKEN" ] && [ -f "$HOME/.claude/.env" ]; then
    NOTION_TOKEN=$(grep "^NOTION_TOKEN=" "$HOME/.claude/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  fi

  if [ -n "$NOTION_TOKEN" ]; then
    ok "$(t '기존 NOTION_TOKEN 발견 — 재사용합니다.' 'Existing NOTION_TOKEN found — reusing.')"
  else
    info "$(t 'Notion Integration 토큰이 필요합니다.' 'A Notion Integration token is required.')"
    info "$(t 'https://www.notion.so/my-integrations 에서 생성하세요.' 'Create one at https://www.notion.so/my-integrations')"
    echo ""
    printf "NOTION_TOKEN ($(t '빈 값이면 나중에 설정' 'leave blank to set later')): "
    read -r NOTION_TOKEN

    # 새 입력 토큰만 형식 검증 (ntn_ 또는 secret_ 로 시작, 최소 20자)
    if [ -n "$NOTION_TOKEN" ]; then
      if [[ ! "$NOTION_TOKEN" =~ ^(ntn_|secret_) ]] || [ ${#NOTION_TOKEN} -lt 20 ]; then
        warn "$(t '토큰 형식이 올바르지 않을 수 있습니다 (ntn_ 또는 secret_ 로 시작해야 합니다).' \
                'Token format may be invalid (should start with ntn_ or secret_).')"
        printf "$(t '계속 진행하시겠습니까? [y/N] ' 'Continue anyway? [y/N] ')"
        read -r CONFIRM
        if [[ ! "$CONFIRM" =~ ^[yY] ]]; then
          NOTION_TOKEN=""
        fi
      fi
    fi
  fi

  if [ -n "$NOTION_TOKEN" ]; then
    ok "$(t '토큰 입력 완료' 'Token accepted')"

    # 기존 NOTION_DB_ID 탐색
    if [ -z "$NOTION_DB_ID" ]; then
      NOTION_DB_ID=$($PYTHON -c "
import json, os
for path in ['$TARGET_DIR/settings.json', os.path.expanduser('~/.claude/settings.json')]:
    try:
        with open(path) as f:
            cfg = json.load(f)
        db_id = cfg.get('env', {}).get('NOTION_DB_ID', '')
        if db_id:
            print(db_id)
            break
    except:
        pass
" 2>/dev/null || true)
    fi

    if [ -n "$NOTION_DB_ID" ]; then
      ok "$(t '기존 NOTION_DB_ID 발견 — 재사용합니다' 'Existing NOTION_DB_ID found — reusing'): $NOTION_DB_ID"
    else
      # DB 자동 생성
      echo ""
      info "$(t '워크로그 DB를 생성할 Notion 페이지 URL 또는 ID를 입력하세요.' 'Enter the URL or ID of the Notion page where the worklog DB will be created.')"
      info "$(t '예' 'e.g.'): https://notion.so/My-Page-abc123def456"
      echo ""
      printf "$(t '부모 페이지 URL/ID' 'Parent page URL/ID'): "
      read -r PARENT_INPUT

      # URL에서 page_id 추출
      PARENT_ID=$(echo "$PARENT_INPUT" | $PYTHON -c "
import sys, re
raw = sys.stdin.read().strip()
m = re.search(r'([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', raw)
print(m.group(1) if m else raw)
")

      if [ -n "$PARENT_ID" ]; then
        info "$(t 'DB 생성 중...' 'Creating DB...')"

        DB_PAYLOAD=$($PYTHON -c "
import json
data = {
    'parent': {'type': 'page_id', 'page_id': '$PARENT_ID'},
    'icon': {'type': 'emoji', 'emoji': '📖'},
    'title': [{'type': 'text', 'text': {'content': 'AI Worklog'}}],
    'properties': {
        'Title':    {'title': {}},
        'DateTime': {'date': {}},
        'Project':  {'select': {'options': []}},
        'Tokens':   {'number': {'format': 'number'}},
        'Cost':     {'number': {'format': 'number'}},
        'Duration': {'number': {'format': 'number'}},
        'Model':    {'select': {'options': [
            {'name': 'claude-opus-4-6', 'color': 'purple'},
            {'name': 'claude-sonnet-4-6', 'color': 'blue'},
            {'name': 'claude-haiku-4-5', 'color': 'green'}
        ]}}
    }
}
print(json.dumps(data))
")

        RESPONSE=$(curl -s --connect-timeout 10 --max-time 30 -w "\n%{http_code}" -X POST "https://api.notion.com/v1/databases" \
          -H "Authorization: Bearer $NOTION_TOKEN" \
          -H "Notion-Version: 2022-06-28" \
          -H "Content-Type: application/json" \
          -d "$DB_PAYLOAD")

        HTTP_CODE=$(echo "$RESPONSE" | tail -1)
        BODY=$(echo "$RESPONSE" | sed '$d')

        if [ "$HTTP_CODE" = "200" ]; then
          NOTION_DB_ID=$(echo "$BODY" | $PYTHON -c "import json,sys; print(json.load(sys.stdin)['id'])")
          ok "$(t 'DB 생성 완료' 'DB created'): $NOTION_DB_ID"
        else
          err "$(t 'DB 생성 실패' 'DB creation failed') (HTTP $HTTP_CODE)"
          echo "$BODY" | $PYTHON -c "import json,sys; d=json.load(sys.stdin); print(d.get('message',str(d)))" 2>/dev/null || echo "$BODY"
          echo ""
          printf "$(t '기존 NOTION_DB_ID를 입력하세요 (URL 또는 ID, 빈 값이면 스킵)' 'Enter existing NOTION_DB_ID (URL or ID, blank to skip)'): "
          read -r NOTION_DB_INPUT
          # URL/문자열에서 ID 자동 추출
          NOTION_DB_ID=$(echo "$NOTION_DB_INPUT" | $PYTHON -c "
import sys, re
raw = sys.stdin.read().strip()
m = re.search(r'([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', raw, re.IGNORECASE)
print(m.group(1) if m else raw)
" 2>/dev/null)
          # Notion API로 유효성 검증
          if [ -n "$NOTION_DB_ID" ]; then
            VERIFY_CODE=$(curl -s --connect-timeout 5 --max-time 10 \
              -o /dev/null -w "%{http_code}" \
              -H "Authorization: Bearer $NOTION_TOKEN" \
              -H "Notion-Version: 2022-06-28" \
              "https://api.notion.com/v1/databases/$NOTION_DB_ID" 2>/dev/null || echo "000")
            case "$VERIFY_CODE" in
              200) ok "$(t 'DB 확인 완료' 'DB verified'): $NOTION_DB_ID" ;;
              403) warn "$(t 'DB에 접근할 수 없습니다. Notion Integration을 DB에 연결했는지 확인하세요.' \
                          'Cannot access DB. Make sure the Notion Integration is connected.')"
                   info "$(t 'DB 페이지 → ··· → Connections → Integration 추가' \
                          'DB page → ··· → Connections → Add integration')" ;;
              404) warn "$(t 'DB를 찾을 수 없습니다. ID를 다시 확인하세요.' 'DB not found. Check the ID.')" ;;
              *)   warn "$(t 'DB 검증 실패 (HTTP' 'DB verification failed (HTTP') $VERIFY_CODE)" ;;
            esac
          fi
        fi
      fi
    fi
  else
    warn "$(t 'Notion 토큰 없이 계속합니다.' 'Continuing without Notion token.')"
    info "$(t '나중에 다음 파일에 NOTION_TOKEN=<값> 을 추가하세요:' 'Add NOTION_TOKEN=<value> to one of these files later:')"
    info "  1) $TARGET_DIR/.env"
    info "  2) $HOME/.claude/.env"
    info "$(t '/worklog 실행 시 위 순서로 자동 탐색합니다.' '/worklog will search them in this order.')"
  fi
fi

# ── git 추적 ─────────────────────────────────────────────────────────────────
if [ "$WORKLOG_DEST" != "notion-only" ]; then
  header "$(t 'Git 추적' 'Git Tracking')"

  echo "  1) $(t '.worklogs/ 를 git에 추적 (기본)' 'Track .worklogs/ in git (default)')"
  echo "  2) $(t '.worklogs/ 를 .gitignore에 추가' 'Add .worklogs/ to .gitignore')"
  echo ""
  printf "$(t '선택' 'Select') [1]: "
  read -r GIT_CHOICE
  GIT_CHOICE="${GIT_CHOICE:-1}"

  if [ "$GIT_CHOICE" = "2" ]; then
    WORKLOG_GIT_TRACK="false"
  else
    WORKLOG_GIT_TRACK="true"
  fi
fi

# ── 작성 시점 ────────────────────────────────────────────────────────────────
header "$(t '워크로그 작성 시점' 'When to Write Worklogs')"

echo "  1) stop         — $(t '세션 종료 시 자동 (추천)' 'automatically on session stop (recommended)')"
echo "  2) manual      — $(t '/worklog 실행할 때만' 'only when running /worklog')"
echo ""
printf "$(t '선택' 'Select') [1]: "
read -r TIMING_CHOICE
TIMING_CHOICE="${TIMING_CHOICE:-1}"

case "$TIMING_CHOICE" in
  2) WORKLOG_TIMING="manual" ;;
  *) WORKLOG_TIMING="stop" ;;
esac

# ── 자동 커밋 (deprecated) ────────────────────────────────────────────────────
# stop hook에서 block하지 않음. 커밋은 워크플로우 도구(ai-bouncer 등)나 사용자가 직접 관리.
AUTO_COMMIT="false"

# ── 파일 복사 ────────────────────────────────────────────────────────────────
header "$(t '파일 설치' 'Installing Files')"

# 스크립트/문서: 항상 덮어쓰기 (패키지 관리 파일, 사용자 수정 X)
copy_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -f "$dst" ]; then
    cp "$dst" "${dst}.bak"
    warn "$(t '기존 파일 백업' 'Backed up existing file'): ${dst}.bak"
  fi
  cp "$src" "$dst"
  ok "$(basename "$dst")"
}

# 훅: 관리 블록(# --- worklog-for-claude start/end ---)만 교체, 나머지 보존
# 하위 호환: 기존 ai-worklog 마커도 인식하여 교체
install_file() {
  local src="$1" dst="$2"
  local START="# --- worklog-for-claude start ---"
  local END="# --- worklog-for-claude end ---"

  mkdir -p "$(dirname "$dst")"

  if [ ! -f "$dst" ]; then
    cp "$src" "$dst"
    ok "$(basename "$dst") ($(t '새로 설치' 'new install'))"
    return
  fi

  $PYTHON - "$src" "$dst" "$START" "$END" <<'PYEOF'
import sys

src_path     = sys.argv[1]
dst_path     = sys.argv[2]
start_marker = sys.argv[3]
end_marker   = sys.argv[4]

# 하위 호환: 기존 ai-worklog 마커
OLD_START = "# --- ai-worklog start ---"
OLD_END   = "# --- ai-worklog end ---"

src = open(src_path, encoding='utf-8').read()
dst = open(dst_path, encoding='utf-8').read()

s_start = src.find(start_marker)
s_end   = src.find(end_marker)

if s_start == -1 or s_end == -1:
    # 소스에 관리 블록 없으면 전체 교체
    open(dst_path, 'w', encoding='utf-8').write(src)
    sys.exit(0)

managed_block = src[s_start : s_end + len(end_marker)]

# 새 마커 먼저 탐색, 없으면 구 마커 탐색
d_start = dst.find(start_marker)
d_end   = dst.find(end_marker)
d_end_len = len(end_marker)

if d_start == -1 or d_end == -1:
    d_start = dst.find(OLD_START)
    d_end   = dst.find(OLD_END)
    d_end_len = len(OLD_END)

if d_start != -1 and d_end != -1:
    # 기존 관리 블록 교체
    new_dst = dst[:d_start] + managed_block + dst[d_end + d_end_len:]
else:
    # 관리 블록 없음: exit 0 앞에 삽입 (exit 0이 있으면 append해도 실행 안 됨)
    import re
    exit_match = re.search(r'^exit\s+0\s*$', dst, re.MULTILINE)
    if exit_match:
        pos = exit_match.start()
        new_dst = dst[:pos] + managed_block + '\n\n' + dst[pos:]
    else:
        new_dst = dst.rstrip('\n') + '\n\n' + managed_block + '\n'

open(dst_path, 'w', encoding='utf-8').write(new_dst)
PYEOF

  ok "$(basename "$dst") ($(t '관리 블록 업데이트' 'managed block updated'))"
}

# scripts (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/scripts/notion-worklog.sh"          "$TARGET_DIR/scripts/notion-worklog.sh"
copy_file "$PACKAGE_DIR/scripts/notion-migrate-worklogs.sh" "$TARGET_DIR/scripts/notion-migrate-worklogs.sh"
copy_file "$PACKAGE_DIR/scripts/duration.py"                "$TARGET_DIR/scripts/duration.py"
copy_file "$PACKAGE_DIR/scripts/token-cost.py"             "$TARGET_DIR/scripts/token-cost.py"
copy_file "$PACKAGE_DIR/scripts/update-check.sh"            "$TARGET_DIR/scripts/update-check.sh"
copy_file "$PACKAGE_DIR/scripts/worklog-write.sh"           "$TARGET_DIR/scripts/worklog-write.sh"

# hooks (관리 블록만 교체)
install_file "$PACKAGE_DIR/hooks/worklog.sh"           "$TARGET_DIR/hooks/worklog.sh"
install_file "$PACKAGE_DIR/hooks/session-end.sh"       "$TARGET_DIR/hooks/session-end.sh"
copy_file    "$PACKAGE_DIR/hooks/post-commit.sh"       "$TARGET_DIR/hooks/post-commit.sh"
copy_file    "$PACKAGE_DIR/hooks/commit-doc-check.sh"         "$TARGET_DIR/hooks/commit-doc-check.sh"
install_file "$PACKAGE_DIR/hooks/on-commit.sh"         "$TARGET_DIR/hooks/on-commit.sh"
install_file "$PACKAGE_DIR/hooks/stop.sh"              "$TARGET_DIR/hooks/stop.sh"

# commands (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/commands/worklog.md"          "$TARGET_DIR/commands/worklog.md"
copy_file "$PACKAGE_DIR/commands/worklog-migrate.md"  "$TARGET_DIR/commands/worklog-migrate.md"
copy_file "$PACKAGE_DIR/commands/worklog-update.md"   "$TARGET_DIR/commands/worklog-update.md"
copy_file "$PACKAGE_DIR/commands/worklog-config.md"  "$TARGET_DIR/commands/worklog-config.md"

# rules (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/rules/worklog-rules.md"    "$TARGET_DIR/rules/worklog-rules.md"
copy_file "$PACKAGE_DIR/rules/auto-commit-rules.md" "$TARGET_DIR/rules/auto-commit-rules.md"

# 실행 권한
chmod +x "$TARGET_DIR/scripts/notion-worklog.sh"
chmod +x "$TARGET_DIR/scripts/notion-migrate-worklogs.sh"
chmod +x "$TARGET_DIR/scripts/update-check.sh"
chmod +x "$TARGET_DIR/scripts/worklog-write.sh"
chmod +x "$TARGET_DIR/hooks/worklog.sh"
chmod +x "$TARGET_DIR/hooks/session-end.sh"
chmod +x "$TARGET_DIR/hooks/post-commit.sh"
chmod +x "$TARGET_DIR/hooks/commit-doc-check.sh"
chmod +x "$TARGET_DIR/hooks/on-commit.sh"
chmod +x "$TARGET_DIR/hooks/stop.sh"

# ── 버전 SHA 저장 ─────────────────────────────────────────────────────────────
INSTALLED_SHA=$(git -C "$PACKAGE_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "$INSTALLED_SHA" > "$TARGET_DIR/.version"
ok "$(t '버전 기록' 'Version recorded'): $INSTALLED_SHA"

# ── .env 설정 ────────────────────────────────────────────────────────────────
if [ -n "$NOTION_TOKEN" ]; then
  ENV_FILE="$TARGET_DIR/.env"
  if [ -f "$ENV_FILE" ]; then
    # 기존 .env에 NOTION_TOKEN이 있으면 업데이트, 없으면 추가
    if grep -q "^NOTION_TOKEN=" "$ENV_FILE" 2>/dev/null; then
      sed -i.bak "s|^NOTION_TOKEN=.*|NOTION_TOKEN=$NOTION_TOKEN|" "$ENV_FILE"
      rm -f "${ENV_FILE}.bak"
    else
      echo "NOTION_TOKEN=$NOTION_TOKEN" >> "$ENV_FILE"
    fi
  else
    echo "NOTION_TOKEN=$NOTION_TOKEN" > "$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
  ok "$(t '.env 설정 완료 (권한: 600)' '.env configured (permissions: 600)')"
fi

# ── settings.json 훅 머지 ───────────────────────────────────────────────────
header "$(t 'settings.json 설정' 'Updating settings.json')"

SETTINGS_FILE="$TARGET_DIR/settings.json"

$PYTHON - "$SETTINGS_FILE" "$TARGET_DIR" "$WORKLOG_TIMING" "$WORKLOG_DEST" "$WORKLOG_GIT_TRACK" "${NOTION_DB_ID:-}" "$WORKLOG_LANG" "$AUTO_COMMIT" "${DOC_CHECK_INTERVAL:-5}" <<'PYEOF'
import json, sys, os

settings_file      = sys.argv[1]
target_dir         = sys.argv[2]
timing             = sys.argv[3]
dest               = sys.argv[4]
git_track          = sys.argv[5]
notion_db_id       = sys.argv[6]
worklog_lang       = sys.argv[7]
auto_commit        = sys.argv[8] if len(sys.argv) > 8 else 'false'
doc_check_interval = sys.argv[9] if len(sys.argv) > 9 else '5'

# 기존 설정 읽기
cfg = {}
if os.path.exists(settings_file):
    with open(settings_file, encoding='utf-8') as f:
        cfg = json.load(f)

# ── env 머지 ──
env = cfg.setdefault('env', {})
env['WORKLOG_TIMING']    = timing
env['WORKLOG_DEST']      = dest
env['WORKLOG_GIT_TRACK'] = git_track
env['WORKLOG_LANG']      = worklog_lang
env['AI_WORKLOG_DIR']    = target_dir
if notion_db_id:
    env['NOTION_DB_ID'] = notion_db_id
env['PROJECT_DOC_CHECK_INTERVAL'] = doc_check_interval

# ── hooks 머지 ──
hooks = cfg.setdefault('hooks', {})

# 훅 정의: (이벤트, command, timeout, async, matcher)
hook_defs = [
    ('PostToolUse',  f'{target_dir}/hooks/worklog.sh',           5,  True,  None),
    ('PostToolUse',  f'{target_dir}/hooks/on-commit.sh',         5,  False, 'Bash'),
    ('PostToolUse',  f'{target_dir}/hooks/commit-doc-check.sh',  5,  False, None),
    ('SessionStart', f'{target_dir}/scripts/update-check.sh',    15, True,  None),
    ('SessionEnd',   f'{target_dir}/hooks/session-end.sh',       15, False, None),
    ('Stop',         f'{target_dir}/hooks/stop.sh',              15, False, None),
]

def add_command_hook(event, command, timeout, is_async, matcher=None):
    event_hooks = hooks.setdefault(event, [])
    for group in event_hooks:
        for h in group.get('hooks', []):
            if h.get('command', '').rstrip() == command:
                print(f'  · {event} hook already exists: {os.path.basename(command)}')
                return
    new_hook = {'type': 'command', 'command': command, 'timeout': timeout}
    if is_async:
        new_hook['async'] = True
    entry = {'hooks': [new_hook]}
    if matcher:
        entry['matcher'] = matcher
    event_hooks.append(entry)
    print(f'  ✓ {event} hook added: {os.path.basename(command)}')

for event, command, timeout, is_async, matcher in hook_defs:
    add_command_hook(event, command, timeout, is_async, matcher)


# 저장
with open(settings_file, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f'\n  Saved: {settings_file}')
PYEOF

ok "$(t 'settings.json 업데이트 완료' 'settings.json updated')"

# ── .gitignore에 .worklogs/ 추가 (git 미추적 모드) ──────────────────────────
if [ "$WORKLOG_GIT_TRACK" = "false" ]; then
  if [ "$SCOPE" = "local" ]; then
    _REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$_REPO_ROOT" ]; then
      GITIGNORE="$_REPO_ROOT/.gitignore"
      if ! grep -q "^\.worklogs/" "$GITIGNORE" 2>/dev/null; then
        echo ".worklogs/" >> "$GITIGNORE"
        ok "$(t '.gitignore에 .worklogs/ 추가' 'Added .worklogs/ to .gitignore')"
      fi
    else
      info "$(t 'git 레포가 아닙니다. .gitignore 설정을 건너뜁니다.' 'Not a git repo. Skipping .gitignore setup.')"
    fi
  else
    # 전역: global gitignore에 추가
    GLOBAL_GITIGNORE=$(git config --global core.excludesFile 2>/dev/null || echo "$HOME/.gitignore_global")
    GLOBAL_GITIGNORE="${GLOBAL_GITIGNORE/#\~/$HOME}"
    if ! grep -q "^\.worklogs/" "$GLOBAL_GITIGNORE" 2>/dev/null; then
      mkdir -p "$(dirname "$GLOBAL_GITIGNORE")"
      echo ".worklogs/" >> "$GLOBAL_GITIGNORE"
      git config --global core.excludesFile "$GLOBAL_GITIGNORE"
      ok "$(t '전역 .gitignore에 .worklogs/ 추가' 'Added .worklogs/ to global .gitignore'): $GLOBAL_GITIGNORE"
    fi
  fi
fi

# ── git hook 설치 ─────────────────────────────────────────────────────────────
header "$(t 'Git Hook 설치' 'Git Hook Setup')"

GIT_HOOKS_DIR="$TARGET_DIR/git-hooks"
mkdir -p "$GIT_HOOKS_DIR"

# post-commit hook 래퍼 설치
copy_file "$PACKAGE_DIR/git-hooks/post-commit" "$GIT_HOOKS_DIR/post-commit"
chmod +x "$GIT_HOOKS_DIR/post-commit"

if [ "$SCOPE" = "global" ]; then
  # 전역: core.hooksPath 설정
  CURRENT_HOOKS_PATH=$(git config --global core.hooksPath 2>/dev/null || true)

  if [ -z "$CURRENT_HOOKS_PATH" ]; then
    git config --global core.hooksPath "$GIT_HOOKS_DIR"
    ok "$(t '전역 git hooksPath 설정' 'Global git hooksPath configured'): $GIT_HOOKS_DIR"
  elif [ "$CURRENT_HOOKS_PATH" = "$GIT_HOOKS_DIR" ]; then
    ok "$(t '전역 git hooksPath 이미 설정됨' 'Global git hooksPath already set'): $GIT_HOOKS_DIR"
  else
    warn "$(t '기존 core.hooksPath 발견' 'Existing core.hooksPath found'): $CURRENT_HOOKS_PATH"
    info "$(t '기존 경로에 post-commit hook도 설치합니다.' 'Also installing post-commit hook to existing path.')"
    # 기존 hooksPath에도 post-commit 설치 (chaining)
    if [ -d "$CURRENT_HOOKS_PATH" ]; then
      copy_file "$PACKAGE_DIR/git-hooks/post-commit" "$CURRENT_HOOKS_PATH/post-commit"
      chmod +x "$CURRENT_HOOKS_PATH/post-commit"
    fi
  fi

  info "$(t 'hook chaining: 레포별 hook은 .git/hooks/post-commit.local로 이름 변경하세요.' \
          'Hook chaining: rename repo hooks to .git/hooks/post-commit.local')"
else
  # 로컬: 현재 레포 .git/hooks/에 설치
  REPO_GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || true)
  if [ -n "$REPO_GIT_DIR" ]; then
    LOCAL_HOOK="$REPO_GIT_DIR/hooks/post-commit"
    if [ -f "$LOCAL_HOOK" ]; then
      # 기존 hook → .local로 보존 (chaining)
      if [ ! -f "${LOCAL_HOOK}.local" ]; then
        mv "$LOCAL_HOOK" "${LOCAL_HOOK}.local"
        warn "$(t '기존 post-commit hook → post-commit.local로 보존' \
                'Existing post-commit hook preserved as post-commit.local')"
      fi
    fi
    copy_file "$PACKAGE_DIR/git-hooks/post-commit" "$LOCAL_HOOK"
    chmod +x "$LOCAL_HOOK"
  else
    warn "$(t 'git 레포가 아닙니다. git hook 설치를 건너뜁니다.' \
            'Not a git repo. Skipping git hook installation.')"
  fi
fi

# ── MCP 서버 설정 ─────────────────────────────────────────────────────────────
header "$(t 'MCP 서버 설정' 'MCP Server Setup')"

DOC_CHECK_INTERVAL="5"
_MCP_INSTALLED="false"

if ! command -v uv &>/dev/null; then
  warn "$(t 'uv가 없습니다. MCP 설정을 건너뜁니다.' 'uv not found. Skipping MCP setup.')"
  info "$(t 'uv 설치: https://docs.astral.sh/uv/' 'Install uv: https://docs.astral.sh/uv/')"
else
  printf "$(t 'PROJECT.md 업데이트 체크 주기 (커밋 몇 개마다?)' 'How many commits between PROJECT.md update checks?') [5]: "
  read -r _DOC_INTERVAL
  DOC_CHECK_INTERVAL="${_DOC_INTERVAL:-5}"

  echo ""
  echo "  $(t 'MCP 클라이언트 선택' 'Select MCP client'):"
  echo "  1) Claude Code (~/.claude/settings.json)"
  echo "  2) Cursor (~/.cursor/mcp.json)"
  echo "  3) Claude Desktop"
  echo "  4) $(t '전부' 'All')"
  echo "  5) $(t '건너뜀' 'Skip')"
  printf "$(t '선택' 'Select') [1]: "
  read -r MCP_CHOICE
  MCP_CHOICE="${MCP_CHOICE:-1}"

  setup_mcp_client() {
    local config_file="$1"
    local client_name="$2"
    mkdir -p "$(dirname "$config_file")"
    $PYTHON - "$config_file" "$DOC_CHECK_INTERVAL" <<'PYEOF'
import json, sys, os
config_file = sys.argv[1]
interval = sys.argv[2]
cfg = {}
if os.path.exists(config_file):
    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
servers = cfg.setdefault('mcpServers', {})
servers['worklog-for-claude'] = {
    'command': 'uvx',
    'args': ['worklog-for-claude'],
    'env': {'PROJECT_DOC_CHECK_INTERVAL': interval}
}
with open(config_file, 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
PYEOF
    ok "$(t 'MCP 설정 완료' 'MCP configured') ($client_name): $config_file"
  }

  if [[ "$MCP_CHOICE" =~ ^[14]$ ]]; then
    setup_mcp_client "$HOME/.claude/settings.json" "Claude Code"
  fi
  if [[ "$MCP_CHOICE" =~ ^[24]$ ]]; then
    setup_mcp_client "$HOME/.cursor/mcp.json" "Cursor"
  fi
  if [[ "$MCP_CHOICE" =~ ^[34]$ ]]; then
    setup_mcp_client "$HOME/Library/Application Support/Claude/claude_desktop_config.json" "Claude Desktop"
  fi

  if [ "$MCP_CHOICE" = "5" ]; then
    info "$(t 'MCP 설정 건너뜀. 나중에 수동으로 추가하세요.' 'MCP setup skipped. Add manually later.')"
    info "  uvx worklog-for-claude"
  else
    _MCP_INSTALLED="true"
  fi
fi

# ── 완료 ─────────────────────────────────────────────────────────────────────
header "$(t '설치 완료' 'Installation Complete')"

echo -e "  ${BOLD}$(t '설정 요약' 'Summary')${NC}"
echo "  ├─ $(t '범위' 'Scope'):     $SCOPE ($TARGET_DIR)"
echo "  ├─ $(t '저장' 'Storage'):   $WORKLOG_DEST"
if [ "$WORKLOG_DEST" != "notion-only" ]; then
echo "  ├─ $(t 'git 추적' 'Git track'): $WORKLOG_GIT_TRACK"
fi
echo "  ├─ $(t '시점' 'Timing'):    $WORKLOG_TIMING"
echo "  ├─ $(t '언어' 'Language'):  $WORKLOG_LANG"
if [ -n "$NOTION_DB_ID" ]; then
echo "  ├─ Notion DB: $NOTION_DB_ID"
fi
echo "  ├─ $(t '훅' 'Hooks'):      PostToolUse (3), SessionStart, SessionEnd, Stop"
if [ "${_MCP_INSTALLED:-}" = "true" ]; then
echo "  ├─ MCP:        uvx worklog-for-claude (interval: ${DOC_CHECK_INTERVAL:-5})"
fi
echo "  └─ $(t 'Git Hook' 'Git Hook'):  post-commit ($(t '터미널 커밋 시 워크로그' 'worklog on terminal commits'))"

echo ""
echo -e "  ${BOLD}$(t '사용법' 'Usage')${NC}"
echo "  • /worklog           — $(t '워크로그 수동 작성' 'write a worklog entry')"
echo "  • /worklog-migrate   — $(t '기존 .worklogs/ → Notion 마이그레이션' 'migrate existing .worklogs/ to Notion')"
echo ""
echo -e "  ${BOLD}$(t '팁' 'Tip')${NC}"
echo "  $(t 'Claude Code 세션에서 /worklog 로 워크로그를 작성하세요.' 'Use /worklog in Claude Code sessions to write worklogs.')"
echo ""
echo -e "  ${BOLD}$(t '재설정' 'Reconfigure')${NC}"
echo "  • $PACKAGE_DIR/install.sh --reconfigure"
echo ""
ok "$(t 'worklog-for-claude 설치가 완료되었습니다!' 'worklog-for-claude installed successfully!')"
