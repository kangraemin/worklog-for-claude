#!/bin/bash
# worklog-for-claude uninstaller
# Usage: ./uninstall.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()     { echo -e "${GREEN}✓${NC}  $*"; }
info()   { echo -e "${BLUE}ℹ${NC}  $*"; }
warn()   { echo -e "${YELLOW}⚠${NC}  $*"; }
err()    { echo -e "${RED}✗${NC}  $*" >&2; }
header() { echo -e "\n${BOLD}${CYAN}── $* ──${NC}\n"; }

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

# ── 설치 범위 감지 ──────────────────────────────────────────────────────────
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
TARGET_DIR=""
SCOPE=""

# 로컬 설치 확인
if [ -n "$REPO_ROOT" ] && [ -f "$REPO_ROOT/.claude/hooks/post-commit.sh" ]; then
  TARGET_DIR="$REPO_ROOT/.claude"
  SCOPE="local"
fi

# 전역 설치 확인
if [ -z "$TARGET_DIR" ] && [ -f "$HOME/.claude/hooks/post-commit.sh" ]; then
  TARGET_DIR="$HOME/.claude"
  SCOPE="global"
fi

if [ -z "$TARGET_DIR" ]; then
  err "worklog-for-claude installation not found."
  exit 1
fi

header "worklog-for-claude 제거 ($SCOPE: $TARGET_DIR)"

# ── 설치된 파일 삭제 ────────────────────────────────────────────────────────
header "파일 제거"

WORKLOG_FILES=(
  # scripts
  "scripts/worklog-write.sh"
  "scripts/notion-worklog.sh"
  "scripts/notion-migrate-worklogs.sh"
  "scripts/notion-create-db.sh"
  "scripts/token-cost.py"
  "scripts/duration.py"
  "scripts/worklog-update-check.sh"
  # hooks
  "hooks/post-commit.sh"
  "hooks/worklog.sh"
  "hooks/on-commit.sh"
  "hooks/commit-doc-check.sh"
  "hooks/session-end.sh"
  "hooks/stop.sh"
  # commands
  "commands/worklog.md"
  "commands/worklog-migrate.md"
  "commands/worklog-update.md"
  "commands/worklog-config.md"
  # rules
  "rules/worklog-rules.md"
  "rules/auto-commit-rules.md"
  # git-hooks
  "git-hooks/post-commit"
  # version
  ".version"
)

REMOVED=0
PRESERVED=0
for rel_path in "${WORKLOG_FILES[@]}"; do
  full_path="$TARGET_DIR/$rel_path"
  [ -f "$full_path" ] || continue

  # .bak 파일 제거
  rm -f "${full_path}.bak"

  if grep -q "worklog-for-claude start" "$full_path" 2>/dev/null; then
    # 마커 블록 제거
    sed '/# --- worklog-for-claude start ---/,/# --- worklog-for-claude end ---/d' "$full_path" > "${full_path}.tmp"
    mv "${full_path}.tmp" "$full_path"

    # 남은 내용 확인 (shebang + 빈줄 + 주석만 남으면 전체 삭제)
    has_content=$(grep -v '^#!' "$full_path" | grep -v '^\s*$' | grep -v '^\s*#' | head -1 || true)
    if [ -z "$has_content" ]; then
      rm -f "$full_path"
      ok "  $rel_path"
      REMOVED=$((REMOVED + 1))
    else
      ok "  $rel_path (마커 블록만 제거)"
      PRESERVED=$((PRESERVED + 1))
    fi
  else
    # 마커 없음 → 전체 삭제
    rm -f "$full_path"
    ok "  $rel_path"
    REMOVED=$((REMOVED + 1))
  fi
done

info "$REMOVED files removed, $PRESERVED files preserved (marker block only)"

# ── settings.json에서 worklog hooks/env 제거 ────────────────────────────────
header "settings.json 정리"

SETTINGS_FILE="$TARGET_DIR/settings.json"

if [ -f "$SETTINGS_FILE" ]; then
  $PYTHON - "$SETTINGS_FILE" <<'PYEOF'
