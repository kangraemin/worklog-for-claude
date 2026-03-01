# ai-worklog

Automatic work logging for [Claude Code](https://claude.com/claude-code) sessions.

Track what you build, how much it costs, and where the tokens go — with optional Notion integration.

## Features

- **Automatic logging** — Records work on each commit, session end, or manually
- **Token & cost tracking** — Tracks tokens, cost ($), and duration per task via [ccusage](https://github.com/jkatagi/ccusage)
- **Notion integration** — Syncs worklogs to a Notion database with structured properties
- **Local markdown logs** — `.worklogs/YYYY-MM-DD.md` files with append-per-entry format
- **Migration tool** — Bulk-migrate existing `.worklogs/` markdown files to Notion
- **Non-destructive install** — Merges into existing `settings.json` hooks without overwriting

## Quick Start

```bash
git clone https://github.com/kangraemin/ai-worklog.git
cd ai-worklog
./install.sh
```

The install wizard will guide you through:
1. **Scope** — Global (`~/.claude/`) or local (`.claude/`)
2. **Storage** — Notion + local, Notion only, or local only
3. **Notion setup** — Auto-creates a database with the right schema
4. **Git tracking** — Whether to track `.worklogs/` in git
5. **Timing** — When to write worklogs (each commit / session end / manual)

## Usage

### Writing worklogs

```
/worklog
```

Generates a worklog entry with:
- What was requested
- What was done
- Changed files
- Token usage & cost delta

### Migrating existing worklogs to Notion

```
/migrate-worklogs                    # dry-run (preview)
/migrate-worklogs --all              # migrate all
/migrate-worklogs --date 2026-03-01  # specific date
```

## Configuration

All settings live in `settings.json` under `env`:

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `WORKLOG_TIMING` | `each-commit` / `session-end` / `manual` | `each-commit` | When to write worklogs |
| `WORKLOG_DEST` | `notion` / `notion-only` / `git` | `git` | Where to store worklogs |
| `WORKLOG_GIT_TRACK` | `true` / `false` | `true` | Whether to `git add .worklogs/` |
| `NOTION_DB_ID` | UUID | — | Notion database ID |
| `AI_WORKLOG_DIR` | path | — | Install directory (auto-set) |

### Storage modes

| Mode | WORKLOG_DEST | WORKLOG_GIT_TRACK | Description |
|------|-------------|-------------------|-------------|
| both | `notion` | `true` | Local files + Notion (recommended) |
| notion-only | `notion-only` | `false` | Notion only, no local files |
| git | `git` | `true` | Local files, tracked in git |
| git-ignore | `git` | `false` | Local files, not tracked |

### Notion setup

1. Create an [integration](https://www.notion.so/my-integrations)
2. Set `NOTION_TOKEN` in `~/.claude/.env`
3. The installer auto-creates the database with these columns:

| Column | Type | Description |
|--------|------|-------------|
| Title | title | One-line work summary |
| Date | date | Work date |
| DateTime | date | Precise timestamp for sorting |
| Project | select | Project name |
| Cost | number | Session cost ($) |
| Duration | number | Work duration (minutes) |
| Model | select | Claude model used |
| Tokens | number | Token count |

## Hooks

The installer adds these Claude Code hooks:

| Event | Hook | Description |
|-------|------|-------------|
| `PostToolUse` | `worklog.sh` | Collects tool usage per session |

## Worklog format

```markdown
## 14:30

### 요청사항
- User request summary

### 작업 내용
- What was done (3 lines max)

### 변경 파일
- `filename`: one-line description

### 토큰 사용량
- 모델: claude-opus-4-6
- 이번 작업: $1.234
```

## Uninstall

```bash
./uninstall.sh
```

Removes hooks, scripts, and env variables. Preserves `.worklogs/` data and Notion credentials by default.

## Requirements

- [Claude Code](https://claude.com/claude-code) CLI
- python3
- curl, jq
- [ccusage](https://github.com/jkatagi/ccusage) (optional, for token tracking)

## License

MIT
