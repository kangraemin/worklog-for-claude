# /finish

세션 종료 전 미커밋 변경사항을 커밋하고 워크로그를 작성한다.
`/commit` 스킬이 없는 유저도 사용 가능한 독립 스킬.

## 절차

1. `git status`로 미커밋 변경사항 확인. 없으면 "변경사항 없음" 출력 후 종료.
2. 커밋 규칙 탐색 (우선순위):
   - 프로젝트 `.claude/rules/git-rules.md`
   - `~/.claude/rules/git-rules.md`
   - 둘 다 없으면 기본 규칙: type 영어(feat/fix/refactor/chore/docs), 설명 한글, 50자 이내
3. 규칙에 따라 커밋:
   - 변경 파일 개별 `git add` (`git add .` / `-A` 금지)
   - `.worklogs/` 파일이 있으면 같이 staging
   - 민감 파일 (.env, credentials, *.key, *.pem) 제외
   - HEREDOC으로 커밋
4. `git push` (upstream 없으면 `-u origin <branch>`)
5. `WORKLOG_TIMING` 확인:
   - `manual`이면 워크로그 스킵, 종료
   - 그 외: 아래 워크로그 진행
6. 대화 컨텍스트에서 이번 작업 요약 작성:

```
### 요청사항
- 사용자 요청

### 작업 내용
- 구체적 변경 2-3줄

### 변경 파일
- `파일명`: 한 줄 설명
```

7. 요약을 임시 파일에 저장 후 실행:

```bash
TMPFILE=$(mktemp)
cat <<'SUMMARY' > "$TMPFILE"
(위 요약 내용)
SUMMARY
bash "${AI_WORKLOG_DIR}/scripts/worklog-write.sh" "$TMPFILE"
rm -f "$TMPFILE"
```

8. `.worklogs/` 변경사항 staging + 커밋 (`docs: 워크로그 자동 갱신`) + 푸시

## 금지사항

- `git add .` / `git add -A`
- `--force`, `--no-verify`
- `Co-Authored-By`
