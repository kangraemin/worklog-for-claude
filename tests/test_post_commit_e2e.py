#!/usr/bin/env python3
"""
post-commit hook + worklog-write.sh e2e 테스트

격리된 git repo에서 실제 post-commit hook / worklog-write.sh 실행 검증:
- CLAUDECODE 설정 시 post-commit 스킵
- .worklogs/ 만 변경된 커밋 시 스킵 (무한루프 방지)
- 터미널 커밋 시 worklog 작성 (claude -p fallback)
- worklog-write.sh 로컬 파일 작성
- Stop hook prompt type 설정 검증

Run: python3 -m pytest tests/test_post_commit_e2e.py -v
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _GitRepoBase(unittest.TestCase):
    """격리된 git repo + remote 환경 픽스처"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai_wl_pce2e_")

        # 글로벌 git hooks 격리용 env (실제 core.hooksPath 차단)
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
        subprocess.run(["git", "-C", self.repo, "push"], capture_output=True, env=git_env)

        # worklog-for-claude 설치 디렉토리 (fake)
        self.ai_dir = os.path.join(self.tmp, "worklog-for-claude")
        os.makedirs(os.path.join(self.ai_dir, "scripts"))
        os.makedirs(os.path.join(self.ai_dir, "hooks"))

        # worklog-write.sh 복사
        shutil.copy(
            os.path.join(PACKAGE_DIR, "scripts", "worklog-write.sh"),
            os.path.join(self.ai_dir, "scripts", "worklog-write.sh"),
        )
        os.chmod(os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), 0o755)

        # post-commit.sh 복사
        shutil.copy(
            os.path.join(PACKAGE_DIR, "hooks", "post-commit.sh"),
            os.path.join(self.ai_dir, "hooks", "post-commit.sh"),
        )
        os.chmod(os.path.join(self.ai_dir, "hooks", "post-commit.sh"), 0o755)

        # token-cost.py, duration.py 스텁 (에러 방지)
        for script in ["token-cost.py", "duration.py"]:
            with open(os.path.join(self.ai_dir, "scripts", script), "w") as f:
                f.write("print('0,0.000')\n")

        # settings.json
        settings = {
            "env": {
                "WORKLOG_TIMING": "stop",
                "WORKLOG_DEST": "git",
                "WORKLOG_GIT_TRACK": "true",
                "WORKLOG_LANG": "ko",
                "AI_WORKLOG_DIR": self.ai_dir,
            }
        }
        with open(os.path.join(self.ai_dir, "settings.json"), "w") as f:
            json.dump(settings, f)

        # 스냅샷 디렉토리 ($HOME/.claude/worklogs/)
        snapshot_dir = os.path.join(self.tmp, ".claude", "worklogs")
        os.makedirs(snapshot_dir, exist_ok=True)

        # claude 스텁 (claude -p 호출 시 빈 결과 반환 → fallback)
        self._bin = os.path.join(self.tmp, "bin")
        os.makedirs(self._bin, exist_ok=True)
        with open(os.path.join(self._bin, "claude"), "w") as f:
            f.write("#!/bin/bash\nexit 1\n")  # 항상 실패 → fallback
        os.chmod(os.path.join(self._bin, "claude"), 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, **extra):
        """테스트용 환경변수 (claude 스텁 사용, 격리)"""
        # 스텁 bin (실제 claude 차단) + python3/git/jq 경로
        python3_dir = os.path.dirname(shutil.which("python3") or "/usr/bin/python3")
        safe_path = f'{self._bin}:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:{python3_dir}'
        env = {
            "HOME": self.tmp,
            "AI_WORKLOG_DIR": self.ai_dir,
            "WORKLOG_TIMING": "stop",
            "WORKLOG_DEST": "git",
            "WORKLOG_GIT_TRACK": "true",
            "WORKLOG_LANG": "ko",
            "PATH": safe_path,
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update(extra)
        return env

    def _make_change_and_commit(self, filename="test.txt", content="hello\n", msg="test commit", env=None):
        """파일 변경 + 커밋 (post-commit hook 수동 실행)"""
        filepath = os.path.join(self.repo, filename)
        with open(filepath, "w") as f:
            f.write(content)
        subprocess.run(["git", "-C", self.repo, "add", filename], capture_output=True, env=env or self._env())
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-m", msg],
            capture_output=True,
            env=env or self._env(),
            timeout=10,
        )

    def _run_post_commit(self, env=None):
        """post-commit.sh 직접 실행"""
        return subprocess.run(
            ["bash", os.path.join(self.ai_dir, "hooks", "post-commit.sh")],
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=env or self._env(),
            timeout=30,
        )


