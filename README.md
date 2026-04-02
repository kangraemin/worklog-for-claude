<p align="center">
  <img src="docs/notion-preview.png" alt="worklog-for-claude" width="640" />
</p>

<h1 align="center">worklog-for-claude</h1>

<p align="center">
  <strong>Automatic work logging for <a href="https://claude.com/claude-code">Claude Code</a> sessions</strong>
  <br />
  Track what you built, how long it took, and what it cost — automatically.
</p>

<p align="center">
  <a href="https://github.com/kangraemin/worklog-for-claude/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="https://github.com/kangraemin/worklog-for-claude/issues"><img alt="Issues" src="https://img.shields.io/github/issues/kangraemin/worklog-for-claude.svg" /></a>
  <a href="https://github.com/kangraemin/worklog-for-claude/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/kangraemin/worklog-for-claude.svg?style=social" /></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey" />
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-compatible-blueviolet" />
</p>

<br />

## Table of Contents

- [Why worklog-for-claude?](#why-worklog-for-claude)
- [Features](#features)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Usage](#usage)
- [Configuration](#configuration)
- [Storage Modes](#storage-modes)
- [Notion Integration](#notion-integration)
- [MCP Server](#mcp-server)
- [Architecture](#architecture)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Why worklog-for-claude?

When you're deep in a Claude Code session, it's easy to lose track of what you've done. **worklog-for-claude captures everything automatically** — so you can focus on building, not bookkeeping.

| Without worklog-for-claude | With worklog-for-claude |
|---|---|
| Manually write what you did | AI-generated commit summaries |
| Guess how long tasks took | Precise Claude processing time |
| No idea what it cost | Token usage and cost per session |
| Forget to log entirely | Triggered on every commit — zero effort |

---

## Features

### Core

- **Zero-friction logging** — Git post-commit hook writes entries automatically. Just commit and it's done.
- **AI-powered summaries** — Uses `claude -p` to generate human-readable work descriptions from diffs.
- **Token & cost tracking** — Parses Claude Code JSONL logs to calculate per-session deltas.
- **Duration tracking** — Measures actual Claude work time, not wall-clock time.

### Storage & Sync

- **Notion sync** — Real-time sync to a Notion database with auto-created schema.
- **Flexible storage** — Local markdown, Notion, or both. Choose per project.
- **Git-tracked worklogs** — Optionally commit `.worklogs/` alongside your code.

### DX

- **Non-destructive install** — Preserves existing git hooks via chaining.
- **Bilingual** — Full Korean and English support (`WORKLOG_LANG`).
- **Self-updating** — Automatic version check on `SessionStart`, or manual with `/update-worklog`.
- **Global or local** — Install once for all projects, or per-repo.
- **Bulk migration** — Move existing markdown worklogs to Notion with `/migrate-worklogs`.
- **MCP server** — Cross-client support (Claude Code, Cursor, Claude Desktop) with PROJECT.md auto-management.

---

## Quick Start

### Prerequisites

| Tool | Purpose |
|---|---|
| [Claude Code](https://claude.com/claude-code) | AI coding assistant (CLI) |
| `python3` | Token/cost calculation |
| `curl` | Notion API, update checks |
| `jq` *(optional)* | JSON processing (session cleanup) |
| `uv` *(optional)* | MCP server support |

### Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/kangraemin/worklog-for-claude/main/install.sh)
```

For local install (specific project only), run the same command from your project directory and select scope: **Local (2)**.

The interactive wizard walks you through:

1. **Language** — Korean (`ko`) or English (`en`)
2. **Scope** — Global (`~/.claude/`) or project-local (`.claude/`)
3. **Storage** — Notion + local files, Notion only, or local files only
4. **Notion setup** — Token input, database auto-creation (if Notion mode selected)
5. **Git tracking** — Track `.worklogs/` in git or add to `.gitignore`
6. **Timing** — Auto on commit or manual only
7. **MCP setup** — Client selection and PROJECT.md check interval (if `uv` installed)

That's it. Start committing and worklogs appear automatically.

> **Tip:** Run the installer again with `--reconfigure` to change settings after initial install.

### Uninstall

```bash
./uninstall.sh
```

Removes hooks, scripts, commands, and config from `settings.json`. **Preserves** `.worklogs/` data and `.env` credentials.

---

## How It Works

### Outside Claude Code (terminal `git commit`)

```
git commit
  └─ post-commit hook fires
       └─ claude -p generates AI summary from diff
            └─ worklog-write.sh
                 ├─ token-cost.py   → cost delta from Claude JSONL
                 ├─ duration.py     → work time from Claude JSONL
                 ├─ .worklogs/YYYY-MM-DD.md   (append locally)
                 └─ notion-worklog.sh          (sync to Notion)
```

### Inside Claude Code session

```
git commit (inside Claude Code)
  └─ post-commit hook detects CLAUDECODE env
       └─ writes pending marker → exits immediately (never blocks)
            └─ on-commit.sh (PostToolUse) detects the commit
                 └─ blocks and requests /worklog
                      └─ worklog-write.sh (same pipeline as above)
```

Works with **any commit method**:
- Direct `git commit` in terminal
- Claude Code `/commit` skill
- `git commit` inside a Claude Code session (via `on-commit.sh`)

The post-commit hook always exits `0` — worklog failures **never block** your commits.

---

## Usage

### Automatic mode (default)

Every `git commit` triggers a worklog entry. No action required.

### Manual mode

```
/worklog
```

Writes a worklog entry from the current conversation context. Works regardless of the `WORKLOG_TIMING` setting.

### Session finish

```
/finish
```

Commits + pushes + writes worklog — all in one step. Great for wrapping up a session.

### Migrate to Notion

```
/migrate-worklogs              # dry-run preview
/migrate-worklogs --all        # migrate all .md files
/migrate-worklogs --date 2026-03-01  # specific date only
/migrate-worklogs --all --delete-after  # migrate and delete source files
```

### Self-update

```
/update-worklog
```

Checks GitHub for updates and re-installs if a new version is available.

---

## Configuration

All settings live in `settings.json` under `env`:

| Variable | Values | Default | Description |
|---|---|---|---|
| `WORKLOG_TIMING` | `stop` \| `manual` | `stop` | When to write worklogs |
| `WORKLOG_DEST` | `git` \| `notion` \| `notion-only` | `git` | Where to store worklogs |
| `WORKLOG_GIT_TRACK` | `true` \| `false` | `true` | Track `.worklogs/` in git |
| `WORKLOG_LANG` | `ko` \| `en` | `ko` | Entry language |
| `NOTION_DB_ID` | UUID | — | Notion database ID |
| `AI_WORKLOG_DIR` | path | `~/.claude` | Installation directory (set by installer) |
| `PROJECT_DOC_CHECK_INTERVAL` | number | `5` | Commits between PROJECT.md update checks (MCP) |

---

## Storage Modes

| Mode | `WORKLOG_DEST` | `WORKLOG_GIT_TRACK` | Local file | Notion | Git-tracked |
|---|---|---|---|---|---|
| **git** | `git` | `true` | Yes | No | Yes |
| **git-ignore** | `git` | `false` | Yes | No | No |
| **both** | `notion` | `true` | Yes | Yes | Yes |
| **notion-only** | `notion-only` | `false` | No | Yes | No |

### Entry Format

```markdown
## 14:30

### Request
- Add duplicate prevention to migration script

### Summary
- Added .migrated fingerprint file to skip already-sent entries
- Updated skipped count in output summary

### Changed Files
- `scripts/notion-migrate-worklogs.sh`: duplicate prevention logic

### Token Usage
- Model: claude-sonnet-4-6
- This session: 52,340 tokens · $1.089
```

> Section headers follow `WORKLOG_LANG` — Korean or English.

---

## Notion Integration

### Setup

1. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Run the installer and select a Notion storage mode — the wizard prompts for your token (`ntn_...` or `secret_...`) and auto-creates the database
3. Share the created database with your integration (Share → Add connections)

> You can also add `NOTION_TOKEN=ntn_...` to `~/.claude/.env` before running the installer — it will be auto-detected.

### Database Schema

| Column | Type | Description |
|---|---|---|
| Title | title | One-line work summary |
| DateTime | date | Work timestamp |
| Project | select | Repository name |
| Tokens | number | Token delta |
| Cost | number | Cost delta ($) |
| Duration | number | Claude work time (minutes) |
| Model | select | Claude model used |

Content body is auto-converted from markdown to Notion blocks (`###` → heading_3, `- ` → bulleted_list_item).

---

## MCP Server

The `mcp/` directory contains a Python MCP server that extends worklog-for-claude to any MCP-compatible client — Claude Code, Cursor, and Claude Desktop.

### What it adds

- **Worklog** — write and read worklogs via MCP tools
- **PROJECT.md** — auto-creates and maintains a project documentation file
- **Gap detection** — compares recent git commits to PROJECT.md and surfaces what's missing

### Install

Requires `uv`. The installer sets this up automatically, or configure manually:

```bash
cd worklog-for-claude/mcp
uv sync
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "worklog-for-claude": {
      "command": "uvx",
      "args": ["worklog-for-claude"],
      "env": { "PROJECT_DOC_CHECK_INTERVAL": "5" }
    }
  }
}
```

See `mcp/README.md` for client-specific configuration examples.

---

## Architecture

### Directory Structure

```
worklog-for-claude/
├── install.sh              # Interactive installer (supports curl pipe)
├── uninstall.sh            # Clean removal
├── hooks/
│   ├── post-commit.sh      # Git post-commit → worklog generation
│   ├── worklog.sh          # PostToolUse → tool usage collection
│   ├── on-commit.sh        # PostToolUse (Bash) → git commit detection
│   ├── commit-doc-check.sh # PostToolUse → PROJECT.md update check
│   ├── session-end.sh      # SessionEnd → cleanup
│   └── stop.sh             # Stop → prompt /worklog (legacy, removed by installer)
├── git-hooks/
│   └── post-commit         # Git hook wrapper
├── scripts/
│   ├── worklog-write.sh    # Core: file + Notion + snapshot
│   ├── token-cost.py       # Token/cost delta from JSONL
│   ├── duration.py         # Work duration from JSONL
│   ├── notion-worklog.sh   # Notion API page creation
│   ├── notion-create-db.sh # Notion database auto-creation
│   ├── notion-migrate-worklogs.sh  # Bulk .md → Notion
│   └── update-check.sh    # Version check against remote
├── commands/               # Claude Code skill definitions
│   ├── worklog.md          # /worklog
│   ├── finish.md           # /finish
│   ├── migrate-worklogs.md # /migrate-worklogs
│   └── update-worklog.md   # /update-worklog
├── rules/                  # Workspace rules
├── mcp/                    # MCP server (Python, FastMCP)
│   ├── src/worklog_mcp/    # Server + tools
│   └── tests/              # MCP test suite
├── tests/                  # End-to-end test suite
└── docs/                   # Documentation assets
```

### Hooks

| Event | File | Description |
|---|---|---|
| Git `post-commit` | `hooks/post-commit.sh` | Generates worklog entry on each commit |
| `PostToolUse` | `hooks/worklog.sh` | Collects tool usage into per-session JSONL |
| `PostToolUse` (Bash) | `hooks/on-commit.sh` | Detects `git commit` and requests `/worklog` |
| `PostToolUse` | `hooks/commit-doc-check.sh` | Checks if PROJECT.md needs updating |
| `SessionStart` | `scripts/update-check.sh` | Version check against GitHub (24h throttle) |
| `SessionEnd` | `hooks/session-end.sh` | Cleans up session collection file |

> The installer removes any existing Stop hooks for worklog — `PostToolUse` (`on-commit.sh`) handles commit detection instead.

### Token Calculation

Token and cost deltas are calculated by parsing Claude Code's official JSONL logs:

1. Read snapshot timestamp from `~/.claude/worklogs/.snapshot`
2. Filter JSONL entries after that timestamp for the current project
3. Sum `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`
4. Apply model-specific pricing (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5)
5. Update snapshot after writing the entry

---

## FAQ

<details>
<summary><strong>Does it slow down my commits?</strong></summary>

Inside a Claude Code session, the hook writes a pending marker and exits immediately — your commit is never blocked. Outside Claude Code, it runs `claude -p` synchronously but completes in seconds. If AI summary generation fails, it falls back to an auto-generated format using the commit message.
</details>

<details>
<summary><strong>Can I use it on multiple projects?</strong></summary>

Yes. Install globally (`~/.claude/`) and it works across all git repos. Each project gets its own `.worklogs/` directory and token calculations are scoped per project.
</details>

<details>
<summary><strong>What if I don't use Notion?</strong></summary>

Notion is completely optional. Choose `git` or `git-ignore` mode during install to use local markdown files only.
</details>

<details>
<summary><strong>Will it break my existing git hooks?</strong></summary>

No. The installer preserves existing hooks by chaining — your original `post-commit` is saved as `post-commit.local` and called before the worklog hook.
</details>

<details>
<summary><strong>How accurate is the cost tracking?</strong></summary>

It parses Claude Code's actual JSONL logs using official token counts and model-specific pricing. Cost is calculated as a delta since the last worklog entry.
</details>

<details>
<summary><strong>Can I migrate from local files to Notion later?</strong></summary>

Yes. Run `/migrate-worklogs --all` to bulk-import existing `.worklogs/*.md` files into Notion. Use `--date` to migrate specific dates.
</details>

<details>
<summary><strong>What if I regenerate my Notion token?</strong></summary>

Regenerating your Notion integration token invalidates the old one. Update in two steps:
1. Replace `NOTION_TOKEN` in `~/.claude/.env` (or `<project>/.claude/.env` for local installs)
2. Re-share the database with the new integration in Notion (Share → Add connections)

Without step 2, API calls will fail with a permission error even though the token itself is valid.
</details>

<details>
<summary><strong>Notion API says "not a database" error?</strong></summary>

Your `NOTION_DB_ID` might contain a page ID instead of the actual database ID. To fix:
1. Open your worklog database in Notion
2. Copy the ID from the URL: `notion.so/<workspace>/<DB_ID>?v=...`
3. Update `NOTION_DB_ID` in `~/.claude/settings.json` (or `<project>/.claude/settings.json`)

The ID is the 32-character hex string before `?v=`.
</details>

---

## Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository
2. **Create** a feature branch
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make** your changes
4. **Test** — run the e2e tests in `tests/`
   ```bash
   python3 -m pytest tests/
   ```
5. **Commit** and push
6. **Open** a Pull Request

### Areas for Contribution

- New storage backends (GitHub Issues, Linear, etc.)
- Additional language support
- Improved token pricing for new models
- CI/CD pipeline improvements
- Documentation and examples

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  Built for <a href="https://claude.com/claude-code">Claude Code</a> by <a href="https://github.com/kangraemin">@kangraemin</a>
  <br />
  <sub>If this project helped you, consider giving it a star!</sub>
</p>
