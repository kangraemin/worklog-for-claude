#!/bin/bash
# ai-worklog install wizard
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

# ── 사전 조건 체크 ───────────────────────────────────────────────────────────
header "사전 조건 체크"

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
check_cmd "python3" || MISSING+=("python3")
check_cmd "curl"    || MISSING+=("curl")
check_cmd "jq"      || MISSING+=("jq")

if [ ${#MISSING[@]} -gt 0 ]; then
  err "필수 도구가 없습니다:"
  for m in "${MISSING[@]}"; do
    echo "   - $m"
  done
  exit 1
fi

# ccusage는 선택
if ! check_cmd "ccusage"; then
  warn "ccusage가 없습니다 (토큰/비용 추적에 필요)"
  echo -n "   npm install -g ccusage 로 설치하시겠습니까? [y/N] "
  read -r INSTALL_CCUSAGE
  if [[ "$INSTALL_CCUSAGE" =~ ^[yY]$ ]]; then
    npm install -g ccusage
    ok "ccusage 설치 완료"
  else
    warn "ccusage 없이 계속합니다 (토큰 추적 불가)"
  fi
fi

# ── 설치 범위 ────────────────────────────────────────────────────────────────
header "설치 범위"

echo "  1) 전역 (~/.claude/) — 모든 프로젝트에 적용"
echo "  2) 로컬 (.claude/)  — 현재 프로젝트에만 적용"
echo ""
echo -n "선택 [1]: "
read -r SCOPE_CHOICE
SCOPE_CHOICE="${SCOPE_CHOICE:-1}"

if [ "$SCOPE_CHOICE" = "2" ]; then
  TARGET_DIR="$(pwd)/.claude"
  SCOPE="local"
else
  TARGET_DIR="$HOME/.claude"
  SCOPE="global"
fi

info "설치 대상: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

# ── 저장 방식 ────────────────────────────────────────────────────────────────
header "워크로그 저장 방식"

echo "  1) Notion + 로컬 파일 (both)  — 추천"
echo "  2) Notion만 (notion-only)"
echo "  3) 로컬 파일만 (git)"
echo ""
echo -n "선택 [1]: "
read -r DEST_CHOICE
DEST_CHOICE="${DEST_CHOICE:-1}"

case "$DEST_CHOICE" in
  2) WORKLOG_DEST="notion-only"; WORKLOG_GIT_TRACK="false" ;;
  3) WORKLOG_DEST="git";         WORKLOG_GIT_TRACK="true"  ;;
  *) WORKLOG_DEST="notion";      WORKLOG_GIT_TRACK="true"  ;;
esac

# ── Notion 설정 ──────────────────────────────────────────────────────────────
NOTION_TOKEN=""
NOTION_DB_ID=""

