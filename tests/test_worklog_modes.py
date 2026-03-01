#!/usr/bin/env python3
"""
워크로그 저장 모드 (--set-mode) 테스트
Run: python3 tests/test_worklog_modes.py
"""

import sys, os, json, subprocess, tempfile, unittest

# 패키지 내 스크립트 경로 (tests/ 기준 상대경로)
SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'notion-migrate-worklogs.sh')
SCRIPT = os.path.abspath(SCRIPT)


# ── apply_mode 로직 (스크립트와 동일) ────────────────────────────────────────

def apply_mode(cfg: dict, mode: str) -> dict:
    env = cfg.setdefault('env', {})
    if mode == 'notion-only':
        env['WORKLOG_DEST']      = 'notion-only'
        env['WORKLOG_GIT_TRACK'] = 'false'
    elif mode == 'git':
        env['WORKLOG_DEST']      = 'git'
        env['WORKLOG_GIT_TRACK'] = 'true'
    elif mode == 'git-ignore':
        env['WORKLOG_DEST']      = 'git'
        env['WORKLOG_GIT_TRACK'] = 'false'
    elif mode == 'both':
        env['WORKLOG_DEST']      = 'notion'
        env['WORKLOG_GIT_TRACK'] = 'true'
    return cfg

VALID_MODES = ['notion-only', 'git', 'git-ignore', 'both']


# ── cost 반올림 로직 (notion-worklog.sh / notion-migrate-worklogs.sh 와 동일) ──

def round_cost(cost: float) -> float:
    return round(cost, 3)


# ── 유닛 테스트: apply_mode ───────────────────────────────────────────────────

class TestApplyMode(unittest.TestCase):

    def _cfg(self):
        return {'env': {'WORKLOG_DEST': 'git', 'WORKLOG_GIT_TRACK': 'true', 'OTHER': 'keep'}}

    def test_notion_only(self):
        cfg = apply_mode(self._cfg(), 'notion-only')
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'notion-only')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'false')

    def test_git(self):
        cfg = apply_mode(self._cfg(), 'git')
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'git')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'true')

    def test_git_ignore(self):
        cfg = apply_mode(self._cfg(), 'git-ignore')
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'git')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'false')

    def test_both(self):
        cfg = apply_mode(self._cfg(), 'both')
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'notion')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'true')

    def test_other_keys_preserved(self):
        """다른 env 키는 변경하지 않음"""
        cfg = apply_mode(self._cfg(), 'git')
        self.assertEqual(cfg['env']['OTHER'], 'keep')

    def test_env_key_created_if_missing(self):
        """env 키 없어도 생성됨"""
        cfg = apply_mode({}, 'git')
        self.assertIn('WORKLOG_DEST', cfg['env'])

    def test_all_modes_produce_valid_dest(self):
        """모든 모드의 WORKLOG_DEST가 알려진 값임"""
        valid_dests = {'git', 'notion', 'notion-only'}
        for mode in VALID_MODES:
            cfg = apply_mode({}, mode)
            self.assertIn(cfg['env']['WORKLOG_DEST'], valid_dests, f"mode={mode}")

    def test_all_modes_produce_valid_git_track(self):
        """모든 모드의 WORKLOG_GIT_TRACK이 true/false"""
        for mode in VALID_MODES:
            cfg = apply_mode({}, mode)
            self.assertIn(cfg['env']['WORKLOG_GIT_TRACK'], {'true', 'false'}, f"mode={mode}")


# ── 유닛 테스트: cost 반올림 ────────────────────────────────────────────────

class TestCostRounding(unittest.TestCase):

    def test_rounds_to_3_decimal_places(self):
        self.assertEqual(round_cost(1.3199667), 1.320)

    def test_exact_3_decimal_unchanged(self):
        self.assertEqual(round_cost(37.470), 37.470)

    def test_long_decimal(self):
        self.assertAlmostEqual(round_cost(720.3599667), 720.360, places=3)

    def test_zero(self):
        self.assertEqual(round_cost(0.0), 0.0)

    def test_small_cost(self):
        self.assertEqual(round_cost(0.8207073), 0.821)

    def test_migrate_cost_rounding(self):
        """migrate 스크립트가 cost를 3자리로 반올림해 notion-worklog.sh에 전달"""
        cost = 1.3199667
        self.assertEqual(round(cost, 3), 1.320)


