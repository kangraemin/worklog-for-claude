#!/usr/bin/env python3
"""
install.sh e2e 테스트

격리된 임시 디렉토리에서 실제 install.sh를 실행하여
- 신규 설치: 파일 배포, settings.json 구성, 실행 권한
- 재설치: 중복 훅 방지, 기존 env/훅 보존, 설정값 업데이트
- 각 저장 모드 (git / both / notion-only)
- .env 파일 생성·갱신·권한
- 로컬 스코프 설치
- 사전 조건 미충족 시 실패

Run: python3 tests/test_install_e2e.py
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTALL_SCRIPT = os.path.join(PACKAGE_DIR, "install.sh")

# install.sh 가 배포하는 파일 목록
EXPECTED_FILES = [
    "scripts/notion-worklog.sh",
    "scripts/notion-migrate-worklogs.sh",
    "scripts/duration.py",
    "hooks/worklog.sh",
    "hooks/session-end.sh",
    "commands/worklog.md",
    "commands/migrate-worklogs.md",
    "rules/worklog-rules.md",
]

# 실행 권한이 필요한 파일
EXPECTED_EXEC = [
    "scripts/notion-worklog.sh",
    "scripts/notion-migrate-worklogs.sh",
    "hooks/worklog.sh",
    "hooks/session-end.sh",
]


def _write_stub(path: str, content: str = "#!/bin/bash\necho stub\n") -> None:
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


class _Base(unittest.TestCase):
    """공통 픽스처·헬퍼"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai_wl_test_")
        self._bin = os.path.join(self.tmp, "bin")
        os.makedirs(self._bin)
        # claude: 사전 조건 체크 통과용 스텁
        _write_stub(os.path.join(self._bin, "claude"))
        # ccusage: 선택 설치 프롬프트가 나오지 않도록 스텁
        _write_stub(os.path.join(self._bin, "ccusage"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 환경 ──────────────────────────────────────────────────────────────────

    def _env(self) -> dict:
        """fake bin 이 PATH 앞에 오도록, HOME 을 tmp 로 오버라이드"""
        return {
            **os.environ,
            "HOME": self.tmp,
            "PATH": f'{self._bin}:{os.environ.get("PATH", "")}',
        }

    def _run(self, inputs: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", INSTALL_SCRIPT],
            input="\n".join(inputs) + "\n",
            capture_output=True,
            text=True,
            env=self._env(),
            cwd=cwd or self.tmp,
            timeout=30,
        )

    # ── 어시스턴트 ──────────────────────────────────────────────────────────────

    def _settings(self, target: str | None = None) -> dict:
        if target is None:
            target = os.path.join(self.tmp, ".claude")
        with open(os.path.join(target, "settings.json")) as f:
            return json.load(f)

    def _hook_commands(self, cfg: dict, event: str) -> list[str]:
        return [
            h.get("command", "")
            for g in cfg.get("hooks", {}).get(event, [])
            for h in g.get("hooks", [])
        ]

    def _assert_files(self, target: str) -> None:
        for rel in EXPECTED_FILES:
            self.assertTrue(
                os.path.exists(os.path.join(target, rel)),
                f"파일 없음: {rel}",
            )

    def _assert_exec(self, target: str) -> None:
        for rel in EXPECTED_EXEC:
            path = os.path.join(target, rel)
            self.assertTrue(
                os.stat(path).st_mode & stat.S_IXUSR,
                f"실행 권한 없음: {rel}",
            )

    def _find_hook(self, cfg: dict, event: str, filename: str) -> dict | None:
        for g in cfg.get("hooks", {}).get(event, []):
            for h in g.get("hooks", []):
                if filename in h.get("command", ""):
                    return h
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 1. 신규 설치 — git-only 모드
# ══════════════════════════════════════════════════════════════════════════════


class TestFreshGitInstall(_Base):
    """신규 설치: git-only, 글로벌 스코프"""

    # 입력 순서: scope=global, dest=git, git-track=track, timing=each-commit
    _BASE = ["1", "1", "3", "1", "1"]

    def test_exit_zero(self):
        r = self._run(self._BASE)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_all_files_installed(self):
        self._run(self._BASE)
        self._assert_files(os.path.join(self.tmp, ".claude"))

    def test_exec_permissions(self):
        self._run(self._BASE)
        self._assert_exec(os.path.join(self.tmp, ".claude"))

    def test_settings_env_git_track(self):
        self._run(self._BASE)
        env = self._settings()["env"]
        self.assertEqual(env["WORKLOG_DEST"], "git")
        self.assertEqual(env["WORKLOG_GIT_TRACK"], "true")
        self.assertEqual(env["WORKLOG_TIMING"], "each-commit")
        self.assertEqual(env["WORKLOG_LANG"], "ko")

    def test_settings_env_english_lang(self):
        self._run(["2", "1", "3", "1", "1"])  # lang=en, scope=global, git, track, each-commit
        self.assertEqual(self._settings()["env"]["WORKLOG_LANG"], "en")

    def test_ai_worklog_dir_points_to_target(self):
        self._run(self._BASE)
        expected = os.path.realpath(os.path.join(self.tmp, ".claude"))
        actual = os.path.realpath(self._settings()["env"]["AI_WORKLOG_DIR"])
        self.assertEqual(actual, expected)

    def test_posttooluse_hook_added(self):
        self._run(self._BASE)
        hooks = self._settings().get("hooks", {})
        self.assertIn("PostToolUse", hooks)

    def test_settings_json_is_valid(self):
        self._run(self._BASE)
        cfg = self._settings()
        self.assertIsInstance(cfg, dict)
        self.assertIn("env", cfg)
        self.assertIn("hooks", cfg)

    def test_output_contains_success_message(self):
        r = self._run(self._BASE)
        self.assertIn("설치가 완료", r.stdout)

    def test_git_ignore_mode(self):
        # scope=global, dest=git, git-track=gitignore, timing=each-commit
        r = self._run(["1", "1", "3", "2", "1"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._settings()["env"]["WORKLOG_GIT_TRACK"], "false")

    def test_timing_session_end(self):
        self._run(["1", "1", "3", "1", "2"])
        self.assertEqual(self._settings()["env"]["WORKLOG_TIMING"], "session-end")

    def test_timing_manual(self):
        self._run(["1", "1", "3", "1", "3"])
        self.assertEqual(self._settings()["env"]["WORKLOG_TIMING"], "manual")

    def test_notion_db_id_not_added_for_git_mode(self):
        """git 모드에서는 NOTION_DB_ID 가 env 에 추가되지 않음"""
        self._run(self._BASE)
        self.assertNotIn("NOTION_DB_ID", self._settings()["env"])


# ══════════════════════════════════════════════════════════════════════════════
# 2. 신규 설치 — Notion 모드 (기존 인증정보 사전 주입)
# ══════════════════════════════════════════════════════════════════════════════


class TestFreshNotionInstallWithCreds(_Base):
    """신규 설치: Notion 모드, .env + settings.json 에 인증정보 사전 주입 → API 호출 없음"""

    def setUp(self):
        super().setUp()
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d)
        env_file = os.path.join(d, ".env")
        with open(env_file, "w") as f:
            f.write("NOTION_TOKEN=secret_fake_xyz\n")
        os.chmod(env_file, 0o600)
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump({"env": {"NOTION_DB_ID": "fake-db-abc"}}, f)

    def test_both_mode_exit_zero(self):
        # scope=global, dest=both, timing=each-commit
        self.assertEqual(self._run(["1", "1", "1", "1"]).returncode, 0)

    def test_both_mode_dest_and_git_track(self):
        self._run(["1", "1", "1", "1"])
        env = self._settings()["env"]
        self.assertEqual(env["WORKLOG_DEST"], "notion")
        self.assertEqual(env["WORKLOG_GIT_TRACK"], "true")

    def test_notion_only_exit_zero(self):
        self.assertEqual(self._run(["1", "1", "2", "1"]).returncode, 0)

    def test_notion_only_dest_and_git_track(self):
        self._run(["1", "1", "2", "1"])
        env = self._settings()["env"]
        self.assertEqual(env["WORKLOG_DEST"], "notion-only")
        self.assertEqual(env["WORKLOG_GIT_TRACK"], "false")

    def test_notion_db_id_written_to_settings(self):
        self._run(["1", "1", "1", "1"])
        self.assertEqual(self._settings()["env"]["NOTION_DB_ID"], "fake-db-abc")

    def test_output_shows_token_reused(self):
        r = self._run(["1", "1", "1", "1"])
        self.assertIn("기존 NOTION_TOKEN", r.stdout)

    def test_output_shows_db_id_reused(self):
        r = self._run(["1", "1", "1", "1"])
        self.assertIn("기존 NOTION_DB_ID", r.stdout)

    def test_all_files_installed(self):
        self._run(["1", "1", "1", "1"])
        self._assert_files(os.path.join(self.tmp, ".claude"))

    def test_hooks_added(self):
        self._run(["1", "1", "1", "1"])
        self.assertIn("PostToolUse", self._settings().get("hooks", {}))


# ══════════════════════════════════════════════════════════════════════════════
# 3. 신규 설치 — Notion 모드, 토큰 없이 스킵
# ══════════════════════════════════════════════════════════════════════════════


class TestNotionInstallNoToken(_Base):
    """토큰 빈 값 입력 → 경고 후 설치 계속"""

    def test_notion_only_no_token_exits_zero(self):
        # scope=global, dest=notion-only, token=empty, timing=each-commit
        r = self._run(["1", "1", "2", "", "1"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_both_no_token_exits_zero(self):
        r = self._run(["1", "1", "1", "", "1"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_files_installed_without_token(self):
        self._run(["1", "1", "2", "", "1"])
        self._assert_files(os.path.join(self.tmp, ".claude"))

    def test_hooks_added_without_token(self):
        self._run(["1", "1", "2", "", "1"])
        self.assertIn("PostToolUse", self._settings().get("hooks", {}))

    def test_no_token_in_env_file(self):
        """토큰 없으면 .env 에 NOTION_TOKEN 이 기록되지 않음"""
        self._run(["1", "1", "2", "", "1"])
        env_file = os.path.join(self.tmp, ".claude", ".env")
        if os.path.exists(env_file):
            self.assertNotIn("NOTION_TOKEN=", open(env_file).read())


# ══════════════════════════════════════════════════════════════════════════════
# 4. 재설치 — 중복 방지 + 기존 설정 보존
# ══════════════════════════════════════════════════════════════════════════════


class TestReinstall(_Base):
    """재설치: 훅 중복 방지, env 보존, 설정값 갱신"""

    def _seed_settings(self, extra_env: dict | None = None, extra_hooks: dict | None = None):
        """훅이 이미 설치된 settings.json 생성"""
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d, exist_ok=True)
        env = {
            "WORKLOG_DEST": "git",
            "WORKLOG_GIT_TRACK": "true",
            "WORKLOG_TIMING": "each-commit",
            "AI_WORKLOG_DIR": d,
        }
        if extra_env:
            env.update(extra_env)
        cfg: dict = {
            "env": env,
            "hooks": {
                "PostToolUse": [{"hooks": [{"type": "command", "command": f"{d}/hooks/worklog.sh", "timeout": 5, "async": True}]}],
            },
        }
        if extra_hooks:
            cfg["hooks"].update(extra_hooks)
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump(cfg, f, indent=2)

    def test_no_duplicate_hooks(self):
        """재설치 시 동일 command 가 중복 추가되지 않음"""
        self._seed_settings()
        self._run(["1", "1", "3", "1", "1"])
        cfg = self._settings()
        cmds = [c for c in self._hook_commands(cfg, "PostToolUse") if "hooks/" in c]
        self.assertEqual(len(cmds), 1, f"중복 훅 발견: {cmds}")

    def test_unrelated_env_keys_preserved(self):
        """worklog 와 무관한 env 키는 재설치 후에도 보존"""
        self._seed_settings(extra_env={"MY_KEY": "keep_me", "FOO": "bar"})
        self._run(["1", "1", "3", "1", "1"])
        env = self._settings()["env"]
        self.assertEqual(env.get("MY_KEY"), "keep_me")
        self.assertEqual(env.get("FOO"), "bar")

    def test_timing_updated_on_reinstall(self):
        self._seed_settings()
        self._run(["1", "1", "3", "1", "2"])  # session-end
        self.assertEqual(self._settings()["env"]["WORKLOG_TIMING"], "session-end")

    def test_dest_updated_on_reinstall(self):
        """git → notion-only 변경"""
        self._seed_settings()
        d = os.path.join(self.tmp, ".claude")
        # .env 에 토큰, settings 에 NOTION_DB_ID 주입
        with open(os.path.join(d, ".env"), "w") as f:
            f.write("NOTION_TOKEN=fake_token\n")
        cfg = self._settings()
        cfg["env"]["NOTION_DB_ID"] = "fake-db"
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump(cfg, f, indent=2)
        self._run(["1", "1", "2", "1"])  # notion-only
        self.assertEqual(self._settings()["env"]["WORKLOG_DEST"], "notion-only")

    def test_backup_created_on_reinstall(self):
        """재설치 시 기존 파일을 .bak 으로 백업"""
        self._run(["1", "1", "3", "1", "1"])   # 첫 설치
        r = self._run(["1", "1", "3", "1", "1"])  # 재설치
        self.assertIn("백업", r.stdout)

    def test_settings_json_valid_after_reinstall(self):
        self._seed_settings()
        self._run(["1", "1", "3", "1", "1"])
        cfg = self._settings()
        self.assertIsInstance(cfg, dict)
        self.assertIn("env", cfg)
        self.assertIn("hooks", cfg)

    def test_third_party_hooks_preserved_after_reinstall(self):
        """타사 훅 보존"""
        self._seed_settings(
            extra_hooks={"PreToolUse": [{"hooks": [{"type": "command", "command": "/opt/lint.sh", "timeout": 5}]}]}
        )
        self._run(["1", "1", "3", "1", "1"])
        cfg = self._settings()
        self.assertIn("PreToolUse", cfg["hooks"])
        self.assertTrue(any("lint.sh" in c for c in self._hook_commands(cfg, "PreToolUse")))


# ══════════════════════════════════════════════════════════════════════════════
# 5. 기존 settings.json (타사 훅 + env) 보존
# ══════════════════════════════════════════════════════════════════════════════


class TestExistingSettingsMerge(_Base):
    """기존 settings.json 이 있을 때 올바르게 머지"""

    def setUp(self):
        super().setUp()
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d)
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump(
                {
                    "env": {"OTHER_KEY": "v1", "API_KEY": "secret"},
                    "hooks": {
                        "PostToolUse": [{"hooks": [{"type": "command", "command": "/opt/other.sh", "timeout": 10}]}],
                        "PreToolUse":  [{"hooks": [{"type": "command", "command": "/opt/lint.sh", "timeout": 5}]}],
                    },
                },
                f,
            )

    def test_existing_env_preserved(self):
        self._run(["1", "1", "3", "1", "1"])
        env = self._settings()["env"]
        self.assertEqual(env.get("OTHER_KEY"), "v1")
        self.assertEqual(env.get("API_KEY"), "secret")

    def test_existing_pretooluse_hook_preserved(self):
        self._run(["1", "1", "3", "1", "1"])
        cmds = self._hook_commands(self._settings(), "PreToolUse")
        self.assertTrue(any("lint.sh" in c for c in cmds))

    def test_existing_posttooluse_hook_preserved(self):
        self._run(["1", "1", "3", "1", "1"])
        cmds = self._hook_commands(self._settings(), "PostToolUse")
        self.assertTrue(any("other.sh" in c for c in cmds))

    def test_worklog_hook_added_alongside_existing(self):
        self._run(["1", "1", "3", "1", "1"])
        cmds = self._hook_commands(self._settings(), "PostToolUse")
        self.assertTrue(any("worklog.sh" in c for c in cmds))


# ══════════════════════════════════════════════════════════════════════════════
# 6. 훅 구조 검증 (async / timeout)
# ══════════════════════════════════════════════════════════════════════════════


class TestHookStructure(_Base):
    def setUp(self):
        super().setUp()
        self._run(["1", "1", "3", "1", "1"])
        self._cfg = self._settings()
        self._target = os.path.join(self.tmp, ".claude")

    def test_posttooluse_is_async(self):
        h = self._find_hook(self._cfg, "PostToolUse", "worklog.sh")
        self.assertIsNotNone(h)
        self.assertTrue(h.get("async"))

    def test_posttooluse_timeout_5(self):
        h = self._find_hook(self._cfg, "PostToolUse", "worklog.sh")
        self.assertEqual(h["timeout"], 5)

    def test_hook_type_is_command(self):
        h = self._find_hook(self._cfg, "PostToolUse", "worklog.sh")
        self.assertEqual(h["type"], "command")

    def test_hook_command_points_to_target_dir(self):
        real_target = os.path.realpath(self._target)
        h = self._find_hook(self._cfg, "PostToolUse", "worklog.sh")
        self.assertTrue(os.path.realpath(h["command"]).startswith(real_target))

    def test_stop_not_registered(self):
        hooks = self._cfg.get("hooks", {})
        self.assertNotIn("Stop", hooks)

    def test_session_end_registered(self):
        hooks = self._cfg.get("hooks", {})
        self.assertIn("SessionEnd", hooks)
        h = self._find_hook(self._cfg, "SessionEnd", "session-end.sh")
        self.assertIsNotNone(h)


# ══════════════════════════════════════════════════════════════════════════════
# 7. .env 파일 처리
# ══════════════════════════════════════════════════════════════════════════════


class TestEnvFileHandling(_Base):
    def _seed_db_id(self):
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump({"env": {"NOTION_DB_ID": "fake-db-id"}}, f)

    def test_env_created_with_new_token(self):
        """토큰 입력 시 .env 파일 생성 및 토큰 기록"""
        self._seed_db_id()
        # scope=global, dest=both, token=my_secret_token, timing=each-commit
        self._run(["1", "1", "1", "my_secret_token", "1"])
        env_path = os.path.join(self.tmp, ".claude", ".env")
        self.assertTrue(os.path.exists(env_path))
        with open(env_path) as f:
            self.assertIn("NOTION_TOKEN=my_secret_token", f.read())

    def test_env_file_permission_600(self):
        self._seed_db_id()
        self._run(["1", "1", "1", "my_secret_token", "1"])
        env_path = os.path.join(self.tmp, ".claude", ".env")
        if os.path.exists(env_path):
            mode = stat.S_IMODE(os.stat(env_path).st_mode)
            self.assertEqual(mode, 0o600, f"expected 600, got {oct(mode)}")

    def test_existing_token_reused_no_overwrite(self):
        """기존 .env 의 NOTION_TOKEN 은 재사용되며 다른 변수는 보존"""
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".env"), "w") as f:
            f.write("NOTION_TOKEN=old_token_abc\nOTHER_VAR=keep\n")
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump({"env": {"NOTION_DB_ID": "fake-db-id"}}, f)

        # 토큰이 자동 감지되므로 추가 입력 불필요
        r = self._run(["1", "1", "1", "1"])
        self.assertIn("기존 NOTION_TOKEN", r.stdout)
        with open(os.path.join(d, ".env")) as f:
            content = f.read()
        self.assertIn("NOTION_TOKEN=old_token_abc", content)
        self.assertIn("OTHER_VAR=keep", content)

    def test_token_updated_in_existing_env(self):
        """기존 .env 의 NOTION_TOKEN 이 있을 때 재설치해도 그대로 유지"""
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".env"), "w") as f:
            f.write("NOTION_TOKEN=existing_token\n")
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump({"env": {"NOTION_DB_ID": "fake-db-id"}}, f)

        self._run(["1", "1", "1", "1"])
        with open(os.path.join(d, ".env")) as f:
            content = f.read()
        # 기존 토큰이 그대로 있어야 함 (재사용 경로)
        self.assertIn("NOTION_TOKEN=existing_token", content)


