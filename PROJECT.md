# worklog-for-claude

## 이게 뭔가
Claude Code 세션의 작업을 자동으로 기록하고, 프로젝트 문서를 AI와 함께 유지하는 도구.

## 왜 만들었나
Claude Code로 작업하다 보면 뭘 했는지, 얼마나 걸렸는지, 비용이 얼마인지 알기 어려움.
워크로그를 자동화하고 싶었고, 나아가 "프로젝트가 어떻게 생겼는지"를 AI가 같이 관리해주는 시스템이 필요했음.

## 구조
```
worklog-for-claude/
├── commands/        # Claude Code 스킬 (.md)
├── hooks/           # git hooks (post-commit 등)
├── scripts/         # worklog-write.sh, notion-worklog.sh 등 shell scripts
├── rules/           # worklog-rules.md
├── tests/           # 스크립트 테스트
├── mcp/             # Python MCP 서버 (feature/mcp-server 브랜치)
│   ├── src/worklog_mcp/
│   │   ├── server.py            # FastMCP 서버, 7개 tool 등록
│   │   ├── tools/worklog.py     # write_worklog, read_worklog
│   │   ├── tools/notion.py      # Notion API 연동
│   │   └── utils/git.py         # git log, diff 헬퍼
│   └── tests/                   # 71개 TC
├── install.sh       # 설치 스크립트
└── uninstall.sh
```

## 기술 스택
- **Shell (Bash)**: 기존 worklog 시스템 — git hook, 스크립트 기반
- **Python + FastMCP**: MCP 서버 — 어떤 MCP 클라이언트에서든 동작
- **Notion API**: 워크로그 원격 저장 (선택)
- **uv**: Python 패키지 관리

## 주요 결정들
- **스킬 → MCP 전환**: 스킬은 프롬프트 기반이라 불안정. MCP는 실제 코드로 동작 — 테스트 가능하고 예측 가능함
- **Cursor 지원 보류**: 워크로그 자동화(stop hook)가 Claude Code에서만 제대로 동작. Cursor는 나중

## 해결한 문제들
- **stop hook 미커밋 block 제거**: 워크로그 작성 전 미커밋 파일 있으면 block하던 로직 제거 — 실제로 불필요한 제약이었음
- **uv run pytest 경로 문제**: mcp/ 서브디렉토리에서 pytest 실행 시 worklog_mcp 모듈 못 찾는 문제 → .venv/bin/python 직접 호출로 해결

## 지금 상태
- 기존 shell 기반 worklog: main 브랜치, 안정
- MCP 서버: feature/mcp-server 브랜치, 71개 TC 통과
- main 머지 전 정리 필요: 브랜치 전략, 레포명 변경 검토
