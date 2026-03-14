#!/usr/bin/env python3
"""
stop.sh hook e2e 테스트

격리된 git repo에서 실제 stop.sh 실행 검증:
- pending worklog 마커가 있으면 block + /worklog 안내
- 미커밋 변경사항이 있으면 block + /finish 안내
- 클린 상태면 통과

Run: python3 -m pytest tests/test_hooks_e2e.py -v
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _HookBase(unittest.TestCase):
    """격리된 git repo 환경에서 stop.sh 테스트 픽스처"""

    def setUp(self):
        if not shutil.which("jq"):
            self.skipTest("jq not found")

        self.tmp = tempfile.mkdtemp(prefix="ai_wl_hook_")

        git_env = {
            "HOME": self.tmp,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
        }

        # bare remote repo
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", self.remote], capture_output=True, check=True, env=git_env)

        # local repo (clone)
        self.repo = os.path.join(self.tmp, "repo")
        subprocess.run(["git", "clone", self.remote, self.repo], capture_output=True, check=True, env=git_env)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "test@test.com"], capture_output=True, env=git_env)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "Test"], capture_output=True, env=git_env)

        # initial commit
        readme = os.path.join(self.repo, "README.md")
        with open(readme, "w") as f:
            f.write("# test\n")
        subprocess.run(["git", "-C", self.repo, "add", "README.md"], capture_output=True, env=git_env)
        subprocess.run(["git", "-C", self.repo, "commit", "-m", "init"], capture_output=True, env=git_env)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, **extra):
        """테스트용 격리 환경변수"""
        safe_path = "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"
        env = {
            "HOME": self.tmp,
            "PATH": safe_path,
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update(extra)
        return env

    def _run_stop_hook(self, stdin_json=None, **env_overrides):
        """stop.sh 실행"""
        hook_script = os.path.join(PACKAGE_DIR, "hooks", "stop.sh")
        input_json = json.dumps(stdin_json) if stdin_json else "{}"
        return subprocess.run(
            ["bash", hook_script],
            input=input_json,
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self._env(**env_overrides),
            timeout=15,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Pending worklog 마커가 있으면 block
# ══════════════════════════════════════════════════════════════════════════════


class TestStopPendingMarker(_HookBase):
    """세션 내 커밋 후 /worklog 미실행 시 block"""

    def setUp(self):
        super().setUp()
        self.repo_abs = os.path.realpath(self.repo)

        # pending 마커 생성
        pending_dir = os.path.join(self.tmp, ".claude", "worklogs", ".pending")
        os.makedirs(pending_dir, exist_ok=True)
        pending_file = os.path.join(pending_dir, "12345.json")
        with open(pending_file, "w") as f:
            json.dump({
                "commit_msg": "feat: test feature",
                "changed_files": "test.py",
                "project_cwd": self.repo_abs,
            }, f)

        self.stdin = {"cwd": self.repo_abs, "stop_hook_active": False}

    def test_block_decision(self):
        """pending 마커가 있으면 decision=block"""
        r = self._run_stop_hook(self.stdin)
        self.assertEqual(r.returncode, 0)
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")

    def test_worklog_reason(self):
        """reason에 /worklog 포함"""
        r = self._run_stop_hook(self.stdin)
        result = json.loads(r.stdout)
        self.assertIn("/worklog", result["reason"])

    def test_shows_commit_msg(self):
        """reason에 커밋 메시지 포함"""
        r = self._run_stop_hook(self.stdin)
        result = json.loads(r.stdout)
        self.assertIn("feat: test feature", result["reason"])


# ══════════════════════════════════════════════════════════════════════════════
# 2. 미커밋 변경사항이 있으면 block
# ══════════════════════════════════════════════════════════════════════════════


class TestStopUncommittedChanges(_HookBase):
    """staged but uncommitted 변경사항이 있으면 block"""

    def setUp(self):
        super().setUp()
        self.repo_abs = os.path.realpath(self.repo)

        # dirty 파일 생성 + stage
        filepath = os.path.join(self.repo, "dirty.txt")
        with open(filepath, "w") as f:
            f.write("dirty content\n")
        subprocess.run(
            ["git", "-C", self.repo, "add", "dirty.txt"],
            capture_output=True,
            env=self._env(),
        )

        self.stdin = {"cwd": self.repo_abs, "stop_hook_active": False}

    def test_block_decision(self):
        """미커밋 변경이 있으면 decision=block"""
        r = self._run_stop_hook(self.stdin)
        self.assertEqual(r.returncode, 0)
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")

    def test_finish_reason(self):
        """reason에 /finish 포함"""
        r = self._run_stop_hook(self.stdin)
        result = json.loads(r.stdout)
        self.assertIn("/finish", result["reason"])

    def test_clean_repo_passes(self):
        """클린 상태에서는 block하지 않음"""
        # dirty 파일 제거 (unstage + delete)
        subprocess.run(
            ["git", "-C", self.repo, "reset", "HEAD", "dirty.txt"],
            capture_output=True,
            env=self._env(),
        )
        os.remove(os.path.join(self.repo, "dirty.txt"))

        r = self._run_stop_hook(self.stdin)
        self.assertEqual(r.returncode, 0)
        # stdout가 비어있거나 JSON이 아님
        stdout = r.stdout.strip()
        if stdout:
            try:
                result = json.loads(stdout)
                self.assertNotEqual(result.get("decision"), "block")
            except json.JSONDecodeError:
                pass  # JSON이 아니면 block이 아닌 것


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    import sys
    sys.exit(0 if result.result.wasSuccessful() else 1)
