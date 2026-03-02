# Auto-Commit Rules

Stop hook에서 `claude -p`로 자동 커밋 시 따르는 규칙.
프로젝트에 `.claude/rules/git-rules.md`가 있으면 이 파일 대신 그것을 따른다.

## 커밋

- type은 영어: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `style`, `perf`
- 설명은 한글 (WORKLOG_LANG=en이면 영어): `feat: 자연어 검색 기능 추가`
- 50자 이내
- HEREDOC 필수:
  ```bash
  git commit -m "$(cat <<'EOF'
  feat: 설명
  EOF
  )"
  ```

## 스테이징

- 파일 개별 `git add` (절대 `git add .` / `-A` 금지)
- 민감 파일 제외: `.env`, `credentials`, `*.key`, `*.pem`

## 푸시

- 커밋 후 반드시 `git push`
- upstream 없으면 `-u origin <branch>`
- `--force` 금지
