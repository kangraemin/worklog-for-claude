<p align="center">
  <img src="docs/notion-preview.png" alt="ai-worklog" width="640" />
</p>

<h1 align="center">ai-worklog</h1>

<p align="center">
  <strong>Automatic work logging for <a href="https://claude.com/claude-code">Claude Code</a> sessions</strong>
  <br />
  Track what you built, how long it took, and what it cost — on every commit.
</p>

<p align="center">
  <a href="https://github.com/kangraemin/ai-worklog/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="https://github.com/kangraemin/ai-worklog/issues"><img alt="Issues" src="https://img.shields.io/github/issues/kangraemin/ai-worklog.svg" /></a>
  <a href="https://github.com/kangraemin/ai-worklog/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/kangraemin/ai-worklog.svg?style=social" /></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey" />
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-compatible-blueviolet" />
</p>

<br />

## Table of Contents

- [Why ai-worklog?](#why-ai-worklog)
- [Features](#features)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Usage](#usage)
- [Configuration](#configuration)
- [Storage Modes](#storage-modes)
- [Notion Integration](#notion-integration)
- [Architecture](#architecture)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Why ai-worklog?

When you're deep in a Claude Code session, it's easy to lose track of what you've done. **ai-worklog captures everything automatically** — so you can focus on building, not bookkeeping.

| Without ai-worklog | With ai-worklog |
|---|---|
| Manually write what you did | AI-generated commit summaries |
| Guess how long tasks took | Precise Claude processing time |
| No idea what it cost | Token usage and cost per session |
| Forget to log entirely | Runs on every commit — zero effort |

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
- **Self-updating** — Built-in version check with `/update-worklog`.
- **Global or local** — Install once for all projects, or per-repo.
- **Bulk migration** — Move existing markdown worklogs to Notion with `/migrate-worklogs`.

---

## Quick Start

### Prerequisites

| Tool | Purpose |
|---|---|
| [Claude Code](https://claude.com/claude-code) | AI coding assistant (CLI) |
| `python3` | Token/cost calculation |
| `curl` | Notion API, update checks |
| `jq` | JSON processing |

### Install

```bash
git clone https://github.com/kangraemin/ai-worklog.git
cd ai-worklog
./install.sh
```

The interactive wizard walks you through:

1. **Language** — Korean (`ko`) or English (`en`)
2. **Scope** — Global (`~/.claude/`) or project-local (`.claude/`)
3. **Storage** — Markdown files, Notion, or both
4. **Timing** — Auto on each commit or manual only
5. **Auto-commit** — Optionally commit uncommitted changes when Claude stops

That's it. Start committing and worklogs appear automatically.

### Uninstall

```bash
./uninstall.sh
```

Removes hooks, scripts, and config. **Preserves** `.worklogs/` data and Notion credentials.

---

## How It Works

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

Works with **any commit method**:
- Direct `git commit`
- Claude Code `/commit` skill
- Auto-commit via Stop hook

The post-commit hook always exits `0` — worklog failures **never block** your commits.

---

## Usage

### Automatic mode (default)

Every `git commit` triggers a worklog entry. No action required.

### Manual mode

```
/worklog
```

Writes a worklog entry from the current conversation context. Works regardless of `WORKLOG_TIMING` setting.

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
| `WORKLOG_TIMING` | `each-commit` \| `manual` | `each-commit` | When to write worklogs |
| `WORKLOG_DEST` | `git` \| `notion` \| `notion-only` | `git` | Where to store worklogs |
| `WORKLOG_GIT_TRACK` | `true` \| `false` | `true` | Track `.worklogs/` in git |
| `WORKLOG_LANG` | `ko` \| `en` | `ko` | Entry language |
| `NOTION_DB_ID` | UUID | — | Notion database ID |

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
- This session: $1.089
```

> Section headers follow `WORKLOG_LANG` — Korean or English.

---

## Notion Integration

### Setup

1. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Add `NOTION_TOKEN=secret_...` to `~/.claude/.env`
3. Run `./install.sh` — the wizard auto-creates the database

### Database Schema

| Column | Type | Description |
|---|---|---|
| Title | title | One-line work summary |
| Date | date | Work date |
| DateTime | date | Precise timestamp (for sorting) |
| Project | select | Repository name |
| Cost | number | Cost delta ($) |
| Tokens | number | Token delta |
| Duration | number | Claude work time (minutes) |
| Model | select | Claude model used |

Content body is auto-converted from markdown to Notion blocks (`###` → heading_3, `- ` → bulleted_list_item).

---

## Architecture

### Directory Structure

```
ai-worklog/
├── install.sh              # Interactive installer
├── uninstall.sh            # Clean removal
├── hooks/
│   ├── post-commit.sh      # Git post-commit → worklog generation
│   ├── worklog.sh          # PostToolUse → tool usage collection
│   ├── session-end.sh      # SessionEnd → cleanup
│   └── stop.sh             # Stop → prompt /finish
├── git-hooks/
│   └── post-commit          # Git hook wrapper
├── scripts/
│   ├── worklog-write.sh     # Core: file + Notion + snapshot
│   ├── token-cost.py        # Token/cost delta from JSONL
│   ├── duration.py          # Work duration from JSONL
│   ├── notion-worklog.sh    # Notion API page creation
│   ├── notion-migrate-worklogs.sh  # Bulk .md → Notion
│   └── update-check.sh     # Version check against remote
├── commands/                # Claude Code skill definitions
├── rules/                   # Workspace rules
├── tests/                   # End-to-end test suite
└── docs/                    # Documentation assets
```

### Hooks

| Event | File | Description |
|---|---|---|
| Git `post-commit` | `hooks/post-commit.sh` | Generates worklog entry on each commit |
| `PostToolUse` | `hooks/worklog.sh` | Collects tool usage into per-session JSONL |
| `SessionEnd` | `hooks/session-end.sh` | Cleans up session collection file |
| `Stop` | `hooks/stop.sh` | Prompts to commit uncommitted changes |

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

The post-commit hook runs `claude -p` in the background. Your commit completes immediately. If AI summary generation fails, it falls back to an auto-generated format using the commit message.
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
