#!/usr/bin/env python3
"""
worklog-write.sh e2e 테스트 — Notion 모드 / notion-only 모드 검증

격리된 git repo에서 worklog-write.sh 직접 실행:
- notion-only 모드: 로컬 파일 미작성, Notion stub 호출
- notion 모드: 로컬 파일 + Notion stub 호출

Run: python3 -m pytest tests/test_worklog_write_e2e.py -v
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class _WorklogWriteBase(unittest.TestCase):
    """격리된 git repo + worklog-write.sh 환경 픽스처"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai_wl_ww_")

        # 글로벌 git hooks 격리용 env
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

        # worklog-write.sh 복사
        shutil.copy(
            os.path.join(PACKAGE_DIR, "scripts", "worklog-write.sh"),
            os.path.join(self.ai_dir, "scripts", "worklog-write.sh"),
        )
        os.chmod(os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), 0o755)

        # notion-worklog.sh stub
        self.notion_log = os.path.join(self.tmp, "notion-stub.log")
        notion_stub = os.path.join(self.ai_dir, "scripts", "notion-worklog.sh")
        with open(notion_stub, "w") as f:
            f.write('#!/bin/bash\n'
                    'LOG_FILE="${NOTION_STUB_LOG}"\n'
                    'echo "TITLE=$1" >> "$LOG_FILE"\n'
                    'echo "DATE=$2" >> "$LOG_FILE"\n'
                    'echo "PROJECT=$3" >> "$LOG_FILE"\n'
                    'echo "COST=$4" >> "$LOG_FILE"\n'
                    'echo "DURATION=$5" >> "$LOG_FILE"\n'
                    'echo "MODEL=$6" >> "$LOG_FILE"\n'
                    'echo "---" >> "$LOG_FILE"\n'
                    'exit 0\n')
        os.chmod(notion_stub, 0o755)

        # token-cost.py stub
        with open(os.path.join(self.ai_dir, "scripts", "token-cost.py"), "w") as f:
            f.write("print('0,0.000,')\n")

        # duration.py stub
        with open(os.path.join(self.ai_dir, "scripts", "duration.py"), "w") as f:
            f.write("print('0,0')\n")

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
        os.makedirs(os.path.join(self.tmp, ".claude", "worklogs"), exist_ok=True)

        # claude 스텁 (항상 실패)
        self._bin = os.path.join(self.tmp, "bin")
        os.makedirs(self._bin, exist_ok=True)
        with open(os.path.join(self._bin, "claude"), "w") as f:
            f.write("#!/bin/bash\nexit 1\n")
        os.chmod(os.path.join(self._bin, "claude"), 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, **extra):
        """테스트용 환경변수 (claude 스텁 사용, 격리)"""
        python3_dir = os.path.dirname(shutil.which("python3") or "/usr/bin/python3")
        safe_path = f'{self._bin}:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:{python3_dir}'
        env = {
            "HOME": self.tmp,
            "AI_WORKLOG_DIR": self.ai_dir,
            "WORKLOG_TIMING": "stop",
            "WORKLOG_DEST": "git",
            "WORKLOG_GIT_TRACK": "true",
            "WORKLOG_LANG": "ko",
            "NOTION_STUB_LOG": self.notion_log,
            "PATH": safe_path,
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update(extra)
        return env

    def _run_worklog_write(self, summary_text, extra_args=None, **env_overrides):
        """worklog-write.sh 실행

        env_overrides에 WORKLOG_DEST 등이 있으면 settings.json도 동기화한다.
        (worklog-write.sh의 _load_settings_env가 settings.json을 export하므로)
        """
        # settings.json env를 env_overrides에 맞게 갱신
        settings_path = os.path.join(self.ai_dir, "settings.json")
        with open(settings_path) as f:
            settings = json.load(f)
        settings_env = settings.get("env", {})
        for k in ("WORKLOG_DEST", "WORKLOG_GIT_TRACK", "WORKLOG_LANG",
                   "WORKLOG_TIMING", "NOTION_DB_ID"):
            if k in env_overrides:
                settings_env[k] = env_overrides[k]
        settings["env"] = settings_env
        with open(settings_path, "w") as f:
            json.dump(settings, f)

        tmpfile = os.path.join(self.tmp, "summary.txt")
        with open(tmpfile, "w") as f:
            f.write(summary_text)

        cmd = ["bash", os.path.join(self.ai_dir, "scripts", "worklog-write.sh"), tmpfile]
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo,
            env=self._env(**env_overrides),
            timeout=15,
        )

        os.remove(tmpfile)
        return result

    def _notion_stub_log(self):
        """notion stub 로그 내용 반환"""
        if os.path.exists(self.notion_log):
            with open(self.notion_log) as f:
                return f.read()
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# 1. notion-only 모드: 로컬 파일 미작성, Notion stub 호출
# ══════════════════════════════════════════════════════════════════════════════


