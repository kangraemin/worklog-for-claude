#!/bin/bash
# worklog-for-claude uninstaller
# Usage: ./uninstall.sh [--global | --local | --target <dir>]

set -euo pipefail

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

# ── 대상 디렉토리 결정 ──────────────────────────────────────────────────────
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --global) TARGET_DIR="$HOME/.claude"; shift ;;
    --local)  TARGET_DIR="$(pwd)/.claude"; shift ;;
    --target) TARGET_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [ -z "$TARGET_DIR" ]; then
  # AI_WORKLOG_DIR 환경변수에서 감지
  if [ -n "${AI_WORKLOG_DIR:-}" ]; then
    TARGET_DIR="$AI_WORKLOG_DIR"
  else
    echo "제거 대상을 선택하세요:"
    echo "  1) 전역 (~/.claude/)"
    echo "  2) 로컬 (.claude/)"
    echo ""
    echo -n "선택 [1]: "
    read -r CHOICE
    CHOICE="${CHOICE:-1}"
    if [ "$CHOICE" = "2" ]; then
      TARGET_DIR="$(pwd)/.claude"
    else
      TARGET_DIR="$HOME/.claude"
    fi
  fi
fi

SETTINGS_FILE="$TARGET_DIR/settings.json"

if [ ! -f "$SETTINGS_FILE" ]; then
  err "settings.json 없음: $SETTINGS_FILE"
  err "worklog-for-claude가 설치되어 있지 않은 것 같습니다."
  exit 1
fi

header "worklog-for-claude 제거"
info "대상: $TARGET_DIR"

# ── settings.json에서 훅 + 환경변수 제거 ────────────────────────────────────
header "settings.json 정리"

python3 - "$SETTINGS_FILE" "$TARGET_DIR" <<'PYEOF'
import json, sys, os

settings_file = sys.argv[1]
target_dir    = sys.argv[2]

with open(settings_file, encoding='utf-8') as f:
    cfg = json.load(f)

# ── 훅 제거 ──
hooks = cfg.get('hooks', {})
worklog_commands = [
    f'{target_dir}/hooks/worklog.sh',
    f'{target_dir}/hooks/session-end.sh',
    f'{target_dir}/hooks/stop.sh',
]
stop_markers = ['stop.sh', '/finish']

removed_hooks = []
for event in list(hooks.keys()):
    groups = hooks[event]
    new_groups = []
    for group in groups:
        new_hooks = []
        for h in group.get('hooks', []):
            cmd = h.get('command', '').rstrip()
            prompt = h.get('prompt', '')
            # command type: worklog_commands에 해당하면 제거
            if cmd in worklog_commands:
                continue
            # prompt/command type Stop hook: 마커 포함하면 제거
            if event == 'Stop' and any(m in cmd or m in prompt for m in stop_markers):
                continue
            new_hooks.append(h)
        if new_hooks:
            group['hooks'] = new_hooks
            new_groups.append(group)
        else:
            removed_hooks.append(event)
    if new_groups:
        hooks[event] = new_groups
    else:
        del hooks[event]
        removed_hooks.append(event)

for event in set(removed_hooks):
    print(f'  ✓ {event} 훅 제거')

# ── 환경변수 제거 ──
env = cfg.get('env', {})
remove_keys = ['WORKLOG_TIMING', 'WORKLOG_DEST', 'WORKLOG_GIT_TRACK', 'WORKLOG_LANG', 'AI_WORKLOG_DIR']
for key in remove_keys:
    if key in env:
        del env[key]
        print(f'  ✓ env.{key} 제거')

# NOTION_DB_ID, NOTION_TOKEN은 보존

with open(settings_file, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f'\n  설정 저장: {settings_file}')
PYEOF

ok "settings.json 정리 완료"

# ── 파일 삭제 ────────────────────────────────────────────────────────────────
header "파일 제거"

remove_file() {
  if [ -f "$1" ]; then
    rm "$1"
    ok "삭제: $(basename "$1")"
  fi
}

remove_file "$TARGET_DIR/scripts/notion-worklog.sh"
remove_file "$TARGET_DIR/scripts/notion-migrate-worklogs.sh"
remove_file "$TARGET_DIR/scripts/duration.py"
remove_file "$TARGET_DIR/scripts/token-cost.py"
remove_file "$TARGET_DIR/scripts/update-check.sh"
remove_file "$TARGET_DIR/scripts/worklog-write.sh"
remove_file "$TARGET_DIR/hooks/worklog.sh"
remove_file "$TARGET_DIR/hooks/session-end.sh"
remove_file "$TARGET_DIR/hooks/stop.sh"
remove_file "$TARGET_DIR/hooks/post-commit.sh"
remove_file "$TARGET_DIR/commands/worklog.md"
remove_file "$TARGET_DIR/commands/migrate-worklogs.md"
remove_file "$TARGET_DIR/commands/update-worklog.md"
remove_file "$TARGET_DIR/commands/finish.md"
remove_file "$TARGET_DIR/rules/worklog-rules.md"
remove_file "$TARGET_DIR/rules/auto-commit-rules.md"
remove_file "$TARGET_DIR/.version"
remove_file "$TARGET_DIR/.version-checked"

# 빈 디렉토리 정리
for dir in scripts hooks commands rules; do
  if [ -d "$TARGET_DIR/$dir" ] && [ -z "$(ls -A "$TARGET_DIR/$dir" 2>/dev/null)" ]; then
    rmdir "$TARGET_DIR/$dir"
    ok "빈 디렉토리 삭제: $dir/"
  fi
done

# ── 워크로그 데이터 ─────────────────────────────────────────────────────────
if [ -d ".worklogs" ] || [ -d "$TARGET_DIR/../.worklogs" ]; then
  echo ""
  warn "워크로그 데이터(.worklogs/)는 보존됩니다."
  echo -n "   삭제하시겠습니까? [y/N] "
  read -r DELETE_DATA
  if [[ "$DELETE_DATA" =~ ^[yY]$ ]]; then
    if [ -d ".worklogs" ]; then
      rm -rf ".worklogs"
      ok ".worklogs/ 삭제"
    fi
  else
    info ".worklogs/ 보존됨"
  fi
fi

# ── .env 정리 ────────────────────────────────────────────────────────────────
# .env에서 NOTION_TOKEN 제거 여부는 사용자에게 맡김 (다른 용도일 수 있음)

# ── 백업 파일 정리 ───────────────────────────────────────────────────────────
BAK_COUNT=$(find "$TARGET_DIR" -name "*.bak" -maxdepth 2 2>/dev/null | wc -l | tr -d ' ')
if [ "$BAK_COUNT" -gt 0 ]; then
  echo ""
  echo -n "   백업 파일(*.bak) $BAK_COUNT개를 삭제하시겠습니까? [y/N] "
  read -r DELETE_BAK
  if [[ "$DELETE_BAK" =~ ^[yY]$ ]]; then
    find "$TARGET_DIR" -name "*.bak" -maxdepth 2 -delete
    ok "백업 파일 삭제"
  fi
fi

# ── 완료 ─────────────────────────────────────────────────────────────────────
header "제거 완료"
ok "worklog-for-claude가 제거되었습니다."
info "settings.json의 NOTION_DB_ID, NOTION_TOKEN은 보존됩니다."
info "필요하면 수동으로 삭제하세요."
