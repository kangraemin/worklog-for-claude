#!/bin/bash
# Notion API로 워크로그 엔트리를 DB에 생성 (작업별 1행)
# Usage: notion-worklog.sh <title> <date> <project> <cost> <duration_min> <model> <tokens> <datetime> <content>

set -euo pipefail

# .env 탐색: AI_WORKLOG_DIR/.env → ~/.claude/.env fallback
if [ -n "${AI_WORKLOG_DIR:-}" ] && [ -f "$AI_WORKLOG_DIR/.env" ]; then
  ENV_FILE="$AI_WORKLOG_DIR/.env"
else
  ENV_FILE="$HOME/.claude/.env"
fi
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

TITLE="${1:?title required}"
DATE="${2:?date required}"
PROJECT="${3:?project required}"
COST="${4:-0}"
DURATION="${5:-0}"
MODEL="${6:-claude-opus-4-6}"
TOKENS="${7:-0}"
DATETIME="${8:-}"
CONTENT="${9:-}"

if [ -z "${NOTION_TOKEN:-}" ]; then
  echo "ERROR: NOTION_TOKEN required (set in .env or env)" >&2
  exit 1
fi
if [ -z "${NOTION_DB_ID:-}" ]; then
  echo "ERROR: NOTION_DB_ID required (set in settings.json env)" >&2
  exit 1
fi

# 본문을 Notion blocks JSON으로 변환 (마크다운 → heading/bullet/paragraph)
CHILDREN_JSON=$(python3 - "$CONTENT" <<'PYEOF'
import sys, json

content = sys.argv[1] if len(sys.argv) > 1 else ''
blocks = []

for line in content.split('\n'):
    stripped = line.strip()
    if not stripped:
        continue

    text = stripped[:2000]

    if stripped.startswith('### '):
        blocks.append({
            'object': 'block',
            'type': 'heading_3',
            'heading_3': {'rich_text': [{'text': {'content': text[4:]}}]}
        })
    elif stripped.startswith('## '):
        blocks.append({
            'object': 'block',
            'type': 'heading_2',
            'heading_2': {'rich_text': [{'text': {'content': text[3:]}}]}
        })
    elif stripped.startswith('# '):
        blocks.append({
            'object': 'block',
            'type': 'heading_1',
            'heading_1': {'rich_text': [{'text': {'content': text[2:]}}]}
        })
    elif stripped.startswith('- '):
        blocks.append({
            'object': 'block',
            'type': 'bulleted_list_item',
            'bulleted_list_item': {'rich_text': [{'text': {'content': text[2:]}}]}
        })
    else:
        blocks.append({
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {'rich_text': [{'text': {'content': text}}]}
        })

print(json.dumps(blocks))
PYEOF
)

# API 페이로드 생성
PAYLOAD=$(python3 - "$NOTION_DB_ID" "$TITLE" "$DATE" "$PROJECT" "$COST" "$DURATION" "$MODEL" "$TOKENS" "$DATETIME" "$CHILDREN_JSON" <<'PYEOF'
import json, sys
cost     = round(float(sys.argv[5]), 3); cost     = cost     if cost     else None
duration = int(sys.argv[6]);             duration = duration if duration else None
tokens   = int(sys.argv[8]);             tokens   = tokens   if tokens   else None
datetime = sys.argv[9] if sys.argv[9] else None
data = {
    'parent': {'database_id': sys.argv[1]},
    'icon': {'type': 'emoji', 'emoji': '📖'},
    'properties': {
        'Title':    {'title': [{'text': {'content': sys.argv[2]}}]},
        'Date':     {'date': {'start': sys.argv[3]}},
        'Project':  {'select': {'name': sys.argv[4]}},
        'Cost':     {'number': cost},
        'Duration': {'number': duration},
        'Model':    {'select': {'name': sys.argv[7]}},
        'Tokens':   {'number': tokens},
        'DateTime': {'date': {'start': datetime}} if datetime else {'date': None},
    },
    'children': json.loads(sys.argv[10])
}
print(json.dumps(data))
PYEOF
)

# Notion API 호출
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "OK"
else
  echo "FAIL: HTTP $HTTP_CODE" >&2
  echo "$BODY" >&2
  exit 1
fi
