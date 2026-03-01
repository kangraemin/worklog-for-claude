---
description: 기존 .worklogs MD 파일을 Notion DB로 마이그레이션
---

# /migrate-worklogs

기존 `.worklogs/*.md` 파일을 Notion DB로 마이그레이션한다.

## 플로우

1. 인자 파싱:
   - `--dry-run` : 실제 전송 없이 파싱 결과만 출력 (기본값)
   - `--date YYYY-MM-DD` : 특정 날짜만 처리
   - `--all` : 실제 전송 실행 (dry-run 아님)
   - `--delete-after` : 전송 성공한 파일의 MD 삭제 (실패한 파일은 보존)

2. 워크로그 디렉토리 결정:
   - 현재 프로젝트 루트의 `.worklogs/` 디렉토리 사용
   - 없으면 `~/.claude/.worklogs/` 사용

3. 환경변수 확인 (`--all` 모드에서만):
   - `NOTION_TOKEN` 없으면 에러 출력 후 종료
   - `NOTION_DB_ID` 없으면 에러 출력 후 종료

4. 실행:
   ```bash
   # dry-run (기본)
   bash "${AI_WORKLOG_DIR}/scripts/notion-migrate-worklogs.sh" --dry-run [--date YYYY-MM-DD] <worklogs_dir>

   # 실제 마이그레이션
   bash "${AI_WORKLOG_DIR}/scripts/notion-migrate-worklogs.sh" [--date YYYY-MM-DD] [--delete-after] <worklogs_dir>
   ```

5. 결과 출력:
   - dry-run: 파싱된 엔트리 목록 출력 후 "실제 전송하려면 `/migrate-worklogs --all` 실행" 안내
   - 실제: 성공/실패 카운트 출력

6. **마이그레이션 완료 후 — 워크로그 저장 방식 변경 제안**:
   - 실제 전송(`--all`)이 성공적으로 완료되면 사용자에게 묻는다:
     "앞으로 워크로그를 어떻게 저장할까요?"
     - `notion-only` : Notion에만 기록 (로컬 파일 없음)
     - `git`         : 파일로만 기록 (git 추적)
     - `git-ignore`  : 파일로만 기록 (git 미추적 — .gitignore 처리)
     - `both`        : 파일 + Notion 모두 기록 (현재 방식)
     - 변경 안 함   : 현재 설정 유지
   - 변경 선택 시:
     ```bash
     bash "${AI_WORKLOG_DIR}/scripts/notion-migrate-worklogs.sh" --set-mode <mode> <worklogs_dir>
     ```
   - `git-ignore` 선택 시 추가 안내: `.worklogs/` 디렉토리를 `.gitignore`에 추가할지 사용자에게 확인

## 사용 예시

```
/migrate-worklogs                              → dry-run (미리보기)
/migrate-worklogs --all                        → 전체 마이그레이션
/migrate-worklogs --all --delete-after         → 전송 후 MD 파일 삭제
/migrate-worklogs --date 2026-02-23            → 특정 날짜 dry-run
/migrate-worklogs --date 2026-02-23 --all      → 특정 날짜만 전송
/migrate-worklogs --date 2026-02-23 --all --delete-after → 특정 날짜 전송 후 삭제
```

## 동작 규칙

- `--delete-after`는 `--all`과 함께만 동작 (dry-run에서는 삭제 안 함)
- 파일 단위로 판단: 한 파일에서 하나라도 실패하면 해당 파일은 보존
- 전체 성공한 파일만 삭제
- 워크로그 모드 변경은 `settings.json`의 `WORKLOG_DEST`, `WORKLOG_GIT_TRACK`을 업데이트

## 워크로그 저장 모드

| 모드 | WORKLOG_DEST | WORKLOG_GIT_TRACK | 설명 |
|------|-------------|-------------------|------|
| `notion-only` | `notion-only` | `false` | Notion에만 기록, 로컬 파일 없음 |
| `git` | `git` | `true` | 로컬 파일만, git 추적 |
| `git-ignore` | `git` | `false` | 로컬 파일만, git 미추적 |
| `both` | `notion` | `true` | 로컬 파일 + Notion (기본) |