# ══════════════════════════════════════════════════════════════════════════════
# 1. CLAUDECODE 설정 시 post-commit 스킵
# ══════════════════════════════════════════════════════════════════════════════


class TestPostCommitSkipInSession(_GitRepoBase):
    """Claude Code 세션 내에서는 post-commit hook 스킵"""

    def test_skip_when_claudecode_set(self):
        """CLAUDECODE 환경변수가 있으면 즉시 exit 0"""
        self._make_change_and_commit()
        r = self._run_post_commit(env=self._env(CLAUDECODE="1"))
        self.assertEqual(r.returncode, 0)
        # .worklogs/ 가 생성되지 않아야 함
        worklogs_dir = os.path.join(self.repo, ".worklogs")
        self.assertFalse(os.path.exists(worklogs_dir), ".worklogs/ should not exist when CLAUDECODE is set")

    def test_runs_when_claudecode_not_set(self):
        """CLAUDECODE 없으면 정상 실행 (워크로그 작성)"""
        self._make_change_and_commit()
        env = self._env()
        env.pop("CLAUDECODE", None)
        r = self._run_post_commit(env=env)
        self.assertEqual(r.returncode, 0)
        worklogs_dir = os.path.join(self.repo, ".worklogs")
        self.assertTrue(os.path.exists(worklogs_dir), ".worklogs/ should be created")


# ══════════════════════════════════════════════════════════════════════════════
# 2. .worklogs/ 만 변경된 커밋 시 스킵 (무한루프 방지)
# ══════════════════════════════════════════════════════════════════════════════


class TestPostCommitSkipWorklogOnly(_GitRepoBase):
    """워크로그 파일만 변경된 커밋에서는 스킵"""

    def test_skip_worklogs_only_commit(self):
        """커밋에 .worklogs/ 파일만 있으면 스킵"""
        # 워크로그 파일만 있는 커밋 생성
        wl_dir = os.path.join(self.repo, ".worklogs")
        os.makedirs(wl_dir, exist_ok=True)
        wl_file = os.path.join(wl_dir, "2026-03-02.md")
        with open(wl_file, "w") as f:
            f.write("# test worklog\n")
        subprocess.run(["git", "-C", self.repo, "add", ".worklogs/"], capture_output=True, env=self._env())
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-m", "docs: update worklog"],
            capture_output=True, env=self._env(), timeout=10,
        )

        env = self._env()
        env.pop("CLAUDECODE", None)
        r = self._run_post_commit(env=env)
        self.assertEqual(r.returncode, 0)
        # 기존 워크로그 파일 외에 새 엔트리가 추가되지 않아야 함
        with open(wl_file) as f:
            content = f.read()
        self.assertEqual(content, "# test worklog\n", "worklog should not be modified for worklogs-only commit")

    def test_runs_for_mixed_commit(self):
        """코드 + .worklogs/ 섞인 커밋은 정상 실행"""
        wl_dir = os.path.join(self.repo, ".worklogs")
        os.makedirs(wl_dir, exist_ok=True)
        with open(os.path.join(wl_dir, "2026-03-02.md"), "w") as f:
            f.write("# test\n")
        with open(os.path.join(self.repo, "code.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "-C", self.repo, "add", ".worklogs/", "code.py"], capture_output=True, env=self._env())
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-m", "feat: add code + worklog"],
            capture_output=True, env=self._env(), timeout=10,
        )

        env = self._env()
        env.pop("CLAUDECODE", None)
        r = self._run_post_commit(env=env)
        self.assertEqual(r.returncode, 0)


# ══════════════════════════════════════════════════════════════════════════════
# 3. worklog-write.sh 로컬 파일 작성
# ══════════════════════════════════════════════════════════════════════════════


class TestWorklogWriteIntegration(_GitRepoBase):
    """worklog-write.sh 가 .worklogs/ 파일을 올바르게 생성"""

    def test_creates_worklog_file(self):
        """워크로그 파일이 생성되고 요약 내용이 포함됨"""
        self._make_change_and_commit(msg="feat: add feature")

        # worklog-write.sh 직접 호출
        summary = "### 작업 내용\n- 기능 추가\n\n### 변경 파일\n- `test.txt`: 테스트 파일 추가"
        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary)

        env = self._env()
        r = subprocess.run(
            ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile],
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=env,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

        # 워크로그 파일 확인
        import glob
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertTrue(len(wl_files) > 0, "워크로그 파일이 생성되어야 함")

        with open(wl_files[0]) as f:
            content = f.read()
        self.assertIn("기능 추가", content)
        self.assertIn("test.txt", content)

    def test_worklog_has_header(self):
        """워크로그 파일에 프로젝트명 + 날짜 헤더가 포함"""
        self._make_change_and_commit()

        summary = "### 작업 내용\n- test"
        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary)

        subprocess.run(
            ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile],
            capture_output=True, text=True, cwd=self.repo, env=self._env(), timeout=15,
        )

        import glob
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        with open(wl_files[0]) as f:
            first_line = f.readline()
        self.assertTrue(first_line.startswith("# Worklog:"))

    def test_snapshot_updated(self):
        """워크로그 작성 후 스냅샷이 갱신됨"""
        self._make_change_and_commit()

        summary = "### 작업 내용\n- test"
        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary)

        subprocess.run(
            ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile],
            capture_output=True, text=True, cwd=self.repo, env=self._env(), timeout=15,
        )

        snapshot = os.path.join(self.tmp, ".claude", "worklogs", ".snapshot")
        self.assertTrue(os.path.exists(snapshot), "스냅샷 파일이 생성되어야 함")
        with open(snapshot) as f:
            data = json.load(f)
        self.assertIn("timestamp", data)
        self.assertGreater(data["timestamp"], 0)

    def test_git_add_worklogs(self):
        """WORKLOG_GIT_TRACK=true면 .worklogs/ 가 git add됨"""
        self._make_change_and_commit()

        summary = "### 작업 내용\n- test"
        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary)

        subprocess.run(
            ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile],
            capture_output=True, text=True, cwd=self.repo, env=self._env(), timeout=15,
        )

        # staged 파일 확인
        r = subprocess.run(
            ["git", "-C", self.repo, "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
        )
        self.assertTrue(
            any(".worklogs/" in f for f in r.stdout.splitlines()),
            f".worklogs/ should be staged, got: {r.stdout}",
        )

    def test_no_cost_option(self):
        """--no-cost 옵션 시 (auto) 표시"""
        self._make_change_and_commit()

        summary = "### 작업 내용\n- test"
        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary)

        subprocess.run(
            ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile, "--no-cost"],
            capture_output=True, text=True, cwd=self.repo, env=self._env(), timeout=15,
        )

        import glob
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        with open(wl_files[0]) as f:
            content = f.read()
        self.assertIn("(auto)", content)


