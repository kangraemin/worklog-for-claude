#!/usr/bin/env python3
"""
healthcheck.sh e2e 테스트

격리된 임시 디렉토리에서 healthcheck.sh --json을 실행하여
정상/비정상 환경에서의 진단 결과를 검증한다.

Run: python3 tests/test_healthcheck_e2e.py
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HEALTHCHECK = os.path.join(PACKAGE_DIR, "scripts", "healthcheck.sh")
INSTALL_SCRIPT = os.path.join(PACKAGE_DIR, "install.sh")

# healthcheck가 확인하는 파일 목록
EXPECTED_FILES = [
    "scripts/worklog-write.sh",
    "scripts/notion-worklog.sh",
    "scripts/duration.py",
    "scripts/token-cost.py",
    "scripts/worklog-update-check.sh",
    "hooks/worklog.sh",
    "hooks/on-commit.sh",
    "hooks/session-end.sh",
    "hooks/post-commit.sh",
    "hooks/commit-doc-check.sh",
    "hooks/stop.sh",
    "git-hooks/post-commit",
    "commands/worklog.md",
    "commands/worklog-config.md",
    "commands/worklog-update.md",
    "commands/worklog-migrate.md",
    "rules/worklog-rules.md",
]

# 5개 hook 확인 대상
HOOK_FILES = ["worklog.sh", "on-commit.sh", "commit-doc-check.sh", "worklog-update-check.sh", "session-end.sh", "stop.sh"]


def _write_stub(path: str, content: str = "#!/bin/bash\necho stub\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


def _make_settings(env: dict, hooks: dict | None = None) -> dict:
    """settings.json 구조 생성"""
    cfg: dict = {"env": env}
    if hooks is not None:
        cfg["hooks"] = hooks
    return cfg


def _default_hooks(target_dir: str) -> dict:
    """install.sh가 등록하는 기본 hooks 구조"""
    return {
        "PostToolUse": [
            {"hooks": [{"type": "command", "command": f"{target_dir}/hooks/worklog.sh", "timeout": 5, "async": True}]},
            {"hooks": [{"type": "command", "command": f"{target_dir}/hooks/on-commit.sh", "timeout": 5}], "matcher": "Bash"},
            {"hooks": [{"type": "command", "command": f"{target_dir}/hooks/commit-doc-check.sh", "timeout": 5}]},
        ],
        "SessionStart": [
            {"hooks": [{"type": "command", "command": f"{target_dir}/scripts/worklog-update-check.sh", "timeout": 15, "async": True}]},
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": f"{target_dir}/hooks/session-end.sh", "timeout": 15}]},
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": f"{target_dir}/hooks/stop.sh", "timeout": 15}]},
        ],
    }


def _default_env(target_dir: str, dest: str = "notion-only") -> dict:
    env = {
        "WORKLOG_TIMING": "stop",
        "WORKLOG_DEST": dest,
        "WORKLOG_GIT_TRACK": "false" if dest == "notion-only" else "true",
        "WORKLOG_LANG": "ko",
        "AI_WORKLOG_DIR": target_dir,
        "PROJECT_DOC_CHECK_INTERVAL": "5",
    }
    if dest != "git":
        env["NOTION_DB_ID"] = "fake-db-id-123"
    return env


class _Base(unittest.TestCase):
    """공통 픽스처"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wl_hc_test_")
        self.target = os.path.join(self.tmp, ".claude")
        os.makedirs(self.target, exist_ok=True)
        # fake bin for install.sh prerequisites
        self._bin = os.path.join(self.tmp, "bin")
        os.makedirs(self._bin)
        _write_stub(os.path.join(self._bin, "claude"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_full(self, dest: str = "notion-only"):
        """정상 설치 환경 구성"""
        # 파일 생성
        for f in EXPECTED_FILES:
            path = os.path.join(self.target, f)
            _write_stub(path)

        # settings.json
        env = _default_env(self.target, dest)
        hooks = _default_hooks(self.target)
        cfg = _make_settings(env, hooks)
        with open(os.path.join(self.target, "settings.json"), "w") as f:
            json.dump(cfg, f, indent=2)

        # .env (Notion 모드용)
        if dest != "git":
            env_file = os.path.join(self.target, ".env")
            with open(env_file, "w") as f:
                f.write("NOTION_TOKEN=secret_fake_token\n")
            os.chmod(env_file, 0o600)

        # .version
        with open(os.path.join(self.target, ".version"), "w") as f:
            f.write("abc1234\n")

        # git-hooks/post-commit 내용 (post-commit.sh 위임)
        pc = os.path.join(self.target, "git-hooks", "post-commit")
        _write_stub(pc, '#!/bin/bash\nexec bash "$AI_WORKLOG_DIR/hooks/post-commit.sh"\n')

    def _run_healthcheck(self, extra_env: dict | None = None) -> dict:
        """healthcheck.sh --json 실행하고 결과 파싱"""
        env = {
            **os.environ,
            "HOME": self.tmp,
            "AI_WORKLOG_DIR": self.target,
            "HEALTHCHECK_SETTINGS": os.path.join(self.target, "settings.json"),
            "HEALTHCHECK_SKIP_VERSION_CHECK": "1",
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(self.target, "git-hooks"),
        }
        if extra_env:
            env.update(extra_env)

        r = subprocess.run(
            ["bash", HEALTHCHECK, "--json"],
            capture_output=True, text=True,
            env=env, cwd=self.tmp, timeout=10,
        )
        try:
            return json.loads(r.stdout.strip())
        except json.JSONDecodeError:
            self.fail(f"healthcheck JSON 파싱 실패.\nstdout: {r.stdout}\nstderr: {r.stderr}\nexit: {r.returncode}")

    def _run_healthcheck_raw(self, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "HOME": self.tmp,
            "AI_WORKLOG_DIR": self.target,
            "HEALTHCHECK_SETTINGS": os.path.join(self.target, "settings.json"),
            "HEALTHCHECK_SKIP_VERSION_CHECK": "1",
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(self.target, "git-hooks"),
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", HEALTHCHECK, "--json"],
            capture_output=True, text=True,
            env=env, cwd=self.tmp, timeout=10,
        )

    def _settings_path(self):
        return os.path.join(self.target, "settings.json")

    def _read_settings(self) -> dict:
        with open(self._settings_path()) as f:
            return json.load(f)

    def _write_settings(self, cfg: dict):
        with open(self._settings_path(), "w") as f:
            json.dump(cfg, f, indent=2)

    def _remove_hook(self, hook_file: str):
        """settings.json에서 특정 hook 제거"""
        cfg = self._read_settings()
        for event in list(cfg.get("hooks", {}).keys()):
            groups = cfg["hooks"][event]
            cfg["hooks"][event] = [
                g for g in groups
                if not any(hook_file in h.get("command", "") for h in g.get("hooks", []))
            ]
            if not cfg["hooks"][event]:
                del cfg["hooks"][event]
        self._write_settings(cfg)

    def _env(self) -> dict:
        return {
            **os.environ,
            "HOME": self.tmp,
            "PATH": f'{self._bin}:{os.environ.get("PATH", "")}',
        }

    def _run_install(self, inputs: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", INSTALL_SCRIPT],
            input="\n".join(inputs) + "\n",
            capture_output=True, text=True,
            env=self._env(), cwd=self.tmp, timeout=30,
        )


# ══════════════════════════════════════════════════════════════════════════════
# A. 정상 환경
# ══════════════════════════════════════════════════════════════════════════════


class TestHealthyNotionOnly(_Base):
    """TC-01: 정상 설치 (notion-only)"""

    def test_all_pass(self):
        self._setup_full("notion-only")
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["files_found"], 17)
        self.assertEqual(r["hooks_found"], 6)
        self.assertEqual(r["git_hook"], "ok")
        self.assertEqual(r["env"], "ok")
        self.assertEqual(r["issue_count"], 0)


class TestHealthyGit(_Base):
    """TC-02: 정상 설치 (git 모드)"""

    def test_git_mode_pass(self):
        self._setup_full("git")
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["env"], "ok")


