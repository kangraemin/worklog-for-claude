# ai-worklog

> Automatic work logging for [Claude Code](https://claude.com/claude-code) sessions.

Track what you built, how long it took, and what it cost — automatically, on every commit.

![Notion DB preview](docs/notion-preview.png)

## What it does

Every time you run `/commit` in Claude Code, ai-worklog:

1. Reads the current conversation context
2. Summarizes what was requested and what was done
3. Calculates token usage and cost delta from project JSONL
4. Writes an entry to `.worklogs/YYYY-MM-DD.md`
5. Optionally syncs to a Notion database

No manual journaling. No forgetting what you did last Tuesday.

## Install

```bash
git clone https://github.com/kangraemin/ai-worklog.git
cd ai-worklog
./install.sh
```

The interactive wizard configures:

- **Scope** — Global (`~/.claude/`) or project-local (`.claude/`)
- **Storage** — Local markdown, Notion, or both
- **Timing** — On each commit, session end, or manually
- **Git tracking** — Whether `.worklogs/` is committed with your code

## Usage

### Writing a worklog

```
/worklog
```

Appends an entry to `.worklogs/YYYY-MM-DD.md`:

```markdown
## 14:30

### 요청사항
- Add duplicate prevention to migration script

### 작업 내용
- Added .migrated fingerprint file to skip already-sent entries
- Updated skipped count in output summary

### 변경 파일
- `scripts/notion-migrate-worklogs.sh`: duplicate prevention logic

### 토큰 사용량
- 모델: claude-sonnet-4-6
- 이번 작업: $1.089
```

With `WORKLOG_TIMING=each-commit` (default), this runs automatically on every `/commit`.

### Migrating existing worklogs to Notion

```bash
/migrate-worklogs              # dry-run preview
/migrate-worklogs --all        # migrate all .md files
/migrate-worklogs --date 2026-03-01  # specific date only
```

Already-migrated entries are skipped automatically (tracked in `.worklogs/.migrated`).

## Configuration

Settings live in `settings.json` under `env`:

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `WORKLOG_TIMING` | `each-commit` / `session-end` / `manual` | `each-commit` | When to write worklogs |
| `WORKLOG_DEST` | `git` / `notion` / `notion-only` | `git` | Where to store worklogs |
| `WORKLOG_GIT_TRACK` | `true` / `false` | `true` | Track `.worklogs/` in git |
| `WORKLOG_LANG` | `ko` / `en` | `ko` | Worklog entry language |
| `NOTION_DB_ID` | UUID | — | Notion database ID |
| `AI_WORKLOG_DIR` | path | — | Install location (auto-set) |

### Storage modes

| Mode | `WORKLOG_DEST` | `WORKLOG_GIT_TRACK` | Result |
|------|---------------|---------------------|--------|
| `git` | `git` | `true` | Markdown files, committed |
| `git-ignore` | `git` | `false` | Markdown files, not committed |
| `notion` | `notion` | `true` | Markdown + Notion |
| `notion-only` | `notion-only` | `false` | Notion only |

### Notion setup

1. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Add `NOTION_TOKEN=secret_...` to `~/.claude/.env`
3. Run `./install.sh` — the wizard auto-creates the database

The database schema:

| Column | Type | Description |
|--------|------|-------------|
| Title | title | One-line work summary |
| Date | date | Work date |
| DateTime | date | Precise timestamp (for sorting) |
| Project | select | Repository name |
| Cost | number | Cost delta ($) |
| Tokens | number | Token delta |
| Duration | number | Actual Claude work time (minutes) |
| Model | select | Claude model used |

## Hooks

| Event | File | Description |
|-------|------|-------------|
| `PostToolUse` | `hooks/worklog.sh` | Collects tool usage into a per-session JSONL file |
| `SessionEnd` | `hooks/session-end.sh` | Cleans up the JSONL collection file |

## Uninstall

```bash
./uninstall.sh
```

Removes hooks, scripts, and env vars from `settings.json`. Preserves `.worklogs/` data and Notion credentials.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- `python3`, `curl`, `jq`

## License

MIT
