#!/bin/bash
# worklog-write.sh — 워크로그 작성 핵심 스크립트
# 모든 호출 경로(post-commit hook, /worklog 스킬)에서 이 스크립트를 사용한다.
#
# Usage:
#   worklog-write.sh <summary_file> [--project NAME] [--date YYYY-MM-DD] [--model MODEL]
#
#   summary_file: 요약 텍스트가 담긴 파일 경로 (- 이면 stdin)
#   summary에는 요청사항 + 작업내용이 포함되어야 함
#
# 환경변수:
#   AI_WORKLOG_DIR    스크립트 디렉토리 (필수)
#   WORKLOG_DEST      저장 대상: git | notion | notion-only
#   WORKLOG_GIT_TRACK git 추적 여부: true | false
#   WORKLOG_LANG      언어: ko | en
#   NOTION_DB_ID      Notion DB ID (notion 모드 시)

set -euo pipefail

# ── 파라미터 파싱 ─────────────────────────────────────────────────────────────
SUMMARY_FILE=""
PROJECT=""
DATE=$(date +%Y-%m-%d)
MODEL="claude-sonnet-4-6"

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --date)    DATE="$2"; shift 2 ;;
    --model)   MODEL="$2"; shift 2 ;;
    *)         SUMMARY_FILE="$1"; shift ;;
  esac
done

if [ -z "$SUMMARY_FILE" ]; then
  echo "Usage: worklog-write.sh <summary_file> [--project NAME] [--date YYYY-MM-DD] [--model MODEL]" >&2
  exit 1
fi

# 요약 텍스트 읽기
if [ "$SUMMARY_FILE" = "-" ]; then
  SUMMARY=$(cat)
else
  SUMMARY=$(cat "$SUMMARY_FILE")
fi

if [ -z "$SUMMARY" ]; then
  echo "Error: empty summary" >&2
  exit 1
fi

# ── 기본값 설정 ───────────────────────────────────────────────────────────────
AI_WORKLOG_DIR="${AI_WORKLOG_DIR:-$HOME/.claude}"
WORKLOG_DEST="${WORKLOG_DEST:-git}"
WORKLOG_GIT_TRACK="${WORKLOG_GIT_TRACK:-true}"
WORKLOG_LANG="${WORKLOG_LANG:-ko}"
PROJECT_CWD=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT="${PROJECT:-$(basename "$PROJECT_CWD")}"
TIMESTAMP=$(date +%H:%M)
DATETIME=$(date +%Y-%m-%dT%H:%M:00+09:00)

# ── 스냅샷 읽기 ──────────────────────────────────────────────────────────────
SNAPSHOT_DIR="$HOME/.claude/worklogs"
SNAPSHOT_FILE="$SNAPSHOT_DIR/.snapshot"
mkdir -p "$SNAPSHOT_DIR"

if [ -f "$SNAPSHOT_FILE" ]; then
  SNAPSHOT_TS=$(python3 -c "import json; print(json.load(open('$SNAPSHOT_FILE')).get('timestamp', 0))" 2>/dev/null || echo "0")
else
  SNAPSHOT_TS=0
fi

# ── 토큰/비용 계산 ───────────────────────────────────────────────────────────
TOKEN_COST_SCRIPT="$AI_WORKLOG_DIR/scripts/token-cost.py"
DURATION_SCRIPT="$AI_WORKLOG_DIR/scripts/duration.py"

TOKENS=0
COST="0.000"
DURATION_MIN=0

if [ -f "$TOKEN_COST_SCRIPT" ]; then
  TC_OUTPUT=$(python3 "$TOKEN_COST_SCRIPT" "$SNAPSHOT_TS" "$PROJECT_CWD" 2>/dev/null || echo "0,0.000")
  TOKENS=$(echo "$TC_OUTPUT" | cut -d, -f1)
  COST=$(echo "$TC_OUTPUT" | cut -d, -f2)
fi

if [ -f "$DURATION_SCRIPT" ]; then
  DUR_OUTPUT=$(python3 "$DURATION_SCRIPT" "$SNAPSHOT_TS" "$PROJECT_CWD" 2>/dev/null || echo "0,0")
  DURATION_MIN=$(echo "$DUR_OUTPUT" | cut -d, -f2)
fi

# ── 변경 파일 목록 ───────────────────────────────────────────────────────────
CHANGED_FILES=$(git diff HEAD~1 HEAD --stat 2>/dev/null || echo "")

# ── 워크로그 엔트리 조합 ─────────────────────────────────────────────────────
if [ "$WORKLOG_LANG" = "en" ]; then
  TOKEN_HEADER="### Token Usage"
  TOKEN_MODEL="- Model: $MODEL"
  TOKEN_COST_LINE="- This session: \$$COST"
else
  TOKEN_HEADER="### 토큰 사용량"
  TOKEN_MODEL="- 모델: $MODEL"
  TOKEN_COST_LINE="- 이번 작업: \$$COST"
fi

ENTRY="---

## $TIMESTAMP

$SUMMARY

$TOKEN_HEADER
$TOKEN_MODEL
$TOKEN_COST_LINE"

# ── 로컬 파일 저장 ───────────────────────────────────────────────────────────
if [ "$WORKLOG_DEST" != "notion-only" ]; then
  WORKLOG_DIR="$PROJECT_CWD/.worklogs"
  WORKLOG_FILE="$WORKLOG_DIR/$DATE.md"
  mkdir -p "$WORKLOG_DIR"

  # 파일 없으면 헤더 생성
  if [ ! -f "$WORKLOG_FILE" ]; then
    echo "# Worklog: $PROJECT — $DATE" > "$WORKLOG_FILE"
  fi

  echo "" >> "$WORKLOG_FILE"
  echo "$ENTRY" >> "$WORKLOG_FILE"

  # git 추적
  if [ "$WORKLOG_GIT_TRACK" = "true" ]; then
    git add "$WORKLOG_DIR/" 2>/dev/null || true
  fi
fi

# ── Notion 전송 ──────────────────────────────────────────────────────────────
NOTION_SCRIPT="$AI_WORKLOG_DIR/scripts/notion-worklog.sh"

if [ "$WORKLOG_DEST" = "notion" ] || [ "$WORKLOG_DEST" = "notion-only" ]; then
  if [ -f "$NOTION_SCRIPT" ] && [ -n "${NOTION_DB_ID:-}" ]; then
    # Title: 요약에서 첫 내용 줄 추출 (### 헤더 스킵, - 제거)
    TITLE=$(echo "$SUMMARY" | grep -v '^\s*$' | grep -v '^###' | head -1 | sed 's/^- //')

    bash "$NOTION_SCRIPT" \
      "$TITLE" \
      "$DATE" \
      "$PROJECT" \
      "$COST" \
      "$DURATION_MIN" \
      "$MODEL" \
      "$TOKENS" \
      "$DATETIME" \
      "$ENTRY" 2>/dev/null && echo "Notion 전송 완료" || echo "Notion 전송 실패" >&2
  fi
fi

# ── 스냅샷 갱신 ──────────────────────────────────────────────────────────────
NOW_TS=$(date +%s)
echo "{\"timestamp\":$NOW_TS}" > "$SNAPSHOT_FILE"

echo "워크로그 작성 완료: $DATE $TIMESTAMP"
