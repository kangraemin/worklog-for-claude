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
        """reason에 미처리 커밋 메시지 포함"""
        r = self._run_stop_hook(self.stdin)
        result = json.loads(r.stdout)
        self.assertIn("feat: test feature", result["reason"])


# ══════════════════════════════════════════════════════════════════════════════
# 2. 미커밋 변경사항이 있으면 block
# ══════════════════════════════════════════════════════════════════════════════


class TestStopUncommittedChanges(_HookBase):
    """미커밋 변경사항이 있으면 block + /finish"""

    def setUp(self):
        super().setUp()
        dirty = os.path.join(self.repo, "dirty.txt")
        with open(dirty, "w") as f:
            f.write("dirty\n")
        subprocess.run(["git", "-C", self.repo, "add", "dirty.txt"], capture_output=True)
        self.stdin = {"cwd": self.repo, "stop_hook_active": False}

    def test_block_decision(self):
        """미커밋 변경사항이 있으면 decision=block"""
        r = self._run_stop_hook(self.stdin)
        self.assertEqual(r.returncode, 0)
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")

    def test_finish_reason(self):
        """dirty일 때 reason에 /finish 포함"""
        r = self._run_stop_hook(self.stdin)
        result = json.loads(r.stdout)
        self.assertIn("/finish", result["reason"])

    def test_clean_repo_no_block(self):
        """클린 + pending 없으면 block 안 함 (exit 0, stdout 비어있음)"""
        # dirty 파일 제거
        subprocess.run(["git", "-C", self.repo, "reset", "HEAD", "dirty.txt"], capture_output=True, env=self._env())
        os.remove(os.path.join(self.repo, "dirty.txt"))
        r = self._run_stop_hook(self.stdin)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


# ══════════════════════════════════════════════════════════════════════════════
# 3. session-end.sh: collecting 파일 정리
# ══════════════════════════════════════════════════════════════════════════════


class TestSessionEndCleanup(_HookBase):
    """session-end.sh가 collecting 파일을 삭제하는지 검증"""

    def setUp(self):
        super().setUp()
        self.session_id = "test-session-abc123"
        collecting_dir = os.path.join(self.tmp, ".claude", "worklogs", ".collecting")
        os.makedirs(collecting_dir, exist_ok=True)
        self.collecting_file = os.path.join(collecting_dir, f"{self.session_id}.jsonl")
        with open(self.collecting_file, "w") as f:
            f.write('{"ts":"2026-03-14T10:00:00Z","tool":"Bash","input":{}}\n')

    def _run_session_end(self, session_id):
        hook_script = os.path.join(PACKAGE_DIR, "hooks", "session-end.sh")
        stdin_json = json.dumps({"session_id": session_id})
        return subprocess.run(
            ["bash", hook_script],
            input=stdin_json,
            capture_output=True, text=True,
            env=self._env(),
            timeout=10,
        )

    def test_collecting_file_removed(self):
        """실행 후 collecting 파일이 삭제됨"""
        self._run_session_end(self.session_id)
        self.assertFalse(os.path.exists(self.collecting_file))

    def test_exit_zero(self):
        """정상 종료 (exit 0)"""
        r = self._run_session_end(self.session_id)
        self.assertEqual(r.returncode, 0)

    def test_nonexistent_session_ok(self):
        """존재하지 않는 session_id로 실행해도 exit 0"""
        r = self._run_session_end("nonexistent-xyz")
        self.assertEqual(r.returncode, 0)


# ══════════════════════════════════════════════════════════════════════════════
# 4. post-commit.sh: AI_WORKLOG_DIR 없을 때 graceful 종료
# ══════════════════════════════════════════════════════════════════════════════


class TestPostCommitMissingAiDir(_HookBase):
    """post-commit.sh가 AI_WORKLOG_DIR 없을 때 graceful하게 종료하는지 검증"""

    def setUp(self):
        super().setUp()
        self.repo_abs = os.path.realpath(self.repo)

    def _run_post_commit(self, **env_overrides):
        hook_script = os.path.join(PACKAGE_DIR, "hooks", "post-commit.sh")
        env = self._env(**env_overrides)
        # AI_WORKLOG_DIR과 CLAUDECODE가 없어야 함
        env.pop("AI_WORKLOG_DIR", None)
        env.pop("CLAUDECODE", None)
        return subprocess.run(
            ["bash", hook_script],
            capture_output=True, text=True,
            cwd=self.repo,
            env=env,
            timeout=15,
        )

    def test_graceful_exit(self):
        """AI_WORKLOG_DIR 없어도 exit 0"""
        r = self._run_post_commit()
        self.assertEqual(r.returncode, 0)

    def test_no_traceback(self):
        """stderr에 Traceback 없음"""
        r = self._run_post_commit()
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    import sys
    sys.exit(0 if result.result.wasSuccessful() else 1)
