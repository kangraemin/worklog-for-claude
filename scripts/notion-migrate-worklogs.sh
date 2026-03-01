#!/bin/bash
# 기존 .worklogs/*.md 파일을 Notion DB로 마이그레이션
# Usage: notion-migrate-worklogs.sh [--dry-run] [--date YYYY-MM-DD] [--delete-after] [--set-mode <mode>] <worklogs_dir>
#
# --dry-run        : 실제 전송 없이 파싱 결과만 출력
# --date           : 특정 날짜 파일만 처리 (예: 2026-02-23)
# --delete-after   : 마이그레이션 성공한 파일의 MD 삭제
# --set-mode <mode>: 마이그레이션 후 워크로그 저장 방식 변경
#                    notion-only | git | git-ignore | both

set -euo pipefail

# .env 탐색: AI_WORKLOG_DIR/.env → ~/.claude/.env fallback
if [ -n "${AI_WORKLOG_DIR:-}" ] && [ -f "$AI_WORKLOG_DIR/.env" ]; then
  ENV_FILE="$AI_WORKLOG_DIR/.env"
else
  ENV_FILE="$HOME/.claude/.env"
fi
if [ -f "$ENV_FILE" ]; then
  set -a; source "$ENV_FILE"; set +a
fi

DRY_RUN=false
TARGET_DATE=""
DELETE_AFTER=false
SET_MODE=""
WORKLOGS_DIR=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)      DRY_RUN=true; shift ;;
    --date)         TARGET_DATE="$2"; shift 2 ;;
    --delete-after) DELETE_AFTER=true; shift ;;
    --set-mode)     SET_MODE="$2"; shift 2 ;;
    *) WORKLOGS_DIR="$1"; shift ;;
  esac
done

if [ -z "$WORKLOGS_DIR" ]; then
  echo "Usage: $0 [--dry-run] [--date YYYY-MM-DD] [--delete-after] [--set-mode <mode>] <worklogs_dir>" >&2
  exit 1
fi

# --set-mode 유효성 검사
if [ -n "$SET_MODE" ]; then
  case "$SET_MODE" in
    notion-only|git|git-ignore|both) ;;
    *)
      echo "ERROR: --set-mode 값은 notion-only | git | git-ignore | both 중 하나" >&2
      exit 1
      ;;
  esac
fi

if [ ! -d "$WORKLOGS_DIR" ]; then
  echo "ERROR: 디렉토리 없음: $WORKLOGS_DIR" >&2
  exit 1
fi

if [ "$DRY_RUN" = false ]; then
  if [ -z "${NOTION_TOKEN:-}" ]; then
    echo "ERROR: NOTION_TOKEN 필요 (.env에 설정)" >&2
    exit 1
  fi
  if [ -z "${NOTION_DB_ID:-}" ]; then
    echo "ERROR: NOTION_DB_ID 필요 (settings.json env에 설정)" >&2
    exit 1
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 - "$WORKLOGS_DIR" "$TARGET_DATE" "$DRY_RUN" "$DELETE_AFTER" "$SCRIPT_DIR" \
  "${NOTION_TOKEN:-}" "${NOTION_DB_ID:-}" <<'PYEOF'
import sys, os, re, subprocess

worklogs_dir = sys.argv[1]
target_date  = sys.argv[2]
dry_run      = sys.argv[3] == "true"
delete_after = sys.argv[4] == "true"
script_dir   = sys.argv[5]
notion_token = sys.argv[6]
notion_db_id = sys.argv[7]

# ── 파서 ────────────────────────────────────────────────────────────────────

def parse_number(s):
    """'56,550,853' → 56550853"""
    return int(re.sub(r'[^\d]', '', s))

def parse_cost(s):
    """'$37.47' → 37.47"""
    return float(re.sub(r'[^\d.]', '', s))