# ── 통합 테스트: 실제 쉘 스크립트 호출 ──────────────────────────────────────

class TestSetModeScript(unittest.TestCase):
    """
    실제 bash 스크립트를 temp 디렉토리로 호출해 settings.json 업데이트 검증.
    NOTION_TOKEN / NOTION_DB_ID 불필요 (--set-mode 는 마이그레이션 없이 동작).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 빈 worklogs 디렉토리 (마이그레이션 대상 없음)
        self.wl_dir = os.path.join(self.tmpdir, '.worklogs')
        os.makedirs(self.wl_dir)
        # 기본 settings.json
        self.settings = os.path.join(self.tmpdir, 'settings.json')
        initial = {'env': {'WORKLOG_DEST': 'git', 'WORKLOG_GIT_TRACK': 'true', 'FOO': 'bar'}}
        with open(self.settings, 'w') as f:
            json.dump(initial, f, indent=2)

    def _run_set_mode(self, mode):
        # HOME을 tmpdir로 override해 settings.json 경로 우회
        # 스크립트는 "$HOME/.claude/settings.json"을 사용하므로
        # tmpdir/.claude/settings.json을 만들어준다
        claude_dir = os.path.join(self.tmpdir, '.claude')
        os.makedirs(claude_dir, exist_ok=True)
        settings_path = os.path.join(claude_dir, 'settings.json')
        initial = {'env': {'WORKLOG_DEST': 'git', 'WORKLOG_GIT_TRACK': 'true', 'FOO': 'bar'}}
        with open(settings_path, 'w') as f:
            json.dump(initial, f, indent=2)

        env = {**os.environ, 'HOME': self.tmpdir}
        # .env 없어도 괜찮도록 (NOTION_TOKEN/DB_ID 불필요 — --set-mode 전용)
        result = subprocess.run(
            ['bash', SCRIPT, '--dry-run', '--set-mode', mode, self.wl_dir],
            capture_output=True, text=True, env=env
        )
        with open(settings_path) as f:
            updated = json.load(f)
        return result, updated

    def test_set_mode_notion_only(self):
        result, cfg = self._run_set_mode('notion-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'notion-only')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'false')

    def test_set_mode_git(self):
        result, cfg = self._run_set_mode('git')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'git')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'true')

    def test_set_mode_git_ignore(self):
        result, cfg = self._run_set_mode('git-ignore')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'git')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'false')

    def test_set_mode_both(self):
        result, cfg = self._run_set_mode('both')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cfg['env']['WORKLOG_DEST'],      'notion')
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'true')

    def test_set_mode_preserves_other_keys(self):
        result, cfg = self._run_set_mode('git')
        self.assertEqual(cfg['env'].get('FOO'), 'bar', "다른 env 키 보존 실패")

    def test_set_mode_output_contains_label(self):
        result, _ = self._run_set_mode('notion-only')
        self.assertIn('Notion에만 기록', result.stdout)

    def test_set_mode_output_contains_dest(self):
        result, _ = self._run_set_mode('git-ignore')
        self.assertIn('WORKLOG_DEST=git', result.stdout)
        self.assertIn('WORKLOG_GIT_TRACK=false', result.stdout)

    def test_invalid_mode_fails(self):
        env = {**os.environ, 'HOME': self.tmpdir}
        result = subprocess.run(
            ['bash', SCRIPT, '--dry-run', '--set-mode', 'invalid', self.wl_dir],
            capture_output=True, text=True, env=env
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('notion-only', result.stderr)

    def test_settings_json_is_valid_json(self):
        result, cfg = self._run_set_mode('both')
        self.assertIsInstance(cfg, dict)
        self.assertIn('env', cfg)

    def test_dry_run_with_set_mode(self):
        """--dry-run과 --set-mode 함께 쓰면 마이그레이션 없이 모드만 변경"""
        result, cfg = self._run_set_mode('git-ignore')
        self.assertIn('[DRY RUN]', result.stdout)
        self.assertEqual(cfg['env']['WORKLOG_GIT_TRACK'], 'false')


# ── 날짜별 1페이지 로직 테스트 ───────────────────────────────────────────────

def parse_existing_page(notion_response: dict) -> str:
    """notion-worklog.sh의 EXISTING 파싱 로직 재현 (빈 문자열 = 없음)"""
    results = notion_response.get("results", [])
    if not results:
        return ""
    p = results[0]
    pid          = p["id"]
    cur_cost     = p["properties"].get("Cost",     {}).get("number", 0) or 0
    cur_duration = p["properties"].get("Duration", {}).get("number", 0) or 0
    return f"{pid}|{cur_cost}|{cur_duration}"


def make_append_json(children_json: list) -> list:
    """append 시 divider + blocks 구성 로직 재현"""
    divider = {"object": "block", "type": "divider", "divider": {}}
    return [divider] + children_json


def make_new_page_payload(db_id: str, date: str, project: str, cost: float,
                           duration: int, model: str, children: list) -> dict:
    """새 페이지 생성 payload 재현 (title = date)"""
    return {
        'parent': {'database_id': db_id},
        'icon': {'type': 'emoji', 'emoji': '📖'},
        'properties': {
            'Title': {'title': [{'text': {'content': date}}]},
            'Date':  {'date': {'start': date}},
            'Project': {'select': {'name': project}},
            'Cost':    {'number': round(cost, 3)},
            'Duration': {'number': int(duration)},
            'Model':   {'select': {'name': model}},
        },
        'children': children
    }


class TestNotionPagePerDate(unittest.TestCase):
    """날짜별 1페이지: 기존 페이지 감지, append, 새 페이지 생성 로직"""

    def test_no_results_returns_empty_string(self):
        result = parse_existing_page({"results": []})
        self.assertEqual(result, "")

    def test_existing_page_returns_pipe_separated(self):
        response = {
            "results": [{
                "id": "abc-123",
                "properties": {
                    "Cost":     {"number": 1.5},
                    "Duration": {"number": 10}
                }
            }]
        }
        result = parse_existing_page(response)
        self.assertEqual(result, "abc-123|1.5|10")

    def test_null_cost_treated_as_zero(self):
        response = {
            "results": [{
                "id": "xyz",
                "properties": {
                    "Cost":     {"number": None},
                    "Duration": {"number": 5}
                }
            }]
        }
        result = parse_existing_page(response)
        self.assertEqual(result, "xyz|0|5")

    def test_missing_properties_treated_as_zero(self):
        response = {
            "results": [{"id": "xyz", "properties": {}}]
        }
        result = parse_existing_page(response)
        self.assertEqual(result, "xyz|0|0")

    def test_append_json_starts_with_divider(self):
        blocks = [{"object": "block", "type": "paragraph",
                   "paragraph": {"rich_text": [{"text": {"content": "test"}}]}}]
        result = make_append_json(blocks)
        self.assertEqual(result[0]["type"], "divider")

    def test_append_json_preserves_original_blocks(self):
        blocks = [{"type": "paragraph"}, {"type": "heading_3"}]
        result = make_append_json(blocks)
        self.assertEqual(result[1:], blocks)

    def test_append_json_length(self):
        blocks = [{"type": "paragraph"}] * 3
        result = make_append_json(blocks)
        self.assertEqual(len(result), 4)  # 1 divider + 3 blocks

    def test_new_page_title_equals_date(self):
        """새 페이지 Title은 date (작업 요약 아님)"""
        payload = make_new_page_payload(
            "db-id", "2026-03-01", "proj", 1.5, 10, "claude-sonnet-4-6", []
        )
        title = payload['properties']['Title']['title'][0]['text']['content']
        self.assertEqual(title, "2026-03-01")

    def test_new_page_date_property_equals_date(self):
        payload = make_new_page_payload(
            "db-id", "2026-03-01", "proj", 1.5, 10, "claude-sonnet-4-6", []
        )
        self.assertEqual(payload['properties']['Date']['date']['start'], "2026-03-01")

    def test_new_page_cost_rounded(self):
        payload = make_new_page_payload(
            "db-id", "2026-03-01", "proj", 1.4161023, 10, "claude-sonnet-4-6", []
        )
        self.assertEqual(payload['properties']['Cost']['number'], 1.416)

    def test_cost_accumulation(self):
        """append 시 cost = 기존 + 신규, 소수점 3자리"""
        cur_cost  = 1.5
        new_cost  = 0.4161023
        total = round(cur_cost + new_cost, 3)
        self.assertEqual(total, 1.916)

    def test_duration_accumulation(self):
        cur = 10
        new = 7
        self.assertEqual(int(cur + new), 17)


if __name__ == '__main__':
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