# ══════════════════════════════════════════════════════════════════════════════
# 4. manual 모드에서 post-commit 스킵
# ══════════════════════════════════════════════════════════════════════════════


class TestPostCommitManualMode(_GitRepoBase):

    def test_skip_when_manual(self):
        """WORKLOG_TIMING=manual이면 post-commit 스킵"""
        self._make_change_and_commit()
        env = self._env(WORKLOG_TIMING="manual")
        env.pop("CLAUDECODE", None)
        r = self._run_post_commit(env=env)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(
            os.path.exists(os.path.join(self.repo, ".worklogs")),
            ".worklogs/ should not exist in manual mode",
        )


# ══════════════════════════════════════════════════════════════════════════════
# on-commit.sh 동작 검증 (PostToolUse Bash hook)
# ══════════════════════════════════════════════════════════════════════════════


class TestOnCommitHookBehavior(unittest.TestCase):
    """on-commit.sh: git commit 감지 → decision:block 반환"""

    def setUp(self):
        if not shutil.which("jq"):
            self.skipTest("jq not found")
        self.hook = os.path.join(PACKAGE_DIR, "hooks", "on-commit.sh")

    def _run_hook(self, command: str, timing: str = "stop") -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        env = {**os.environ, "WORKLOG_TIMING": timing}
        return subprocess.run(
            ["bash", self.hook],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )

    def test_git_commit_returns_block(self):
        """git commit 명령 → decision:block"""
        r = self._run_hook('git commit -m "feat: test"')
        self.assertEqual(r.returncode, 0)
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")

    def test_block_reason_contains_worklog(self):
        """block reason에 /worklog 포함"""
        r = self._run_hook('git commit -m "test"')
        result = json.loads(r.stdout)
        self.assertIn("/worklog", result["reason"])

    def test_git_push_no_block(self):
        """git push → block 없음 (exit 0, no output)"""
        r = self._run_hook("git push")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_git_pull_no_block(self):
        """git pull → block 없음"""
        r = self._run_hook("git pull")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_unrelated_bash_command_no_block(self):
        """git과 무관한 bash 명령은 block 없음"""
        r = self._run_hook("echo hello world")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_manual_timing_no_block(self):
        """WORKLOG_TIMING=manual → block 없음"""
        r = self._run_hook('git commit -m "test"', timing="manual")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_git_commit_amend_triggers_block(self):
        """git commit --amend도 감지"""
        r = self._run_hook("git commit --amend --no-edit")
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")

    def test_multiline_with_git_commit(self):
        """멀티라인 명령에서 git commit 감지"""
        cmd = 'git add -A && git commit -m "feat: test" && git push'
        r = self._run_hook(cmd)
        result = json.loads(r.stdout)
        self.assertEqual(result["decision"], "block")


