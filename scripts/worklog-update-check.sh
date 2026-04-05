#!/bin/bash
# worklog-for-claude 자동 업데이트 체커
# Usage: worklog-update-check.sh [--force] [--check-only]
#   --force      : 24h throttle 무시하고 즉시 체크
#   --check-only : 버전 확인만 (업데이트 안 함)

set -euo pipefail

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

REPO="kangraemin/worklog-for-claude"
RAW_BASE="https://raw.githubusercontent.com/$REPO/main"
API_URL="https://api.github.com/repos/$REPO/commits/main"

AI_WORKLOG_DIR="${AI_WORKLOG_DIR:-$HOME/.claude}"
VERSION_FILE="$AI_WORKLOG_DIR/.version"
CHECKED_FILE="$AI_WORKLOG_DIR/.version-checked"

FORCE=false
CHECK_ONLY=false
for arg in "$@"; do
  case $arg in
    --force)      FORCE=true ;;
    --check-only) CHECK_ONLY=true ;;
  esac
done

# ── 누락 hook 검증 (매 세션) ──────────────────────────────────────────────────
_ensure_hook() {
  local sf="$1" event="$2" cmd="$3" timeout="$4" is_async="$5" matcher="${6:-}"
  [ -f "$sf" ] || return 0
  local basename
  basename=$(basename "$cmd")
  grep -q "$basename" "$sf" 2>/dev/null && return 0
  $PYTHON -c "
import json, sys
sf, event, cmd = sys.argv[1], sys.argv[2], sys.argv[3]
timeout, is_async, matcher = int(sys.argv[4]), sys.argv[5] == 'true', sys.argv[6]
cfg = json.load(open(sf))
hooks = cfg.setdefault('hooks', {})
entries = hooks.setdefault(event, [])
hook = {'type': 'command', 'command': cmd, 'timeout': timeout}
if is_async:
    hook['async'] = True
entry = {'hooks': [hook]}
if matcher:
    entry['matcher'] = matcher
entries.append(entry)
with open(sf, 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('added')
" "$sf" "$event" "$cmd" "$timeout" "$is_async" "$matcher" 2>/dev/null
  echo -e "${_G:-}✓${_N:-}  ${event} hook 등록: $basename" >&2
}

SETTINGS="$HOME/.claude/settings.json"
_ensure_hook "$SETTINGS" "PostToolUse"  "$AI_WORKLOG_DIR/hooks/worklog.sh"           5  true  ""     || true
_ensure_hook "$SETTINGS" "PostToolUse"  "$AI_WORKLOG_DIR/hooks/on-commit.sh"         5  false "Bash" || true
_ensure_hook "$SETTINGS" "PostToolUse"  "$AI_WORKLOG_DIR/hooks/commit-doc-check.sh"  5  false ""     || true
_ensure_hook "$SETTINGS" "SessionStart" "$AI_WORKLOG_DIR/scripts/worklog-update-check.sh"   15  true  ""     || true
_ensure_hook "$SETTINGS" "SessionEnd"   "$AI_WORKLOG_DIR/hooks/session-end.sh"      15  false ""     || true
_ensure_hook "$SETTINGS" "Stop"         "$AI_WORKLOG_DIR/hooks/stop.sh"             15  false ""     || true

# ── PROJECT.md 생성 안내 (프로젝트별 1회) ────────────────────────────────────
if git rev-parse --is-inside-work-tree &>/dev/null; then
  _PROJ_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
  _PROMPTED="$_PROJ_ROOT/.claude/.project-md-prompted"
  if [ ! -f "$_PROJ_ROOT/PROJECT.md" ] && [ ! -f "$_PROMPTED" ]; then
    mkdir -p "$_PROJ_ROOT/.claude"
    touch "$_PROMPTED"
    echo "💡 PROJECT.md가 없습니다. /update-project 를 실행하면 프로젝트 문서가 자동 생성됩니다."
  fi
fi

# ── 24시간 throttle ───────────────────────────────────────────────────────────
if [ "$FORCE" = false ] && [ "$CHECK_ONLY" = false ] && [ -f "$CHECKED_FILE" ]; then
  LAST=$(cat "$CHECKED_FILE" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  DIFF=$(( NOW - LAST ))
  if [ "$DIFF" -lt 86400 ]; then
    exit 0
  fi
fi

# ── 최신 SHA 조회 ────────────────────────────────────────────────────────────
LATEST_SHA=$(curl -sf --max-time 5 "$API_URL" 2>/dev/null | $PYTHON -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d['sha'][:7])
except:
    sys.exit(1)
" 2>/dev/null) || {
  # 네트워크 실패 시 조용히 종료
  exit 0
}

# 체크 타임스탬프 갱신
date +%s > "$CHECKED_FILE"

# ── 설치된 버전 확인 ─────────────────────────────────────────────────────────
INSTALLED_SHA=$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")

if [ "$CHECK_ONLY" = true ]; then
  echo "installed: $INSTALLED_SHA"
  echo "latest:    $LATEST_SHA"
  if [ "$LATEST_SHA" = "$INSTALLED_SHA" ]; then
    echo "status: up-to-date"
  else
    echo "status: update-available"
  fi
  exit 0
fi

# ── 업데이트 필요 없으면 종료 ────────────────────────────────────────────────
if [ "$LATEST_SHA" = "$INSTALLED_SHA" ]; then
  exit 0
fi

# ── bootstrap: 자기 자신을 먼저 업데이트 후 재실행 ────────────────────────────
# 옛날 버전의 FILES 배열이 불완전할 수 있으므로,
# 새 버전의 worklog-update-check.sh로 교체 후 재실행해서 전체 파일을 받는다.
SELF_SCRIPT="$AI_WORKLOG_DIR/scripts/worklog-update-check.sh"
if [ "${_UPDATE_BOOTSTRAPPED:-}" != "1" ]; then
  SELF_TMP=$(mktemp) || { echo "worklog-for-claude: mktemp failed" >&2; exit 0; }
  trap 'rm -f "$SELF_TMP"' EXIT
  if curl -sf --max-time 10 "$RAW_BASE/scripts/worklog-update-check.sh" -o "$SELF_TMP" 2>/dev/null; then
    # 무결성 검증: 비어있지 않고, 유효한 bash 구문이어야 함
    if [ -s "$SELF_TMP" ] && bash -n "$SELF_TMP" 2>/dev/null; then
      if ! cmp -s "$SELF_TMP" "$SELF_SCRIPT"; then
        mv "$SELF_TMP" "$SELF_SCRIPT"
        chmod +x "$SELF_SCRIPT"
        trap - EXIT
        export _UPDATE_BOOTSTRAPPED=1
        exec bash "$SELF_SCRIPT" --force
      fi
    else
      echo "worklog-for-claude: 다운로드 파일 검증 실패, 업데이트 건너뜀" >&2
    fi
  fi
  rm -f "$SELF_TMP"
  trap - EXIT
fi

# ── 파일 다운로드 + 교체 ─────────────────────────────────────────────────────
FILES=(
  # scripts
  "scripts/worklog-write.sh"
  "scripts/notion-worklog.sh"
  "scripts/notion-create-db.sh"
  "scripts/notion-migrate-worklogs.sh"
  "scripts/token-cost.py"
  "scripts/duration.py"
  "scripts/worklog-update-check.sh"
  # hooks
  "hooks/post-commit.sh"
  "hooks/on-commit.sh"
  "hooks/worklog.sh"
  "hooks/session-end.sh"
  "hooks/stop.sh"
  # git-hooks
  "git-hooks/post-commit"
  # commands
  "commands/worklog.md"
  "commands/worklog-update.md"
  "commands/worklog-migrate.md"
  "commands/worklog-config.md"
  # rules
  "rules/worklog-rules.md"
  "rules/auto-commit-rules.md"
  # install
  "install.sh"
)

_G='\033[0;32m' _D='\033[2m' _R='\033[0;31m' _B='\033[1m' _N='\033[0m'

FAILED=0
UPDATED=0
UNCHANGED=0
for file in "${FILES[@]}"; do
  dst="$AI_WORKLOG_DIR/$file"
  mkdir -p "$(dirname "$dst")"

  tmp=$(mktemp) || { FAILED=$(( FAILED + 1 )); continue; }
  if curl -sf --max-time 10 "$RAW_BASE/$file" -o "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
    # .sh 파일이면 bash 구문 검증
    if [[ "$file" == *.sh ]] && ! bash -n "$tmp" 2>/dev/null; then
      rm -f "$tmp"
      echo -e "${_R}✗${_N}  ${file} (구문 오류)" >&2
      FAILED=$(( FAILED + 1 ))
      continue
    fi
    if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then
      echo -e "${_D}·  ${file}${_N}" >&2
      UNCHANGED=$(( UNCHANGED + 1 ))
      rm -f "$tmp"
    else
      mv "$tmp" "$dst"
      chmod +x "$dst" 2>/dev/null || true
      echo -e "${_G}✓${_N}  ${file}" >&2
      UPDATED=$(( UPDATED + 1 ))
    fi
  else
    rm -f "$tmp"
    echo -e "${_R}✗${_N}  ${file}" >&2
    FAILED=$(( FAILED + 1 ))
  fi
done

if [ "$FAILED" -gt 0 ]; then
  echo "worklog-for-claude: 업데이트 일부 실패 ($FAILED개). 다음 실행 시 재시도합니다." >&2
  exit 0
fi

# ── post-update: WORKLOG_TIMING=each-commit → stop 마이그레이션 ──────────────
_migrate_timing() {
  local sf="$1"
  [ -f "$sf" ] || return 0
  $PYTHON -c "
import json, sys
sf = sys.argv[1]
with open(sf) as f: cfg = json.load(f)
env = cfg.get('env', {})
if env.get('WORKLOG_TIMING') == 'each-commit':
    env['WORKLOG_TIMING'] = 'stop'
    cfg['env'] = env
    with open(sf, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('migrated')
" "$sf" 2>/dev/null
}

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
for _sf in "$HOME/.claude/settings.json" ${REPO_ROOT:+"$REPO_ROOT/.claude/settings.json"}; do
  result=$(_migrate_timing "$_sf")
  [ "$result" = "migrated" ] && echo -e "${_G}✓${_N}  WORKLOG_TIMING: each-commit → stop ($_sf)" >&2
done

# ── post-update: git hook 재설치 ──────────────────────────────────────────────
HOOK_SRC="$AI_WORKLOG_DIR/git-hooks/post-commit"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [ -n "$REPO_ROOT" ] && [ -f "$HOOK_SRC" ]; then
  HOOK_DST="$REPO_ROOT/.git/hooks/post-commit"
  mkdir -p "$REPO_ROOT/.git/hooks"
  if [ -f "$HOOK_DST" ] && ! grep -q "ai-worklog" "$HOOK_DST" 2>/dev/null; then
    mv "$HOOK_DST" "$HOOK_DST.local"
  fi
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
fi

# ── 버전 파일 갱신 ───────────────────────────────────────────────────────────
echo "$LATEST_SHA" > "$VERSION_FILE"

echo -e "\n${_G}✓${_N}  ${_B}worklog-for-claude${_N} $INSTALLED_SHA → $LATEST_SHA — ${_G}${UPDATED}개 업데이트${_N}, ${_D}${UNCHANGED}개 변경 없음${_N}" >&2
echo "worklog-for-claude $INSTALLED_SHA → $LATEST_SHA 업데이트 완료 (${UPDATED}개 파일)"