if [ "$WORKLOG_DEST" != "git" ]; then
  header "Notion 설정"

  # 기존 토큰 탐색
  NOTION_TOKEN="${NOTION_TOKEN:-}"
  if [ -z "$NOTION_TOKEN" ] && [ -f "$TARGET_DIR/.env" ]; then
    NOTION_TOKEN=$(grep "^NOTION_TOKEN=" "$TARGET_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  fi
  if [ -z "$NOTION_TOKEN" ] && [ -f "$HOME/.claude/.env" ]; then
    NOTION_TOKEN=$(grep "^NOTION_TOKEN=" "$HOME/.claude/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  fi

  if [ -n "$NOTION_TOKEN" ]; then
    ok "기존 NOTION_TOKEN 발견 — 재사용합니다."
  else
    info "Notion Integration 토큰이 필요합니다."
    info "https://www.notion.so/my-integrations 에서 생성하세요."
    echo ""
    echo -n "NOTION_TOKEN (빈 값이면 나중에 설정): "
    read -r NOTION_TOKEN
  fi

  if [ -n "$NOTION_TOKEN" ]; then
    ok "토큰 입력 완료"

    # 기존 NOTION_DB_ID 탐색
    if [ -z "$NOTION_DB_ID" ]; then
      NOTION_DB_ID=$(python3 -c "
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
      ok "기존 NOTION_DB_ID 발견 — 재사용합니다: $NOTION_DB_ID"
    else
      # DB 자동 생성
      echo ""
      info "워크로그 DB를 생성할 Notion 페이지 URL 또는 ID를 입력하세요."
      info "예: https://notion.so/My-Page-abc123def456"
      echo ""
      echo -n "부모 페이지 URL/ID: "
      read -r PARENT_INPUT

      # URL에서 page_id 추출
      PARENT_ID=$(echo "$PARENT_INPUT" | python3 -c "
import sys, re
raw = sys.stdin.read().strip()
m = re.search(r'([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', raw)
print(m.group(1) if m else raw)
")

      if [ -n "$PARENT_ID" ]; then
        info "DB 생성 중..."

        DB_PAYLOAD=$(python3 -c "
import json
data = {
    'parent': {'type': 'page_id', 'page_id': '$PARENT_ID'},
    'icon': {'type': 'emoji', 'emoji': '📖'},
    'title': [{'type': 'text', 'text': {'content': 'AI Worklog'}}],
    'properties': {
        'Title':    {'title': {}},
        'Date':     {'date': {}},
        'DateTime': {'date': {}},
        'Project':  {'select': {'options': []}},
        'Cost':     {'number': {'format': 'number'}},
        'Duration': {'number': {'format': 'number'}},
        'Model':    {'select': {'options': [
            {'name': 'claude-opus-4-6', 'color': 'purple'},
            {'name': 'claude-sonnet-4-6', 'color': 'blue'},
            {'name': 'claude-haiku-4-5', 'color': 'green'}
        ]}},
        'Tokens':   {'number': {'format': 'number'}}
    }
}
print(json.dumps(data))
")

        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://api.notion.com/v1/databases" \
          -H "Authorization: Bearer $NOTION_TOKEN" \
          -H "Notion-Version: 2022-06-28" \
          -H "Content-Type: application/json" \
          -d "$DB_PAYLOAD")

        HTTP_CODE=$(echo "$RESPONSE" | tail -1)
        BODY=$(echo "$RESPONSE" | sed '$d')

        if [ "$HTTP_CODE" = "200" ]; then
          NOTION_DB_ID=$(echo "$BODY" | jq -r '.id')
          ok "DB 생성 완료: $NOTION_DB_ID"
        else
          err "DB 생성 실패 (HTTP $HTTP_CODE)"
          echo "$BODY" | jq -r '.message // .' 2>/dev/null || echo "$BODY"
          echo ""
          echo -n "기존 NOTION_DB_ID를 직접 입력하시겠습니까? (빈 값이면 스킵): "
          read -r NOTION_DB_ID
        fi
      fi
    fi
  else
    warn "Notion 토큰 없이 계속합니다."
    info "나중에 다음 파일에 NOTION_TOKEN=<값> 을 추가하세요:"
    info "  1) $TARGET_DIR/.env"
    info "  2) $HOME/.claude/.env"
    info "/worklog 실행 시 위 순서로 자동 탐색합니다."
  fi
fi

# ── git 추적 ─────────────────────────────────────────────────────────────────
if [ "$WORKLOG_DEST" = "git" ]; then
  header "Git 추적"

  echo "  1) .worklogs/ 를 git에 추적 (기본)"
  echo "  2) .worklogs/ 를 .gitignore에 추가"
  echo ""
  echo -n "선택 [1]: "
  read -r GIT_CHOICE
  GIT_CHOICE="${GIT_CHOICE:-1}"

  if [ "$GIT_CHOICE" = "2" ]; then
    WORKLOG_GIT_TRACK="false"
  else
    WORKLOG_GIT_TRACK="true"
  fi
fi

# ── 작성 시점 ────────────────────────────────────────────────────────────────
header "워크로그 작성 시점"

echo "  1) each-commit — 커밋할 때마다 자동 (추천)"
echo "  2) session-end — 세션 종료 시"
echo "  3) manual      — /worklog 실행할 때만"
echo ""
echo -n "선택 [1]: "
read -r TIMING_CHOICE
TIMING_CHOICE="${TIMING_CHOICE:-1}"

case "$TIMING_CHOICE" in
  2) WORKLOG_TIMING="session-end" ;;
  3) WORKLOG_TIMING="manual" ;;
  *) WORKLOG_TIMING="each-commit" ;;
esac

# ── 파일 복사 ────────────────────────────────────────────────────────────────
header "파일 설치"

# 스크립트/문서: 항상 덮어쓰기 (패키지 관리 파일, 사용자 수정 X)
copy_file() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -f "$dst" ]; then
    cp "$dst" "${dst}.bak"
    warn "기존 파일 백업: ${dst}.bak"
  fi
  cp "$src" "$dst"
  ok "$(basename "$dst")"
}

# 훅: 관리 블록(# --- ai-worklog start/end ---)만 교체, 나머지 보존
install_file() {
  local src="$1" dst="$2"
  local START="# --- ai-worklog start ---"
  local END="# --- ai-worklog end ---"

  mkdir -p "$(dirname "$dst")"

  if [ ! -f "$dst" ]; then
    cp "$src" "$dst"
    ok "$(basename "$dst") (새로 설치)"
    return
  fi

  python3 - "$src" "$dst" "$START" "$END" <<'PYEOF'
import sys

src_path     = sys.argv[1]
dst_path     = sys.argv[2]
start_marker = sys.argv[3]
end_marker   = sys.argv[4]

src = open(src_path, encoding='utf-8').read()
dst = open(dst_path, encoding='utf-8').read()

s_start = src.find(start_marker)
s_end   = src.find(end_marker)

if s_start == -1 or s_end == -1:
    # 소스에 관리 블록 없으면 전체 교체
    open(dst_path, 'w', encoding='utf-8').write(src)
    sys.exit(0)

managed_block = src[s_start : s_end + len(end_marker)]

d_start = dst.find(start_marker)
d_end   = dst.find(end_marker)

if d_start != -1 and d_end != -1:
    # 기존 관리 블록 교체
    new_dst = dst[:d_start] + managed_block + dst[d_end + len(end_marker):]
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

  ok "$(basename "$dst") (관리 블록 업데이트)"
}