class TestCommitDocCheckHookBehavior(unittest.TestCase):
    """commit-doc-check.sh: git commit 후 PROJECT.md 업데이트 체크"""

    def setUp(self):
        if not shutil.which("jq"):
            self.skipTest("jq not found")
        self.hook = os.path.join(PACKAGE_DIR, "hooks", "commit-doc-check.sh")
        self.tmp = tempfile.mkdtemp(prefix="wl_doccheck_")
        # git repo 초기화
        git_env = {"HOME": self.tmp, "PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1"}
        subprocess.run(["git", "init", self.tmp], capture_output=True, check=True, env=git_env)
        subprocess.run(["git", "-C", self.tmp, "config", "user.email", "t@t.com"], capture_output=True, env=git_env)
        subprocess.run(["git", "-C", self.tmp, "config", "user.name", "T"], capture_output=True, env=git_env)
        # PROJECT.md 생성
        with open(os.path.join(self.tmp, "PROJECT.md"), "w") as f:
            f.write("# Project\n")
        subprocess.run(["git", "-C", self.tmp, "add", "PROJECT.md"], capture_output=True, env=git_env)
        subprocess.run(["git", "-C", self.tmp, "commit", "-m", "init"], capture_output=True, env=git_env)
        self._git_env = git_env

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_hook(self, command: str, threshold: int = 3) -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        env = {
            **os.environ,
            "HOME": self.tmp,
            "GIT_CONFIG_NOSYSTEM": "1",
            "PROJECT_DOC_CHECK_INTERVAL": str(threshold),
        }
        return subprocess.run(
            ["bash", self.hook],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.tmp,
            env=env,
            timeout=5,
        )

    def _make_commits(self, n: int):
        """더미 커밋 n개 생성"""
        git_env = {**self._git_env, "HOME": self.tmp}
        for i in range(n):
            f = os.path.join(self.tmp, f"dummy_{i}.txt")
            with open(f, "w") as fp:
                fp.write(f"commit {i}\n")
            subprocess.run(["git", "-C", self.tmp, "add", f], capture_output=True, env=git_env)
            subprocess.run(["git", "-C", self.tmp, "commit", "-m", f"chore: dummy {i}"], capture_output=True, env=git_env)

    def test_git_push_no_output(self):
        """git push → 출력 없음"""
        r = self._run_hook("git push")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_no_project_md_no_output(self):
        """PROJECT.md 없는 프로젝트 → 출력 없음"""
        os.remove(os.path.join(self.tmp, "PROJECT.md"))
        r = self._run_hook('git commit -m "test"')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_under_threshold_no_message(self):
        """threshold 미달 커밋 수 → 메시지 없음"""
        self._make_commits(1)  # 1 commit, threshold=3
        r = self._run_hook('git commit -m "test"', threshold=3)
        self.assertEqual(r.stdout.strip(), "")

    def test_over_threshold_shows_message(self):
        """threshold 초과 시 메시지 출력"""
        self._make_commits(3)  # threshold=3 → 3 >= 3 → 메시지 출력
        r = self._run_hook('git commit -m "test"', threshold=3)
        self.assertIn("PROJECT.md", r.stdout)

    def test_stdin_json_parsing(self):
        """stdin JSON에서 command 올바르게 파싱됨 (환경변수 방식 아님)"""
        env = {
            **os.environ,
            "HOME": self.tmp,
            "GIT_CONFIG_NOSYSTEM": "1",
            "PROJECT_DOC_CHECK_INTERVAL": "1",
        }
        env.pop("TOOL_INPUT", None)
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": 'git commit -m "test"'}})
        self._make_commits(2)
        r = subprocess.run(
            ["bash", self.hook],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.tmp,
            env=env,
            timeout=5,
        )
        self.assertEqual(r.returncode, 0)
        # threshold=1, 2 commits → 메시지 있어야 함
        self.assertIn("PROJECT.md", r.stdout)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    import sys
    sys.exit(0 if result.result.wasSuccessful() else 1)