class TestHealthyBoth(_Base):
    """TC-03: 정상 설치 (both 모드)"""

    def test_both_mode_pass(self):
        self._setup_full("notion")
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "pass")


# ══════════════════════════════════════════════════════════════════════════════
# B. 파일 무결성 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestMissingSingleScript(_Base):
    """TC-04: scripts/duration.py 삭제"""

    def test_missing_duration(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "scripts/duration.py"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 16)
        self.assertIn("scripts/duration.py", r["files_missing"])


class TestMissingSingleHook(_Base):
    """TC-05: hooks/worklog.sh 삭제"""

    def test_missing_worklog_hook(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "hooks/worklog.sh"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 16)
        self.assertIn("hooks/worklog.sh", r["files_missing"])


class TestMissingAllScripts(_Base):
    """TC-06: scripts/ 전체 삭제"""

    def test_missing_all_scripts(self):
        self._setup_full()
        shutil.rmtree(os.path.join(self.target, "scripts"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 12)
        self.assertEqual(len(r["files_missing"]), 5)


class TestMissingAllHooks(_Base):
    """TC-07: hooks/ 전체 삭제"""

    def test_missing_all_hooks(self):
        self._setup_full()
        shutil.rmtree(os.path.join(self.target, "hooks"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 11)
        self.assertEqual(len(r["files_missing"]), 6)


class TestMissingAllCommands(_Base):
    """TC-08: commands/ 전체 삭제"""

    def test_missing_all_commands(self):
        self._setup_full()
        shutil.rmtree(os.path.join(self.target, "commands"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 13)


class TestMissingAllRules(_Base):
    """TC-09: rules/ 전체 삭제"""

    def test_missing_all_rules(self):
        self._setup_full()
        shutil.rmtree(os.path.join(self.target, "rules"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 16)


class TestMissingGitHookFile(_Base):
    """TC-10: git-hooks/post-commit 삭제"""

    def test_missing_git_hook_file(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "git-hooks/post-commit"))
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 16)
        self.assertIn("git-hooks/post-commit", r["files_missing"])
        # 연쇄: git hook도 실패
        self.assertNotEqual(r["git_hook"], "ok")


class TestMissingAllFiles(_Base):
    """TC-11: 전체 파일 삭제"""

    def test_missing_all_files(self):
        self._setup_full()
        for f in EXPECTED_FILES:
            p = os.path.join(self.target, f)
            if os.path.exists(p):
                os.remove(p)
        r = self._run_healthcheck()
        self.assertEqual(r["files_found"], 0)
        self.assertEqual(len(r["files_missing"]), 17)


# ══════════════════════════════════════════════════════════════════════════════
# C. Hook 등록 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestMissingWorklogHook(_Base):
    """TC-12: worklog.sh hook만 제거"""

    def test_hook_missing(self):
        self._setup_full()
        self._remove_hook("worklog.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 5)
        self.assertIn("worklog.sh", r["hooks_missing"])


class TestMissingOnCommitHook(_Base):
    """TC-13: on-commit.sh hook만 제거"""

    def test_hook_missing(self):
        self._setup_full()
        self._remove_hook("on-commit.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 5)
        self.assertIn("on-commit.sh", r["hooks_missing"])


class TestMissingSessionEndHook(_Base):
    """TC-14: session-end.sh hook만 제거"""

    def test_hook_missing(self):
        self._setup_full()
        self._remove_hook("session-end.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 5)
        self.assertIn("session-end.sh", r["hooks_missing"])


class TestMissingUpdateCheckHook(_Base):
    """TC-15: worklog-update-check.sh hook만 제거"""

    def test_hook_missing(self):
        self._setup_full()
        self._remove_hook("worklog-update-check.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 5)
        self.assertIn("worklog-update-check.sh", r["hooks_missing"])


class TestMissingCommitDocCheckHook(_Base):
    """TC-16: commit-doc-check.sh hook만 제거"""

    def test_hook_missing(self):
        self._setup_full()
        self._remove_hook("commit-doc-check.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 5)
        self.assertIn("commit-doc-check.sh", r["hooks_missing"])


class TestMissingPostToolUseAll(_Base):
    """TC-17: PostToolUse 전체 제거"""

    def test_3_hooks_missing(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["hooks"]["PostToolUse"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 3)


class TestMissingHooksSectionAll(_Base):
    """TC-18: hooks 섹션 전체 없음"""

    def test_all_hooks_missing(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["hooks"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["hooks_found"], 0)


class TestHookRegisteredButFileMissing(_Base):
    """TC-19: hook 등록됨 + 파일 없음"""

    def test_hook_file_missing(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "hooks/worklog.sh"))
        r = self._run_healthcheck()
        # hook은 settings.json에 등록돼있으므로 hooks_found는 5
        self.assertEqual(r["hooks_found"], 6)
        # 하지만 파일 누락 경고
        self.assertIn("worklog.sh", r.get("hooks_file_missing", []))


# ══════════════════════════════════════════════════════════════════════════════
# D. Git Hook 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestGitHookPathNotSet(_Base):
    """TC-20: core.hooksPath 미설정 + git-hooks/ 없음"""

    def test_git_hook_missing(self):
        self._setup_full()
        shutil.rmtree(os.path.join(self.target, "git-hooks"))
        r = self._run_healthcheck({"HEALTHCHECK_GIT_HOOKS_PATH": ""})
        self.assertEqual(r["git_hook"], "missing")


class TestGitHookPathSetNoFile(_Base):
    """TC-21: core.hooksPath 설정 + post-commit 없음"""

    def test_git_hook_warn(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "git-hooks/post-commit"))
        r = self._run_healthcheck()
        self.assertEqual(r["git_hook"], "warn")
        self.assertIn("파일 없음", r.get("git_hook_detail", ""))


class TestGitHookContentMismatch(_Base):
    """TC-22: post-commit 내용 불일치"""

    def test_git_hook_content_mismatch(self):
        self._setup_full()
        pc = os.path.join(self.target, "git-hooks/post-commit")
        with open(pc, "w") as f:
            f.write("#!/bin/bash\necho 'unrelated hook'\n")
        r = self._run_healthcheck()
        self.assertEqual(r["git_hook"], "warn")
        self.assertIn("불일치", r.get("git_hook_detail", ""))


class TestGitHookNoExecPermission(_Base):
    """TC-23: post-commit 실행 권한 없음"""

    def test_git_hook_no_exec(self):
        self._setup_full()
        pc = os.path.join(self.target, "git-hooks/post-commit")
        os.chmod(pc, 0o644)
        r = self._run_healthcheck()
        self.assertEqual(r["git_hook"], "warn")
        self.assertIn("권한", r.get("git_hook_detail", ""))


# ══════════════════════════════════════════════════════════════════════════════
# F. 환경변수 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestMissingWorklogTiming(_Base):
    """TC-27: WORKLOG_TIMING 없음"""

    def test_env_warn(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["env"]["WORKLOG_TIMING"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertTrue(any("WORKLOG_TIMING" in i for i in r.get("env_issues", [])))


class TestMissingWorklogDest(_Base):
    """TC-28: WORKLOG_DEST 없음"""

    def test_env_warn(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["env"]["WORKLOG_DEST"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertTrue(any("WORKLOG_DEST" in i for i in r.get("env_issues", [])))


class TestMissingWorklogLang(_Base):
    """TC-29: WORKLOG_LANG 없음"""

    def test_env_warn_only(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["env"]["WORKLOG_LANG"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertTrue(any("WORKLOG_LANG" in i for i in r.get("env_issues", [])))


class TestMissingAiWorklogDir(_Base):
    """TC-30: AI_WORKLOG_DIR 없음"""

    def test_env_warn_only(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["env"]["AI_WORKLOG_DIR"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertTrue(any("AI_WORKLOG_DIR" in i for i in r.get("env_issues", [])))


class TestMissingNotionDbIdNotionMode(_Base):
    """TC-31: NOTION_DB_ID 없음 (dest=notion-only)"""

    def test_env_warn_required(self):
        self._setup_full("notion-only")
        cfg = self._read_settings()
        del cfg["env"]["NOTION_DB_ID"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertTrue(any("NOTION_DB_ID" in i for i in r.get("env_issues", [])))


class TestMissingNotionDbIdGitMode(_Base):
    """TC-32: NOTION_DB_ID 없음 (dest=git) → ✅"""

    def test_env_ok(self):
        self._setup_full("git")
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "ok")


class TestMissingNotionTokenNotionMode(_Base):
    """TC-33: .env에 NOTION_TOKEN 없음 (dest=notion)"""

    def test_env_warn(self):
        self._setup_full("notion")
        env_file = os.path.join(self.target, ".env")
        with open(env_file, "w") as f:
            f.write("# no token\n")
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertTrue(any("NOTION_TOKEN" in i for i in r.get("env_issues", [])))


class TestMissingNotionTokenGitMode(_Base):
    """TC-34: NOTION_TOKEN 없음 (dest=git) → ✅"""

    def test_env_ok(self):
        self._setup_full("git")
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "ok")


class TestMissingEnvFile(_Base):
    """TC-35: .env 파일 없음 (dest=notion-only)"""

    def test_env_warn(self):
        self._setup_full("notion-only")
        os.remove(os.path.join(self.target, ".env"))
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertTrue(any("NOTION_TOKEN" in i for i in r.get("env_issues", [])))


class TestMissingEnvSectionAll(_Base):
    """TC-36: env 섹션 전체 없음"""

    def test_env_warn_all(self):
        self._setup_full()
        cfg = self._read_settings()
        del cfg["env"]
        self._write_settings(cfg)
        r = self._run_healthcheck()
        self.assertEqual(r["env"], "warn")
        self.assertGreater(len(r.get("env_issues", [])), 0)


# ══════════════════════════════════════════════════════════════════════════════
# G. 버전 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestMissingVersionFile(_Base):
    """TC-37: .version 파일 없음"""

    def test_version_unknown(self):
        self._setup_full()
        os.remove(os.path.join(self.target, ".version"))
        r = self._run_healthcheck()
        self.assertEqual(r["version"], "unknown")


class TestEmptyVersionFile(_Base):
    """TC-38: .version 빈 파일"""

    def test_version_unknown(self):
        self._setup_full()
        with open(os.path.join(self.target, ".version"), "w") as f:
            f.write("")
        r = self._run_healthcheck()
        self.assertEqual(r["version"], "unknown")


# ══════════════════════════════════════════════════════════════════════════════
# H. settings.json 자체 비정상
# ══════════════════════════════════════════════════════════════════════════════


class TestSettingsJsonMissing(_Base):
    """TC-39: settings.json 없음"""

    def test_not_installed(self):
        # setUp만 실행, _setup_full 안 함
        r = self._run_healthcheck_raw()
        self.assertEqual(r.returncode, 1)
        result = json.loads(r.stdout.strip())
        self.assertEqual(result["status"], "not_installed")


class TestSettingsJsonInvalid(_Base):
    """TC-40: settings.json 잘못된 JSON"""

    def test_parse_error(self):
        self._setup_full()
        with open(self._settings_path(), "w") as f:
            f.write("{invalid json content")
        r = self._run_healthcheck_raw()
        self.assertEqual(r.returncode, 1)
        result = json.loads(r.stdout.strip())
        self.assertEqual(result["status"], "error")


# ══════════════════════════════════════════════════════════════════════════════
# I. 로컬 + 글로벌 혼합
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalOnly(_Base):
    """TC-41: 글로벌에만 설치"""

    def test_global_pass(self):
        self._setup_full()
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "pass")


class TestGlobalAndLocal(_Base):
    """TC-42: 글로벌 + 로컬"""

    def test_merged(self):
        self._setup_full()
        local_dir = os.path.join(self.tmp, "project", ".claude")
        os.makedirs(local_dir, exist_ok=True)
        local_cfg = {"env": {"WORKLOG_DEST": "git", "WORKLOG_GIT_TRACK": "true"}}
        local_settings = os.path.join(local_dir, "settings.json")
        with open(local_settings, "w") as f:
            json.dump(local_cfg, f)
        r = self._run_healthcheck({"HEALTHCHECK_LOCAL_SETTINGS": local_settings})
        # 로컬이 dest=git으로 오버라이드 → Notion 체크 스킵 → ok
        self.assertEqual(r["env"], "ok")


class TestLocalOverride(_Base):
    """TC-43: 로컬 env 오버라이드"""

    def test_local_priority(self):
        self._setup_full()
        local_dir = os.path.join(self.tmp, "project", ".claude")
        os.makedirs(local_dir, exist_ok=True)
        local_cfg = {"env": {"NOTION_DB_ID": "local-override-db"}}
        local_settings = os.path.join(local_dir, "settings.json")
        with open(local_settings, "w") as f:
            json.dump(local_cfg, f)
        r = self._run_healthcheck({"HEALTHCHECK_LOCAL_SETTINGS": local_settings})
        self.assertEqual(r["status"], "pass")


# ══════════════════════════════════════════════════════════════════════════════
# J. 종합 판정 + 제안
# ══════════════════════════════════════════════════════════════════════════════


class TestOverallWarn(_Base):
    """TC-44: 1개 항목만 ⚠️"""

    def test_overall_warn(self):
        self._setup_full()
        os.remove(os.path.join(self.target, "scripts/duration.py"))
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "warn")
        self.assertGreater(r["issue_count"], 0)


class TestOverallFail(_Base):
    """TC-45: 3개 이상 ❌"""

    def test_overall_fail(self):
        self._setup_full()
        # 파일 3개 삭제
        for f in ["scripts/duration.py", "scripts/token-cost.py", "hooks/worklog.sh"]:
            os.remove(os.path.join(self.target, f))
        # hook 1개 제거
        self._remove_hook("session-end.sh")
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "fail")
        self.assertGreaterEqual(r["issue_count"], 3)


class TestOverallPass(_Base):
    """TC-46: 전부 ✅"""

    def test_overall_pass(self):
        self._setup_full()
        r = self._run_healthcheck()
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["issue_count"], 0)


# ══════════════════════════════════════════════════════════════════════════════
# K. 비정상 → install.sh 재실행 → 정상 복구
# ══════════════════════════════════════════════════════════════════════════════


class _RecoveryBase(_Base):
    """복구 테스트 공통: install.sh로 정상 설치 후 파괴 → 재설치 → healthcheck"""

    # install.sh 입력: lang=ko, scope=global, dest=git, track=yes, timing=auto, interval=default
    _GIT_INPUTS = ["1", "1", "3", "1", "1", "", "5"]

    def _install(self, inputs: list[str] | None = None):
        r = self._run_install(inputs or self._GIT_INPUTS)
        self.assertEqual(r.returncode, 0, f"install failed: {r.stderr}")

    def _healthcheck_after_install(self) -> dict:
        target = os.path.join(self.tmp, ".claude")
        return self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": os.path.join(target, "settings.json"),
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })


class TestRecoveryFiles(_RecoveryBase):
    """TC-47: 파일 3개 삭제 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        for f in ["scripts/duration.py", "scripts/token-cost.py", "hooks/worklog.sh"]:
            p = os.path.join(target, f)
            if os.path.exists(p):
                os.remove(p)
        # 비정상 확인
        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": os.path.join(target, "settings.json"),
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertLess(r["files_found"], 17)
        # 재설치
        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["files_found"], r2["files_total"])


class TestRecoveryHooks(_RecoveryBase):
    """TC-48: hooks 전체 제거 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        sf = os.path.join(target, "settings.json")
        with open(sf) as f:
            cfg = json.load(f)
        cfg["hooks"] = {}
        with open(sf, "w") as f:
            json.dump(cfg, f, indent=2)
        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": sf,
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertEqual(r["hooks_found"], 0)
        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["hooks_found"], r2["hooks_total"])


class TestRecoveryGitHook(_RecoveryBase):
    """TC-49: git-hooks/post-commit 삭제 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        gh = os.path.join(target, "git-hooks", "post-commit")
        if os.path.exists(gh):
            os.remove(gh)
        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": os.path.join(target, "settings.json"),
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertNotEqual(r["git_hook"], "ok")
        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["git_hook"], "ok")


class TestRecoveryEnvFile(_RecoveryBase):
    """TC-50: .env 삭제 (notion 모드) → 재설치 → 복구"""

    # lang=ko, scope=global, dest=both, track=yes, timing=auto, interval
    # Notion 사전 주입으로 .env 재생성 확인
    def test_recovery(self):
        # .env 사전 주입 후 설치
        d = os.path.join(self.tmp, ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".env"), "w") as f:
            f.write("NOTION_TOKEN=secret_test_token\n")
        os.chmod(os.path.join(d, ".env"), 0o600)
        with open(os.path.join(d, "settings.json"), "w") as f:
            json.dump({"env": {"NOTION_DB_ID": "fake-db"}}, f)
        self._install(["1", "1", "1", "1", "1", "", "5"])
        target = os.path.join(self.tmp, ".claude")
        # .env 삭제
        env_file = os.path.join(target, ".env")
        if os.path.exists(env_file):
            os.remove(env_file)
        # 재설치: .env가 다시 사전 주입되어야 하므로 다시 만들어줌
        with open(env_file, "w") as f:
            f.write("NOTION_TOKEN=secret_test_token\n")
        os.chmod(env_file, 0o600)
        self._install(["1", "1", "1", "1", "1", "", "5"])
        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": os.path.join(target, "settings.json"),
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertTrue(os.path.exists(env_file))


class TestRecoveryEnvVars(_RecoveryBase):
    """TC-52: env 3개 삭제 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        sf = os.path.join(target, "settings.json")
        with open(sf) as f:
            cfg = json.load(f)
        for k in ["WORKLOG_TIMING", "WORKLOG_DEST", "WORKLOG_LANG"]:
            cfg["env"].pop(k, None)
        with open(sf, "w") as f:
            json.dump(cfg, f, indent=2)
        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": sf,
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertEqual(r["env"], "warn")
        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["env"], "ok")


class TestRecoveryComplex(_RecoveryBase):
    """TC-53: 복합 삭제 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        sf = os.path.join(target, "settings.json")
        # 파일 2개 삭제
        for f in ["scripts/duration.py", "hooks/on-commit.sh"]:
            p = os.path.join(target, f)
            if os.path.exists(p):
                os.remove(p)
        # hook 1개 제거
        with open(sf) as fh:
            cfg = json.load(fh)
        if "SessionEnd" in cfg.get("hooks", {}):
            del cfg["hooks"]["SessionEnd"]
        # env 1개 삭제
        cfg["env"].pop("WORKLOG_LANG", None)
        with open(sf, "w") as fh:
            json.dump(cfg, fh, indent=2)

        r = self._run_healthcheck({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": sf,
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertNotEqual(r["status"], "pass")

        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["files_found"], r2["files_total"])
        self.assertEqual(r2["hooks_found"], r2["hooks_total"])


class TestRecoverySettingsDeleted(_RecoveryBase):
    """TC-54: settings.json 삭제 → 재설치 → 복구"""

    def test_recovery(self):
        self._install()
        target = os.path.join(self.tmp, ".claude")
        sf = os.path.join(target, "settings.json")
        os.remove(sf)
        r = self._run_healthcheck_raw({
            "AI_WORKLOG_DIR": target,
            "HEALTHCHECK_SETTINGS": sf,
            "HEALTHCHECK_GIT_HOOKS_PATH": os.path.join(target, "git-hooks"),
        })
        self.assertEqual(r.returncode, 1)
        self._install()
        r2 = self._healthcheck_after_install()
        self.assertEqual(r2["files_found"], r2["files_total"])


if __name__ == "__main__":
    unittest.main()
