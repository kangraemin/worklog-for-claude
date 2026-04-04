---
description: "워크로그 설정 조회/변경. 'worklog 설정', 'worklog config', '워크로그 설정 보여줘', '워크로그 설정 바꿔줘' 요청 시 트리거."
---

# /worklog-config

워크로그 설정을 조회하거나 변경한다.

## 인자

- 인자 없음 → 현재 설정 조회
- `<key> <value>` → 해당 설정 변경

지원 키:

| 키 | 환경변수 | 허용 값 |
|---|---|---|
| `timing` | `WORKLOG_TIMING` | `stop`, `manual` |
| `dest` | `WORKLOG_DEST` | `git`, `notion`, `notion-only` |
| `git-track` | `WORKLOG_GIT_TRACK` | `true`, `false` |
| `lang` | `WORKLOG_LANG` | `ko`, `en` |

## 조회 플로우

1. settings.json 탐색 순서:
   - 로컬: `<프로젝트>/.claude/settings.json`
   - 글로벌: `~/.claude/settings.json`
2. 두 파일의 env를 머지 (로컬이 글로벌을 오버라이드)
3. 아래 포맷으로 출력:

```
worklog-for-claude 설정
━━━━━━━━━━━━━━━━━━━━━━
  Timing:    stop
  Storage:   notion-only
  Git Track: false
  Language:  ko
  Notion DB: 316d4919-...
  MCP Check: 5 commits

  Source: ~/.claude/settings.json
         .claude/settings.json (local override)
```

4. 로컬 오버라이드가 있으면 해당 키 옆에 `(local)` 표시

## 변경 플로우

1. 인자에서 key, value 파싱
2. 허용 값 검증 — 틀리면 허용 값 목록 보여주고 종료
3. 대상 settings.json 결정:
   - 로컬 `.claude/settings.json`이 있으면 로컬에 저장
   - 없으면 글로벌 `~/.claude/settings.json`에 저장
4. python3으로 settings.json 읽기 → env 키 업데이트 → 쓰기:

```bash
python3 -c "
import json, sys
file = sys.argv[1]
key = sys.argv[2]
value = sys.argv[3]
with open(file) as f:
    cfg = json.load(f)
cfg.setdefault('env', {})[key] = value
with open(file, 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
" "<settings_path>" "<ENV_KEY>" "<value>"
```

5. 변경 결과 확인: 조회 플로우 실행하여 최종 상태 출력

## 건강 진단 (인자 없이 실행 시)

설정 조회 출력 후 이어서 건강 진단을 실행한다:

```bash
bash "${AI_WORKLOG_DIR:-$HOME/.claude}/scripts/healthcheck.sh"
```

문제 발견 시 `/worklog-update` 또는 `install.sh` 재설치를 제안한다.

## 사용 예시

```
/worklog-config                    → 현재 설정 조회 + 건강 진단
/worklog-config timing manual      → 수동 모드로 변경 (건강 진단 미실행)
/worklog-config dest git           → 로컬 파일만 저장
/worklog-config lang en            → 영어로 변경
/worklog-config git-track false    → .worklogs/ git 미추적
```
