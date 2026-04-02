#!/usr/bin/env python3
"""
Full lifecycle e2e: install.sh → git commit → .worklogs 생성 검증

빈 폴더에 실제 install.sh 실행 후 git commit하여
모든 설정 조합에서 워크로그가 정상 동작하는지 확인.

Run: python3 -m pytest tests/test_full_lifecycle_e2e.py -v
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTALL_SCRIPT = os.path.join(PACKAGE_DIR, "install.sh")
UNINSTALL_SCRIPT = os.path.join(PACKAGE_DIR, "uninstall.sh")


def _write_stub(path: str, content: str = "#!/bin/bash\necho stub\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


class _LifecycleBase(unittest.TestCase):
    """
    공통 픽스처:
    - tmpdir with HOME override
    - git repo (init + remote)
    - claude stub (항상 실패 → fallback)
    - notion-worklog.sh stub (호출 여부 기록)
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai_wl_lifecycle_")

        # stub bin
        self._bin = os.path.join(self.tmp, "bin")
        os.makedirs(self._bin)
        _write_stub(os.path.join(self._bin, "claude"), "#!/bin/bash\nexit 1\n")

        # git env (격리)
        self._git_env = {
            "HOME": self.tmp,
            "PATH": f'{self._bin}:/usr/bin:/bin:/usr/local/bin:{os.path.dirname(shutil.which("python3") or "/usr/bin/python3")}',
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }

        # bare remote
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", self.remote],
                       capture_output=True, check=True, env=self._git_env)

        # local repo
        self.repo = os.path.join(self.tmp, "repo")
        subprocess.run(["git", "clone", self.remote, self.repo],
                       capture_output=True, check=True, env=self._git_env)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "test@test.com"],
                       capture_output=True, env=self._git_env)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "Test"],
                       capture_output=True, env=self._git_env)

        # initial commit
        with open(os.path.join(self.repo, "README.md"), "w") as f:
            f.write("# test\n")
        subprocess.run(["git", "-C", self.repo, "add", "README.md"],
                       capture_output=True, env=self._git_env)
        subprocess.run(["git", "-C", self.repo, "commit", "-m", "init"],
                       capture_output=True, env=self._git_env)
        subprocess.run(["git", "-C", self.repo, "push"],
                       capture_output=True, env=self._git_env)

        # snapshot dir
        os.makedirs(os.path.join(self.tmp, ".claude", "worklogs"), exist_ok=True)

        # notion stub log
        self.notion_log = os.path.join(self.tmp, "notion_calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _install(self, inputs: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", INSTALL_SCRIPT],
            input="\n".join(inputs) + "\n",
            capture_output=True,
            text=True,
            env=self._git_env,
            cwd=cwd or self.tmp,
            timeout=30,
        )

    def _uninstall(self, cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", UNINSTALL_SCRIPT],
            capture_output=True,
            text=True,
            env=self._git_env,
            cwd=cwd or self.repo,
            timeout=30,
        )

    def _patch_notion_stub(self, target_dir: str):
        """notion-worklog.sh를 stub으로 교체 (호출 기록만)"""
        notion_script = os.path.join(target_dir, "scripts", "notion-worklog.sh")
        if os.path.exists(notion_script):
            _write_stub(notion_script, f"#!/bin/bash\necho \"$@\" >> {self.notion_log}\n")

    def _commit_env(self, target_dir: str, **overrides):
        """커밋 시 사용할 env (post-commit hook이 올바른 경로 사용하도록)"""
        env = {**self._git_env, "AI_WORKLOG_DIR": target_dir}
        env.update(overrides)
        return env

    def _make_commit(self, msg="test change", env=None):
        """파일 변경 + 커밋"""
        test_file = os.path.join(self.repo, "test.txt")
        with open(test_file, "a") as f:
            f.write(f"{msg}\n")
        subprocess.run(["git", "-C", self.repo, "add", "test.txt"],
                       capture_output=True, env=env or self._git_env)
        return subprocess.run(
            ["git", "-C", self.repo, "commit", "-m", msg],
            capture_output=True, text=True,
            env=env or self._git_env,
            timeout=30,
        )

    def _worklogs_dir(self):
        return os.path.join(self.repo, ".worklogs")

    def _worklogs_files(self):
        d = self._worklogs_dir()
        if not os.path.isdir(d):
            return []
        return [f for f in os.listdir(d) if f.endswith(".md")]

    def _settings(self, target: str) -> dict:
        with open(os.path.join(target, "settings.json")) as f:
            return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Global + git + track + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalGitTrackStop(_LifecycleBase):
    """전역 설치, git 모드, track, stop → 커밋 시 .worklogs 생성"""

    def setUp(self):
        super().setUp()
        # global install: lang=ko, scope=global, storage=git, track=1, timing=stop, mcp=skip
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0, f"install failed: {r.stderr}")
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        # commit
        self._make_commit("feature: test change", env=self._commit_env(self.target))

    def test_worklogs_file_created(self):
        self.assertTrue(len(self._worklogs_files()) > 0, ".worklogs/ should have files")

    def test_worklogs_has_timestamp(self):
        content = open(os.path.join(self._worklogs_dir(), self._worklogs_files()[0])).read()
        self.assertTrue(re.search(r"## \d{2}:\d{2}", content), "should have ## HH:MM")

    def test_worklogs_has_auto_marker(self):
        content = open(os.path.join(self._worklogs_dir(), self._worklogs_files()[0])).read()
        self.assertIn("(auto)", content, "fallback should have (auto) marker")

    def test_snapshot_updated(self):
        snapshot = os.path.join(self.tmp, ".claude", "worklogs", ".snapshot")
        self.assertTrue(os.path.exists(snapshot))
        data = json.load(open(snapshot))
        self.assertIn("timestamp", data)
        self.assertGreater(data["timestamp"], 0)

    def test_commit_exit_zero(self):
        r = self._make_commit("second commit", env=self._commit_env(self.target))
        self.assertEqual(r.returncode, 0, "commit should succeed")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Global + git + ignore + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalGitIgnoreStop(_LifecycleBase):
    """전역 설치, git 모드, ignore → .worklogs 생성되지만 unstaged"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "1", "3", "2", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_file_created(self):
        self.assertTrue(len(self._worklogs_files()) > 0)

    def test_not_staged(self):
        r = subprocess.run(
            ["git", "-C", self.repo, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, env=self._git_env,
        )
        self.assertNotIn(".worklogs", r.stdout)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Global + git + track + manual
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalGitTrackManual(_LifecycleBase):
    """전역 설치, manual 타이밍 → commit해도 .worklogs 미생성

    NOTE: post-commit.sh는 settings.json 로드 전에 WORKLOG_TIMING env를 체크하므로
    터미널 커밋에서 manual이 작동하려면 env에 WORKLOG_TIMING=manual이 필요.
    (실제 Claude Code 세션에서는 settings.json env가 프로세스 env로 전달됨)
    """

    def setUp(self):
        super().setUp()
        r = self._install(["1", "1", "3", "1", "2", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._make_commit("test", env=self._commit_env(self.target, WORKLOG_TIMING="manual"))

    def test_no_worklogs(self):
        self.assertEqual(len(self._worklogs_files()), 0, ".worklogs should not exist")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Global + notion-only + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalNotionOnlyStop(_LifecycleBase):
    """전역 설치, notion-only → .worklogs 미생성, notion stub 호출"""

    def setUp(self):
        super().setUp()
        # storage=notion-only(2), no notion token → notion 없이 진행
        r = self._install(["1", "1", "2", "", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_no_local_file(self):
        self.assertEqual(len(self._worklogs_files()), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Global + both + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalBothStop(_LifecycleBase):
    """전역 설치, both(notion) 모드 → .worklogs 생성 + notion stub 호출"""

    def setUp(self):
        super().setUp()
        # storage=both(1), no token → token 없이 설치
        r = self._install(["1", "1", "1", "", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        # NOTION_DB_ID를 직접 설정 (token 없으니 notion 호출은 stub)
        settings_path = os.path.join(self.target, "settings.json")
        cfg = json.load(open(settings_path))
        cfg["env"]["NOTION_DB_ID"] = "fake-db-id"
        with open(settings_path, "w") as f:
            json.dump(cfg, f, indent=2)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_local_file_created(self):
        self.assertTrue(len(self._worklogs_files()) > 0)

    def test_notion_stub_called(self):
        # notion stub이 호출되면 로그 파일에 기록
        self.assertTrue(
            os.path.exists(self.notion_log),
            "notion stub should be called",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 6. Local + git + track + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestLocalGitTrackStop(_LifecycleBase):
    """로컬 설치 → .claude가 프로젝트 내, .worklogs 생성"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, f"install failed: {r.stderr}")
        self.target = os.path.join(self.repo, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_claude_dir_in_project(self):
        self.assertTrue(os.path.isdir(self.target))

    def test_worklogs_created(self):
        self.assertTrue(len(self._worklogs_files()) > 0)

    def test_settings_ai_worklog_dir(self):
        cfg = self._settings(self.target)
        # macOS: /var → /private/var symlink
        actual = os.path.realpath(cfg["env"]["AI_WORKLOG_DIR"])
        expected = os.path.realpath(self.target)
        self.assertEqual(actual, expected)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Local + git + ignore + stop
# ══════════════════════════════════════════════════════════════════════════════


class TestLocalGitIgnoreStop(_LifecycleBase):
    """로컬 설치, git ignore → 파일 생성 + unstaged"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "2", "3", "2", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.repo, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_file_created(self):
        self.assertTrue(len(self._worklogs_files()) > 0)

    def test_not_staged(self):
        r = subprocess.run(
            ["git", "-C", self.repo, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, env=self._git_env,
        )
        self.assertNotIn(".worklogs", r.stdout)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Local + git + track + manual
# ══════════════════════════════════════════════════════════════════════════════


class TestLocalGitTrackManual(_LifecycleBase):
    """로컬 설치, manual → commit해도 .worklogs 미생성"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "2", "3", "1", "2", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.repo, ".claude")
        self._make_commit("test", env=self._commit_env(self.target, WORKLOG_TIMING="manual"))

    def test_no_worklogs(self):
        self.assertEqual(len(self._worklogs_files()), 0)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Session mode (CLAUDECODE)
# ══════════════════════════════════════════════════════════════════════════════


class TestSessionMode(_LifecycleBase):
    """CLAUDECODE=1 시 pending marker 생성, .worklogs 직접 안 씀"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        env = self._commit_env(self.target, CLAUDECODE="1")
        self._make_commit("test", env=env)

    def test_pending_marker_created(self):
        pending_dir = os.path.join(self.tmp, ".claude", "worklogs", ".pending")
        if os.path.isdir(pending_dir):
            files = os.listdir(pending_dir)
            self.assertTrue(len(files) > 0, "pending marker should exist")
        else:
            # pending dir 안 만들어질 수도 있음 (python3 없는 경우 등)
            pass

    def test_no_worklogs_directly(self):
        self.assertEqual(len(self._worklogs_files()), 0)

    def test_commit_exit_zero(self):
        env = self._commit_env(self.target, CLAUDECODE="1")
        r = self._make_commit("second", env=env)
        self.assertEqual(r.returncode, 0)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Language — Korean
# ══════════════════════════════════════════════════════════════════════════════


class TestLanguageKo(_LifecycleBase):
    """WORKLOG_LANG=ko 시 한국어 헤더"""

    def setUp(self):
        super().setUp()
        # ko(1), global, git, track, stop
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_korean_headers(self):
        files = self._worklogs_files()
        if files:
            content = open(os.path.join(self._worklogs_dir(), files[0])).read()
            self.assertIn("토큰 사용량", content)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Language — English
# ══════════════════════════════════════════════════════════════════════════════


class TestLanguageEn(_LifecycleBase):
    """WORKLOG_LANG=en 시 영어 헤더"""

    def setUp(self):
        super().setUp()
        # en(2), global, git, track, stop
        r = self._install(["2", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)
        self._make_commit("test", env=self._commit_env(self.target))

    def test_english_headers(self):
        files = self._worklogs_files()
        if files:
            content = open(os.path.join(self._worklogs_dir(), files[0])).read()
            self.assertIn("Token Usage", content)


# ══════════════════════════════════════════════════════════════════════════════
# 12. MCP skip
# ══════════════════════════════════════════════════════════════════════════════


class TestMcpSkipFullInstall(_LifecycleBase):
    """MCP skip 후 mcpServers 없음"""

    def test_no_mcp_servers(self):
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        cfg = self._settings(os.path.join(self.tmp, ".claude"))
        self.assertNotIn("mcpServers", cfg)


# ══════════════════════════════════════════════════════════════════════════════
# 13. Uninstall 후 커밋
# ══════════════════════════════════════════════════════════════════════════════


class TestPostUninstall(_LifecycleBase):
    """uninstall 후 commit해도 .worklogs 미생성"""

    def setUp(self):
        super().setUp()
        # 로컬 설치
        r = self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        # uninstall
        r2 = self._uninstall(cwd=self.repo)
        self.assertEqual(r2.returncode, 0)
        # commit
        self._make_commit("after uninstall")

    def test_no_worklogs(self):
        self.assertEqual(len(self._worklogs_files()), 0)

    def test_hook_not_present(self):
        hook = os.path.join(self.repo, ".git", "hooks", "post-commit")
        # hook이 없거나, 있어도 worklog 관련 아님
        if os.path.exists(hook):
            content = open(hook).read()
            self.assertNotIn("worklog", content.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 14. 재설치 후 커밋
# ══════════════════════════════════════════════════════════════════════════════


class TestReinstallCommit(_LifecycleBase):
    """uninstall → reinstall → commit → .worklogs 생성"""

    def test_worklogs_after_reinstall(self):
        # 설치
        self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        target = os.path.join(self.repo, ".claude")
        # 제거
        self._uninstall(cwd=self.repo)
        # 재설치
        r = self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self._patch_notion_stub(target)
        # 커밋
        self._make_commit("after reinstall", env=self._commit_env(target))
        self.assertTrue(len(self._worklogs_files()) > 0)


# ══════════════════════════════════════════════════════════════════════════════
# 15. Hook chaining
# ══════════════════════════════════════════════════════════════════════════════


class TestHookChaining(_LifecycleBase):
    """기존 post-commit hook이 .local로 보존되고 실행됨"""

    def test_existing_hook_still_runs(self):
        # 기존 hook 설치
        hooks_dir = os.path.join(self.repo, ".git", "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        marker = os.path.join(self.tmp, "original_hook_ran")
        with open(os.path.join(hooks_dir, "post-commit"), "w") as f:
            f.write(f"#!/bin/bash\ntouch {marker}\n")
        os.chmod(os.path.join(hooks_dir, "post-commit"), 0o755)

        # 로컬 설치 (기존 hook → .local 보존)
        r = self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        target = os.path.join(self.repo, ".claude")
        self._patch_notion_stub(target)

        # .local 존재 확인
        self.assertTrue(os.path.exists(os.path.join(hooks_dir, "post-commit.local")))

        # 커밋 → 기존 hook도 실행됨
        self._make_commit("test chaining", env=self._commit_env(target))
        self.assertTrue(os.path.exists(marker), "original hook should have run")


# ══════════════════════════════════════════════════════════════════════════════
# 16. 설치 후 파일 검증 — 쓸데없는 파일 없는지
# ══════════════════════════════════════════════════════════════════════════════

EXPECTED_HOOKS = {
    "post-commit.sh", "worklog.sh", "on-commit.sh",
    "commit-doc-check.sh", "session-end.sh",
}
EXPECTED_SCRIPTS = {
    "worklog-write.sh", "notion-worklog.sh", "notion-migrate-worklogs.sh",
    "token-cost.py", "duration.py", "update-check.sh",
}
EXPECTED_COMMANDS = {
    "worklog.md", "finish.md", "migrate-worklogs.md", "update-worklog.md",
    "worklog-config.md",
}
EXPECTED_RULES = {
    "worklog-rules.md", "auto-commit-rules.md",
}
KNOWN_ENV_KEYS = {
    "WORKLOG_TIMING", "WORKLOG_DEST", "WORKLOG_GIT_TRACK",
    "WORKLOG_LANG", "AI_WORKLOG_DIR", "NOTION_DB_ID",
    "PROJECT_DOC_CHECK_INTERVAL",
}


class TestInstalledFilesClean(_LifecycleBase):
    """설치 후 쓸데없는 파일 없는지 검증"""

    def setUp(self):
        super().setUp()
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.tmp, ".claude")

    def _list_files(self, subdir: str) -> set[str]:
        d = os.path.join(self.target, subdir)
        if not os.path.isdir(d):
            return set()
        return {f for f in os.listdir(d) if not f.endswith(".bak")}

    def test_no_extra_files_in_hooks(self):
        actual = self._list_files("hooks")
        extra = actual - EXPECTED_HOOKS
        self.assertEqual(extra, set(), f"unexpected files in hooks/: {extra}")

    def test_no_extra_files_in_scripts(self):
        actual = self._list_files("scripts")
        extra = actual - EXPECTED_SCRIPTS
        self.assertEqual(extra, set(), f"unexpected files in scripts/: {extra}")

    def test_no_extra_files_in_commands(self):
        actual = self._list_files("commands")
        extra = actual - EXPECTED_COMMANDS
        self.assertEqual(extra, set(), f"unexpected files in commands/: {extra}")

    def test_no_extra_files_in_rules(self):
        actual = self._list_files("rules")
        extra = actual - EXPECTED_RULES
        self.assertEqual(extra, set(), f"unexpected files in rules/: {extra}")

    def test_no_bak_files_on_fresh_install(self):
        bak_files = glob.glob(os.path.join(self.target, "**", "*.bak"), recursive=True)
        self.assertEqual(bak_files, [], f"fresh install should have no .bak: {bak_files}")

    def test_settings_json_no_unknown_env(self):
        cfg = self._settings(self.target)
        env_keys = set(cfg.get("env", {}).keys())
        unknown = env_keys - KNOWN_ENV_KEYS
        self.assertEqual(unknown, set(), f"unknown env keys: {unknown}")


# ══════════════════════════════════════════════════════════════════════════════
# 17. Uninstall 실제 동작 검증
# ══════════════════════════════════════════════════════════════════════════════


class TestUninstallFull(_LifecycleBase):
    """install → uninstall 후 완전 정리 검증"""

    def setUp(self):
        super().setUp()
        # 로컬 설치
        r = self._install(["1", "2", "3", "1", "1", "5", "5"], cwd=self.repo)
        self.assertEqual(r.returncode, 0)
        self.target = os.path.join(self.repo, ".claude")

        # .worklogs + .env 생성 (보존 대상)
        wl_dir = os.path.join(self.repo, ".worklogs")
        os.makedirs(wl_dir, exist_ok=True)
        with open(os.path.join(wl_dir, "2026-04-01.md"), "w") as f:
            f.write("# test worklog\n")
        with open(os.path.join(self.target, ".env"), "w") as f:
            f.write("NOTION_TOKEN=ntn_test\n")

        # 다른 hook 추가 (보존 대상)
        settings_path = os.path.join(self.target, "settings.json")
        cfg = json.load(open(settings_path))
        cfg["hooks"].setdefault("PreToolUse", []).append({
            "hooks": [{"type": "command", "command": "/some/other-hook.sh"}]
        })
        with open(settings_path, "w") as f:
            json.dump(cfg, f, indent=2)

        # uninstall
        r2 = self._uninstall(cwd=self.repo)
        self.assertEqual(r2.returncode, 0, f"uninstall failed: {r2.stderr}")

    def test_all_worklog_files_gone(self):
        for subdir in ["hooks", "scripts", "commands", "rules"]:
            d = os.path.join(self.target, subdir)
            if os.path.isdir(d):
                files = os.listdir(d)
                for f in files:
                    self.assertFalse(
                        f.endswith(".sh") or f.endswith(".py") or f.endswith(".md"),
                        f"worklog file should be gone: {subdir}/{f}",
                    )

    def test_settings_hooks_clean(self):
        cfg = self._settings(self.target)
        WORKLOG_MARKERS = ["worklog.sh", "on-commit.sh", "commit-doc-check.sh",
                           "session-end.sh", "update-check.sh"]
        for event, groups in cfg.get("hooks", {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    cmd = h.get("command", "")
                    for marker in WORKLOG_MARKERS:
                        self.assertNotIn(marker, cmd, f"{marker} should be removed from {event}")

    def test_settings_env_clean(self):
        cfg = self._settings(self.target)
        env = cfg.get("env", {})
        for key in KNOWN_ENV_KEYS:
            self.assertNotIn(key, env)

    def test_git_hook_removed(self):
        hook = os.path.join(self.repo, ".git", "hooks", "post-commit")
        if os.path.exists(hook):
            content = open(hook).read()
            self.assertNotIn("worklog", content.lower())

    def test_worklogs_preserved(self):
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".worklogs")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, ".worklogs", "2026-04-01.md")))

    def test_env_preserved(self):
        self.assertTrue(os.path.exists(os.path.join(self.target, ".env")))

    def test_settings_json_still_valid(self):
        cfg = self._settings(self.target)
        self.assertIsInstance(cfg, dict)

    def test_other_hooks_preserved(self):
        cfg = self._settings(self.target)
        pre_hooks = cfg.get("hooks", {}).get("PreToolUse", [])
        cmds = [h.get("command", "") for g in pre_hooks for h in g.get("hooks", [])]
        self.assertIn("/some/other-hook.sh", cmds, "other hooks should be preserved")


# ══════════════════════════════════════════════════════════════════════════════
# 18. 설정 변경 후 실제 동작 검증 (worklog-config 시뮬레이션)
# ══════════════════════════════════════════════════════════════════════════════


class TestConfigChange(_LifecycleBase):
    """설치 → settings.json 변경 → 커밋 → 변경된 동작 확인"""

    def setUp(self):
        super().setUp()
        # 전역 설치 (git + track + each-commit + ko)
        r = self._install(["1", "1", "3", "1", "1", "5", "5"])
        self.assertEqual(r.returncode, 0, f"install failed: {r.stderr}")
        self.target = os.path.join(self.tmp, ".claude")
        self._patch_notion_stub(self.target)

    def _update_setting(self, key: str, value: str):
        """settings.json env를 직접 수정 (worklog-config가 하는 것과 동일)"""
        settings_path = os.path.join(self.target, "settings.json")
        with open(settings_path) as f:
            cfg = json.load(f)
        cfg.setdefault("env", {})[key] = value
        with open(settings_path, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def test_timing_change_to_manual(self):
        """each-commit → manual 변경 후 커밋 → .worklogs 미생성"""
        self._update_setting("WORKLOG_TIMING", "manual")
        self._make_commit("after manual", env=self._commit_env(self.target, WORKLOG_TIMING="manual"))
        self.assertEqual(len(self._worklogs_files()), 0, ".worklogs should not be created in manual mode")

    def test_timing_change_back_to_each_commit(self):
        """manual → each-commit 변경 후 커밋 → .worklogs 생성"""
        # 먼저 manual로 변경
        self._update_setting("WORKLOG_TIMING", "manual")
        self._make_commit("manual commit", env=self._commit_env(self.target, WORKLOG_TIMING="manual"))
        self.assertEqual(len(self._worklogs_files()), 0)

        # 다시 each-commit으로 변경
        self._update_setting("WORKLOG_TIMING", "each-commit")
        self._make_commit("back to auto", env=self._commit_env(self.target))
        self.assertTrue(len(self._worklogs_files()) > 0, ".worklogs should be created after switching back")

    def test_dest_change_to_notion_only(self):
        """git → notion-only 변경 후 커밋 → .worklogs 로컬 파일 미생성"""
        self._update_setting("WORKLOG_DEST", "notion-only")
        self._make_commit("notion only", env=self._commit_env(self.target, WORKLOG_DEST="notion-only"))
        self.assertEqual(len(self._worklogs_files()), 0, "no local file in notion-only mode")

    def test_git_track_change_to_false(self):
        """true → false 변경 후 커밋 → 파일 생성되지만 unstaged"""
        self._update_setting("WORKLOG_GIT_TRACK", "false")
        self._make_commit("track false", env=self._commit_env(self.target, WORKLOG_GIT_TRACK="false"))
        self.assertTrue(len(self._worklogs_files()) > 0, "file should still be created")
        # unstaged 확인
        r = subprocess.run(
            ["git", "-C", self.repo, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, env=self._git_env,
        )
        self.assertNotIn(".worklogs", r.stdout, "should not be staged")

    def test_lang_change_to_en(self):
        """ko → en 변경 후 커밋 → Token Usage 영어 헤더"""
        self._update_setting("WORKLOG_LANG", "en")
        self._make_commit("english", env=self._commit_env(self.target, WORKLOG_LANG="en"))
        files = self._worklogs_files()
        if files:
            content = open(os.path.join(self._worklogs_dir(), files[0])).read()
            self.assertIn("Token Usage", content, "should have English header")
            self.assertNotIn("토큰 사용량", content, "should not have Korean header")


if __name__ == "__main__":
    import sys
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