# ══════════════════════════════════════════════════════════════════════════════
# 8. 로컬 스코프 설치
# ══════════════════════════════════════════════════════════════════════════════


class TestLocalScopeInstall(_Base):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", self.tmp], capture_output=True, check=False)
        subprocess.run(["git", "-C", self.tmp, "config", "user.email", "test@test.com"], capture_output=True, check=False)
        subprocess.run(["git", "-C", self.tmp, "config", "user.name", "Test"], capture_output=True, check=False)

    def test_files_in_local_claude_dir(self):
        r = self._run(["1", "2", "3", "1", "1"], cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self._assert_files(os.path.join(self.tmp, ".claude"))

    def test_ai_worklog_dir_is_local_claude(self):
        self._run(["1", "2", "3", "1", "1"], cwd=self.tmp)
        expected = os.path.realpath(os.path.join(self.tmp, ".claude"))
        actual = os.path.realpath(self._settings()["env"]["AI_WORKLOG_DIR"])
        self.assertEqual(actual, expected)

    def test_hooks_use_local_paths(self):
        self._run(["1", "2", "3", "1", "1"], cwd=self.tmp)
        cfg = self._settings()
        real_local = os.path.realpath(os.path.join(self.tmp, ".claude"))
        h = self._find_hook(cfg, "PostToolUse", "worklog.sh")
        self.assertIsNotNone(h, "PostToolUse/worklog.sh 훅 없음")
        self.assertTrue(os.path.realpath(h["command"]).startswith(real_local))

    def test_gitignore_mode_adds_worklogs_entry(self):
        """git-ignore 모드: .gitignore 에 .worklogs/ 추가"""
        self._run(["1", "2", "3", "2", "1"], cwd=self.tmp)
        gitignore = os.path.join(self.tmp, ".gitignore")
        if os.path.exists(gitignore):
            with open(gitignore) as f:
                self.assertIn(".worklogs/", f.read())


# ══════════════════════════════════════════════════════════════════════════════
# 9. 사전 조건 실패
# ══════════════════════════════════════════════════════════════════════════════


class TestPrerequisiteFailure(_Base):
    def test_fails_when_claude_missing(self):
        """claude 없으면 exit 1 + 오류 메시지"""
        # fake bin 에서 claude 제거
        os.remove(os.path.join(self._bin, "claude"))
        # python3·curl·jq 스텁 추가 (다른 필수 도구 누락 방지)
        for cmd in ["python3", "curl", "jq"]:
            _write_stub(os.path.join(self._bin, cmd))

        env = {**os.environ, "HOME": self.tmp, "PATH": f"{self._bin}:/bin:/usr/bin"}
        r = subprocess.run(
            ["bash", INSTALL_SCRIPT],
            input="1\n3\n1\n1\n",
            capture_output=True,
            text=True,
            env=env,
            cwd=self.tmp,
            timeout=15,
        )
        self.assertNotEqual(r.returncode, 0)
        combined = r.stdout + r.stderr
        self.assertIn("claude", combined.lower())


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
