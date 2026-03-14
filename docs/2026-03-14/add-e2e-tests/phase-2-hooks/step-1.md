# Step 1: Stop hook 테스트 (pending + uncommitted)

## TC

| TC | 검증 항목 | 기대 결과 | 상태 |
|----|----------|----------|------|
| TC-01 | pending 마커 감지 시 block decision | `decision == "block"` | ✅ |
| TC-02 | pending 마커 감지 시 /worklog reason | `reason`에 `/worklog` 포함 | ✅ |
| TC-03 | pending 마커 감지 시 커밋 메시지 표시 | `reason`에 커밋 메시지 포함 | ✅ |
| TC-04 | 미커밋 변경 감지 시 block decision | `decision == "block"` | ✅ |
| TC-05 | 미커밋 변경 감지 시 /finish reason | `reason`에 `/finish` 포함 | ✅ |
| TC-06 | 클린 repo에서 통과 | stdout 비어있음 | ✅ |

## 실행출력

TC-01~06: `python3 -m pytest tests/test_hooks_e2e.py -v`
→ 6 passed in 1.62s

```
tests/test_hooks_e2e.py::TestStopPendingMarker::test_block_decision PASSED
tests/test_hooks_e2e.py::TestStopPendingMarker::test_shows_commit_msg PASSED
tests/test_hooks_e2e.py::TestStopPendingMarker::test_worklog_reason PASSED
tests/test_hooks_e2e.py::TestStopUncommittedChanges::test_block_decision PASSED
tests/test_hooks_e2e.py::TestStopUncommittedChanges::test_clean_repo_passes PASSED
tests/test_hooks_e2e.py::TestStopUncommittedChanges::test_finish_reason PASSED
```