def parse_token_section(text):
    """토큰 사용량 섹션 → dict"""
    result = {
        'model': 'claude-opus-4-6',
        'tokens': 0,
        'cost': 0.0,
        'duration': 0,
        'daily_tokens': 0,
        'daily_cost': 0.0,
    }
    for line in text.split('\n'):
        line = line.strip().lstrip('- ')
        if line.startswith('모델:'):
            result['model'] = line.split(':', 1)[1].strip()
        elif line.startswith('이번 작업:'):
            m = re.search(r'([\d,]+)\s*토큰\s*/\s*\$([\d.]+)', line)
            if m:
                result['tokens'] = parse_number(m.group(1))
                result['cost']   = float(m.group(2))
            else:
                m2 = re.search(r'\$([\d.]+)', line)
                if m2:
                    result['cost'] = float(m2.group(1))
        elif line.startswith('소요 시간:'):
            m = re.search(r'(\d+)', line)
            if m:
                result['duration'] = int(m.group(1))
        elif line.startswith('일일 누적:'):
            m = re.search(r'([\d,]+)\s*토큰\s*/\s*\$([\d.]+)', line)
            if m:
                result['daily_tokens'] = parse_number(m.group(1))
                result['daily_cost']   = float(m.group(2))
    return result

def parse_entry(date, project, entry_text):
    """## HH:MM 블록 하나를 파싱 → dict 또는 None"""
    lines = entry_text.strip().split('\n')
    if not lines:
        return None

    time_match = re.match(r'^## (\d{2}:\d{2})', lines[0])
    if not time_match:
        return None
    time_str = time_match.group(1)

    # 섹션 분리
    sections = {}
    cur_name, cur_lines = None, []
    for line in lines[1:]:
        if line.startswith('### '):
            if cur_name is not None:
                sections[cur_name] = '\n'.join(cur_lines).strip()
            cur_name  = line[4:].strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_name is not None:
        sections[cur_name] = '\n'.join(cur_lines).strip()

    # 타이틀: 요청사항 > 작업 내용 첫 bullet
    title = f"{date} {time_str}"
    for sec in ['요청사항', '작업 내용']:
        for line in sections.get(sec, '').split('\n'):
            line = line.strip().lstrip('- ')
            if line:
                title = line[:100]
                break
        if title != f"{date} {time_str}":
            break

    # 토큰 파싱
    token_info = parse_token_section(sections.get('토큰 사용량', ''))

    # 전달할 content 구성 (일일 누적 / 소요 시간 라인 제거)
    def clean_token_section(text):
        lines = [l for l in text.split('\n')
                 if not re.search(r'일일 누적|소요 시간', l)]
        return '\n'.join(lines).strip()

    parts = []
    for sec in ['요청사항', '작업 내용', '변경 파일', '토큰 사용량']:
        raw = sections.get(sec, '').strip()
        if not raw:
            continue
        cleaned = clean_token_section(raw) if sec == '토큰 사용량' else raw
        if cleaned:
            parts.append(f"### {sec}\n{cleaned}")
    content = '\n\n'.join(parts)

    return {
        'date':         date,
        'time':         time_str,
        'project':      project,
        'title':        title,
        'content':      content,
        **token_info,
    }

def parse_file(filepath):
    """md 파일 전체 → [entry, ...]"""
    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    date    = os.path.basename(filepath).replace('.md', '')
    project = '.claude'
    m = re.match(r'^# Worklog:\s*(.+?)\s*—', text)
    if m:
        project = m.group(1).strip()

    # ## HH:MM 단위로 분리
    blocks, current = [], []
    for line in text.split('\n'):
        if re.match(r'^## \d{2}:\d{2}', line) and current:
            blocks.append('\n'.join(current))
            current = [line]
        elif re.match(r'^## \d{2}:\d{2}', line):
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append('\n'.join(current))

    entries = []
    for block in blocks:
        e = parse_entry(date, project, block)
        if e:
            entries.append(e)
    return entries

# ── 마이그레이션 ─────────────────────────────────────────────────────────────

md_files = sorted([
    f for f in os.listdir(worklogs_dir)
    if f.endswith('.md') and re.match(r'^\d{4}-\d{2}-\d{2}\.md$', f)
])
if target_date:
    md_files = [f for f in md_files if f == f"{target_date}.md"]
    if not md_files:
        print(f"ERROR: {target_date}.md 파일 없음", file=sys.stderr)
        sys.exit(1)

total, success, failed = 0, 0, 0
deleted_files = []

env = {**os.environ, 'NOTION_TOKEN': notion_token, 'NOTION_DB_ID': notion_db_id}

