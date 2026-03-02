# ai-worklog

> Automatic work logging for [Claude Code](https://claude.com/claude-code) sessions.

Track what you built, how long it took, and what it cost — automatically, on every commit.

![Notion DB preview](docs/notion-preview.png)

## What it does

Every time you `git commit`, ai-worklog:

1. Runs a git post-commit hook
2. Uses `claude -p` to summarize the commit (request, changes, file descriptions)
3. Calculates token usage and cost delta from project JSONL
4. Writes an entry to `.worklogs/YYYY-MM-DD.md`
5. Optionally syncs to a Notion database

Works with any commit method — `/commit` skill, `git commit` directly, or auto-commit via Stop hook.

## Install

```bash
git clone https://github.com/kangraemin/ai-worklog.git
cd ai-worklog
./install.sh
```

The interactive wizard configures:

- **Scope** — Global (`~/.claude/`) or project-local (`.claude/`)
- **Storage** — Local markdown, Notion, or both
- **Timing** — On each commit or manually
- **Git tracking** — Whether `.worklogs/` is committed with your code
- **Auto-commit** — Auto-commit uncommitted changes when Claude stops

## Usage

### Automatic (default)

With `WORKLOG_TIMING=each-commit`, every `git commit` triggers a post-commit hook that writes a worklog entry automatically. No action required.

### Manual

```
/worklog
```

Writes a worklog entry from the current conversation context.

### Entry format

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

### Migrating existing worklogs to Notion

```
/migrate-worklogs              # dry-run preview
/migrate-worklogs --all        # migrate all .md files
/migrate-worklogs --date 2026-03-01  # specific date only
```

Already-migrated entries are skipped automatically (tracked in `.worklogs/.migrated`).

### Updating ai-worklog

```
/update-worklog
```

Checks for updates and re-runs install if a new version is available.

## Configuration

Settings live in `settings.json` under `env`:

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `WORKLOG_TIMING` | `each-commit` / `manual` | `each-commit` | When to write worklogs |
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

## Architecture

### How it works

```
git commit
  └→ post-commit hook (git-hooks/post-commit)
       └→ hooks/post-commit.sh
            ├→ claude -p: summarize commit (request, changes, file descriptions)
            └→ scripts/worklog-write.sh
                 ├→ token-cost.py: calculate cost delta
                 ├→ duration.py: calculate work time
                 ├→ write .worklogs/YYYY-MM-DD.md
                 └→ notion-worklog.sh: sync to Notion (optional)
```

### Hooks

| Event | File | Description |
|-------|------|-------------|
| `PostToolUse` | `hooks/worklog.sh` | Collects tool usage into a per-session JSONL file |
| `SessionEnd` | `hooks/session-end.sh` | Cleans up the JSONL collection file |
| `Stop` | `hooks/stop.sh` | Auto-commits uncommitted changes (optional) |
| git `post-commit` | `hooks/post-commit.sh` | Generates worklog entry on each commit |

### Scripts

| File | Description |
|------|-------------|
| `scripts/worklog-write.sh` | Core worklog writer (file + Notion + snapshot) |
| `scripts/token-cost.py` | Token/cost delta from JSONL |
| `scripts/duration.py` | Actual Claude work time from JSONL |
| `scripts/notion-worklog.sh` | Notion API page creation |
| `scripts/notion-migrate-worklogs.sh` | Bulk migration of .md to Notion |
| `scripts/update-check.sh` | Version check against remote |

### Commands

| Skill | Description |
|-------|-------------|
| `/worklog` | Manual worklog entry from conversation context |
| `/migrate-worklogs` | Migrate existing .worklogs/ to Notion |
| `/update-worklog` | Check for updates and re-install |

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