import json, sys, os, re

settings_file = sys.argv[1]

try:
    with open(settings_file, encoding='utf-8') as f:
        cfg = json.load(f)
except Exception:
    print("  ⚠ settings.json 읽기 실패")
    sys.exit(0)

# hooks 제거: worklog 관련 command 패턴
WORKLOG_MARKERS = [
    'worklog.sh', 'on-commit.sh', 'commit-doc-check.sh',
    'session-end.sh', 'stop.sh', 'worklog-update-check.sh', 'post-commit.sh'
]

hooks = cfg.get('hooks', {})
for event in list(hooks.keys()):
    event_hooks = hooks[event]
    filtered = []
    for group in event_hooks:
        group_hooks = group.get('hooks', [])
        remaining = [
            h for h in group_hooks
            if not any(m in h.get('command', '') for m in WORKLOG_MARKERS)
        ]
        if remaining:
            group['hooks'] = remaining
            filtered.append(group)
    if filtered:
        hooks[event] = filtered
    else:
        del hooks[event]

print("  ✓ worklog hooks removed")

# env 제거
WORKLOG_ENV_KEYS = [
    'WORKLOG_TIMING', 'WORKLOG_DEST', 'WORKLOG_GIT_TRACK',
    'WORKLOG_LANG', 'AI_WORKLOG_DIR', 'NOTION_DB_ID',
    'PROJECT_DOC_CHECK_INTERVAL'
]

env = cfg.get('env', {})
removed_keys = []
for key in WORKLOG_ENV_KEYS:
    if key in env:
        del env[key]
        removed_keys.append(key)

if removed_keys:
    print(f"  ✓ env keys removed: {', '.join(removed_keys)}")
else:
    print("  · no worklog env keys found")

# 빈 env/hooks 정리
if not env:
    cfg.pop('env', None)
if not hooks:
    cfg.pop('hooks', None)

with open(settings_file, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f"\n  Saved: {settings_file}")
PYEOF
  ok "settings.json updated"
else
  info "settings.json not found, skipping"
fi

# ── git hook 정리 ───────────────────────────────────────────────────────────
header "Git Hook 정리"

if [ "$SCOPE" = "global" ]; then
  CURRENT_HOOKS_PATH=$(git config --global core.hooksPath 2>/dev/null || true)
  if [ "$CURRENT_HOOKS_PATH" = "$TARGET_DIR/git-hooks" ]; then
    git config --global --unset core.hooksPath 2>/dev/null || true
    ok "core.hooksPath reset"
  else
    info "core.hooksPath points elsewhere ($CURRENT_HOOKS_PATH), not touching"
  fi
else
  REPO_GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || true)
  if [ -n "$REPO_GIT_DIR" ]; then
    LOCAL_HOOK="$REPO_GIT_DIR/hooks/post-commit"
    if [ -f "$LOCAL_HOOK" ] && grep -q "worklog-for-claude\|AI_WORKLOG_DIR\|post-commit.sh" "$LOCAL_HOOK" 2>/dev/null; then
      rm -f "$LOCAL_HOOK"
      ok "post-commit hook removed"
      # post-commit.local 복원
      if [ -f "${LOCAL_HOOK}.local" ]; then
        mv "${LOCAL_HOOK}.local" "$LOCAL_HOOK"
        ok "post-commit.local restored as post-commit"
      fi
    else
      info "post-commit hook not ours, not touching"
    fi
  fi
fi

# ── 빈 디렉토리 정리 ───────────────────────────────────────────────────────
for subdir in scripts hooks commands rules git-hooks; do
  dir="$TARGET_DIR/$subdir"
  if [ -d "$dir" ] && [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
    rmdir "$dir" 2>/dev/null || true
  fi
done

# ── 완료 ────────────────────────────────────────────────────────────────────
header "제거 완료"

echo "  Preserved:"
echo "  • .worklogs/ (worklog data)"
echo "  • .env (credentials)"
echo ""
ok "worklog-for-claude has been removed."