for filename in md_files:
    filepath     = os.path.join(worklogs_dir, filename)
    entries      = parse_file(filepath)
    file_failed  = 0
    print(f"\n📄 {filename}  ({len(entries)} entries)")

    for e in entries:
        # 내용 없는 항목 스킵 (title이 "YYYY-MM-DD HH:MM" 패턴 = 내용 없음)
        if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$', e['title']):
            print(f"  ⏭  [{e['time']}] (내용 없음, 스킵)")
            continue

        total += 1
        label = f"  [{e['time']}] {e['title'][:55]}"

        if dry_run:
            print(f"  ▷ [{e['time']}] {e['title'][:55]}")
            print(f"        model={e['model']}  cost=${e['cost']}  tokens={e['tokens']}  duration={e['duration']}m")
            success += 1
            continue

        datetime_str = f"{e['date']}T{e['time']}:00+09:00"
        result = subprocess.run(
            [
                "bash", os.path.join(script_dir, "notion-worklog.sh"),
                e['title'], e['date'], e['project'],
                str(round(e['cost'], 3)), str(e['duration']),
                e['model'], str(e['tokens']),
                datetime_str, e['content'],
            ],
            capture_output=True, text=True, env=env
        )
        if result.returncode == 0:
            print(f"  ✅ {label}")
            success += 1
        else:
            print(f"  ❌ {label}")
            print(f"     {result.stderr.strip()}")
            failed += 1
            file_failed += 1

    # 파일 전체 성공 시에만 삭제
    if delete_after and not dry_run and file_failed == 0 and entries:
        os.remove(filepath)
        deleted_files.append(filename)
        print(f"  🗑  {filename} 삭제됨")

tag = "[DRY RUN] " if dry_run else ""
fail_str = f", {failed} 실패" if failed else ""
print(f"\n{tag}완료: {success}/{total} 처리됨{fail_str}")

if delete_after and deleted_files:
    print(f"삭제된 파일 ({len(deleted_files)}개): {', '.join(deleted_files)}")
elif delete_after and not dry_run and not deleted_files:
    print("삭제된 파일 없음 (실패한 항목이 있는 파일은 보존됨)")

if failed:
    sys.exit(1)
PYEOF

# ── --set-mode 처리 ────────────────────────────────────────────────────────
if [ -n "$SET_MODE" ]; then
  # settings.json 탐색: 로컬 .claude/settings.json → 전역 ~/.claude/settings.json
  if [ -f ".claude/settings.json" ]; then
    SETTINGS_FILE="./.claude/settings.json"
  else
    SETTINGS_FILE="$HOME/.claude/settings.json"
  fi
  python3 - "$SETTINGS_FILE" "$SET_MODE" <<'SETEOF'
import sys, json

settings_file = sys.argv[1]
mode          = sys.argv[2]

with open(settings_file, encoding='utf-8') as f:
    cfg = json.load(f)

env = cfg.setdefault('env', {})

if mode == 'notion-only':
    env['WORKLOG_DEST']      = 'notion-only'
    env['WORKLOG_GIT_TRACK'] = 'false'
elif mode == 'git':
    env['WORKLOG_DEST']      = 'git'
    env['WORKLOG_GIT_TRACK'] = 'true'
elif mode == 'git-ignore':
    env['WORKLOG_DEST']      = 'git'
    env['WORKLOG_GIT_TRACK'] = 'false'
elif mode == 'both':
    env['WORKLOG_DEST']      = 'notion'
    env['WORKLOG_GIT_TRACK'] = 'true'

with open(settings_file, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')

labels = {
    'notion-only': 'Notion에만 기록',
    'git':         '파일로만 기록 (git 추적)',
    'git-ignore':  '파일로만 기록 (git 미추적)',
    'both':        '파일 + Notion 모두 기록',
}
print(f"\n⚙  워크로그 모드 변경: {labels[mode]}")
print(f"   WORKLOG_DEST={env['WORKLOG_DEST']}  WORKLOG_GIT_TRACK={env['WORKLOG_GIT_TRACK']}")
print(f"   ({settings_file} 업데이트 완료)")
SETEOF
fi