# scripts (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/scripts/notion-worklog.sh"          "$TARGET_DIR/scripts/notion-worklog.sh"
copy_file "$PACKAGE_DIR/scripts/notion-migrate-worklogs.sh" "$TARGET_DIR/scripts/notion-migrate-worklogs.sh"
copy_file "$PACKAGE_DIR/scripts/duration.py"                "$TARGET_DIR/scripts/duration.py"

# hooks (관리 블록만 교체)
install_file "$PACKAGE_DIR/hooks/worklog.sh" "$TARGET_DIR/hooks/worklog.sh"

# commands (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/commands/worklog.md"          "$TARGET_DIR/commands/worklog.md"
copy_file "$PACKAGE_DIR/commands/migrate-worklogs.md" "$TARGET_DIR/commands/migrate-worklogs.md"

# rules (항상 덮어쓰기)
copy_file "$PACKAGE_DIR/rules/worklog-rules.md" "$TARGET_DIR/rules/worklog-rules.md"

# 실행 권한
chmod +x "$TARGET_DIR/scripts/notion-worklog.sh"
chmod +x "$TARGET_DIR/scripts/notion-migrate-worklogs.sh"
chmod +x "$TARGET_DIR/hooks/worklog.sh"

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
  ok ".env 설정 완료 (권한: 600)"
fi

# ── settings.json 훅 머지 ───────────────────────────────────────────────────
header "settings.json 설정"

SETTINGS_FILE="$TARGET_DIR/settings.json"

python3 - "$SETTINGS_FILE" "$TARGET_DIR" "$WORKLOG_TIMING" "$WORKLOG_DEST" "$WORKLOG_GIT_TRACK" "${NOTION_DB_ID:-}" <<'PYEOF'
import json, sys, os

settings_file = sys.argv[1]
target_dir    = sys.argv[2]
timing        = sys.argv[3]
dest          = sys.argv[4]
git_track     = sys.argv[5]
notion_db_id  = sys.argv[6]

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
env['AI_WORKLOG_DIR']    = target_dir
if notion_db_id:
    env['NOTION_DB_ID'] = notion_db_id

# ── hooks 머지 ──
hooks = cfg.setdefault('hooks', {})

# 훅 정의: (이벤트, command, timeout, async)
hook_defs = [
    ('PostToolUse', f'{target_dir}/hooks/worklog.sh', 5, True),
]

for event, command, timeout, is_async in hook_defs:
    event_hooks = hooks.setdefault(event, [])

    # 중복 체크: 같은 command가 이미 있는지
    already_exists = False
    for group in event_hooks:
        for h in group.get('hooks', []):
            if h.get('command', '').rstrip() == command:
                already_exists = True
                break
        if already_exists:
            break

    if not already_exists:
        new_hook = {
            'type': 'command',
            'command': command,
            'timeout': timeout,
        }
        if is_async:
            new_hook['async'] = True

        event_hooks.append({'hooks': [new_hook]})
        print(f'  ✓ {event} 훅 추가: {os.path.basename(command)}')
    else:
        print(f'  · {event} 훅 이미 존재: {os.path.basename(command)}')

# 저장
with open(settings_file, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f'\n  설정 저장: {settings_file}')
PYEOF

ok "settings.json 업데이트 완료"

# ── .gitignore에 .worklogs/ 추가 (git 미추적 모드) ──────────────────────────
if [ "$WORKLOG_GIT_TRACK" = "false" ] && [ "$SCOPE" = "local" ]; then
  GITIGNORE="$(git rev-parse --show-toplevel 2>/dev/null)/.gitignore"
  if [ -n "$GITIGNORE" ] && ! grep -q "^\.worklogs/" "$GITIGNORE" 2>/dev/null; then
    echo ".worklogs/" >> "$GITIGNORE"
    ok ".gitignore에 .worklogs/ 추가"
  fi
fi

# ── 완료 ─────────────────────────────────────────────────────────────────────
header "설치 완료"

echo -e "  ${BOLD}설정 요약${NC}"
echo "  ├─ 범위:     $SCOPE ($TARGET_DIR)"
echo "  ├─ 저장:     $WORKLOG_DEST"
echo "  ├─ git 추적: $WORKLOG_GIT_TRACK"
echo "  ├─ 시점:     $WORKLOG_TIMING"
if [ -n "$NOTION_DB_ID" ]; then
echo "  ├─ Notion DB: $NOTION_DB_ID"
fi
echo "  └─ 훅:       PostToolUse"

echo ""
echo -e "  ${BOLD}사용법${NC}"
echo "  • /worklog           — 워크로그 수동 작성"
echo "  • /migrate-worklogs  — 기존 .worklogs/ → Notion 마이그레이션"
echo ""
echo -e "  ${BOLD}재설정${NC}"
echo "  • $PACKAGE_DIR/install.sh --reconfigure"
echo ""
ok "ai-worklog 설치가 완료되었습니다!"
