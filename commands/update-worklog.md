---
description: worklog-for-claude 최신 버전 확인 및 업데이트
---

# /update-worklog

## 플로우

1. `bash "${AI_WORKLOG_DIR}/scripts/update-check.sh" --check-only` 로 현재/최신 버전 확인
2. 결과 출력:
   - `up-to-date` → "최신 버전입니다 (SHA)" 출력 후 종료
   - `update-available` → 현재/최신 SHA 보여주고 업데이트 여부 확인
3. 업데이트 확인 시 `bash "${AI_WORKLOG_DIR}/scripts/update-check.sh" --force` 실행
4. 완료 메시지 출력