class TestNotionOnlyNoLocalFile(_WorklogWriteBase):
    """notion-only 모드: 로컬 파일 미작성, Notion stub 호출"""

    _SUMMARY = "### 작업 내용\n- 테스트 기능 추가\n\n### 변경 파일\n- `test.py`: 테스트 추가"

    def _run(self):
        return self._run_worklog_write(
            self._SUMMARY,
            WORKLOG_DEST="notion-only",
            NOTION_DB_ID="fake-db-id",
        )

    def test_exit_zero(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_local_file_created(self):
        self._run()
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertEqual(len(wl_files), 0, ".worklogs/ 에 파일이 없어야 함")

    def test_notion_stub_called(self):
        self._run()
        self.assertTrue(os.path.exists(self.notion_log), "notion stub이 호출되어야 함")

    def test_notion_stub_receives_correct_args(self):
        self._run()
        log = self._notion_stub_log()
        self.assertIn("TITLE=", log)
        # TITLE이 비어있지 않은지
        for line in log.splitlines():
            if line.startswith("TITLE="):
                self.assertNotEqual(line, "TITLE=", "TITLE이 비어있으면 안 됨")

    def test_pending_cleaned(self):
        """pending 마커가 정리되는지 확인"""
        pending_dir = os.path.join(self.tmp, ".claude", "worklogs", ".pending")
        os.makedirs(pending_dir, exist_ok=True)
        pending_file = os.path.join(pending_dir, "12345.json")
        repo_abs = os.path.realpath(self.repo)
        with open(pending_file, "w") as f:
            json.dump({"commit_msg": "test", "changed_files": "test.py", "project_cwd": repo_abs}, f)

        self._run()
        self.assertFalse(os.path.exists(pending_file), "pending 마커가 삭제되어야 함")


# ══════════════════════════════════════════════════════════════════════════════
# 2. notion 모드: 로컬 파일 + Notion stub 호출
# ══════════════════════════════════════════════════════════════════════════════


class TestNotionBothMode(_WorklogWriteBase):
    """notion 모드: 로컬 파일 + Notion stub 호출"""

    _SUMMARY = "### 작업 내용\n- API 엔드포인트 추가\n\n### 변경 파일\n- `api.py`: 엔드포인트 추가"

    def _run(self):
        return self._run_worklog_write(
            self._SUMMARY,
            WORKLOG_DEST="notion",
            NOTION_DB_ID="fake-db-id",
        )

    def test_local_file_created(self):
        self._run()
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertTrue(len(wl_files) > 0, "로컬 파일이 생성되어야 함")

    def test_notion_stub_called(self):
        self._run()
        self.assertTrue(os.path.exists(self.notion_log), "notion stub이 호출되어야 함")

    def test_local_content_has_summary(self):
        self._run()
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        with open(wl_files[0]) as f:
            content = f.read()
        self.assertIn("API 엔드포인트 추가", content)

    def test_stub_receives_project_name(self):
        self._run()
        log = self._notion_stub_log()
        self.assertIn("PROJECT=repo", log)


# ══════════════════════════════════════════════════════════════════════════════
# 3. 영어 출력 모드: WORKLOG_LANG=en
# ══════════════════════════════════════════════════════════════════════════════


class TestEnglishOutput(_WorklogWriteBase):
    """WORKLOG_LANG=en 모드: 토큰 섹션이 영어로 출력되는지 검증"""

    _SUMMARY = "### Summary\n- Added search feature\n\n### Changed Files\n- `search.py`: add search endpoint"

    def _run(self):
        return self._run_worklog_write(
            self._SUMMARY,
            WORKLOG_DEST="git",
            WORKLOG_LANG="en",
        )

    def _read_worklog(self):
        self._run()
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertTrue(len(wl_files) > 0, "워크로그 파일이 생성되어야 함")
        with open(wl_files[0]) as f:
            return f.read()

    def test_english_token_header(self):
        content = self._read_worklog()
        self.assertIn("### Token Usage", content)

    def test_english_model_label(self):
        content = self._read_worklog()
        self.assertIn("- Model:", content)

    def test_english_session_label(self):
        content = self._read_worklog()
        self.assertIn("- This session:", content)

    def test_no_korean_headers(self):
        content = self._read_worklog()
        self.assertNotIn("토큰 사용량", content)
        self.assertNotIn("모델:", content)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Git 미추적 모드: WORKLOG_GIT_TRACK=false
# ══════════════════════════════════════════════════════════════════════════════


class TestGitTrackFalse(_WorklogWriteBase):
    """WORKLOG_GIT_TRACK=false 모드: 파일 생성되지만 git staging 안 됨"""

    _SUMMARY = "### 작업 내용\n- 설정 변경\n\n### 변경 파일\n- `config.py`: 설정 수정"

    def _run(self):
        return self._run_worklog_write(
            self._SUMMARY,
            WORKLOG_DEST="git",
            WORKLOG_GIT_TRACK="false",
        )

    def test_file_created_but_not_staged(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        # 파일 존재 확인
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertTrue(len(wl_files) > 0, ".worklogs/*.md 파일이 존재해야 함")
        # git staged에 없는지 확인
        git_env = {
            "HOME": self.tmp,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "dumb",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        staged = subprocess.run(
            ["git", "-C", self.repo, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, env=git_env,
        )
        self.assertNotIn(".worklogs/", staged.stdout)

    def test_file_content_valid(self):
        self._run()
        wl_files = glob.glob(os.path.join(self.repo, ".worklogs", "*.md"))
        self.assertTrue(len(wl_files) > 0)
        with open(wl_files[0]) as f:
            content = f.read()
        self.assertIn("설정 변경", content)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    import sys
    sys.exit(0 if result.result.wasSuccessful() else 1)
