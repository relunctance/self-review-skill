#!/usr/bin/env python3
"""
self-review-skill: review_status.py 单元测试
TDD 模式：先写测试，再写实现
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_real_home():
    """获取真实 home 目录"""
    return subprocess.check_output(
        ["getent", "passwd", os.environ.get("USER", "") or subprocess.check_output(["whoami"]).decode().strip()],
        text=True
    ).split(":")[5]


class TestReviewStatus:
    """review_status.py 测试"""

    STATUS_SCRIPT = "/home/gql/repos/self-review-skill/scripts/review_status.py"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后清理"""
        self.test_id = f"test_status_{os.getpid()}"
        self.temp_dirs = []
        yield
        # 清理状态文件
        real_home = get_real_home()
        review_states = Path(real_home) / ".hermes" / "review-states"
        if review_states.exists():
            for item in review_states.iterdir():
                if self.test_id in item.name:
                    shutil.rmtree(item, ignore_errors=True)
        # 清理临时目录
        for td in self.temp_dirs:
            shutil.rmtree(td, ignore_errors=True)

    def create_temp_repo(self) -> Path:
        """创建临时 git 仓库"""
        tmpdir = tempfile.mkdtemp(prefix=f"self_review_{self.test_id}_")
        self.temp_dirs.append(tmpdir)
        repo_path = Path(tmpdir) / "repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path, check=True, capture_output=True
        )
        return repo_path

    def call_status(self, cwd: Path = None, json_mode: bool = True) -> tuple:
        """调用 review_status.py"""
        cmd = ["python3", self.STATUS_SCRIPT]
        if json_mode:
            cmd.append("--json")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None
        )
        return result.stdout, result.stderr, result.returncode

    def test_status_not_in_git_repo(self):
        """验证：不在 git 仓库时返回错误"""
        tmpdir = tempfile.mkdtemp(prefix=f"self_review_{self.test_id}_notgit_")
        self.temp_dirs.append(tmpdir)

        stdout, stderr, returncode = self.call_status(cwd=Path(tmpdir))

        assert returncode == 1, f"Expected exit code 1, got {returncode}"
        data = json.loads(stdout)
        assert data["success"] == False
        assert data["error"] == "NOT_IN_GIT_REPO"
        print("✅ test_status_not_in_git_repo passed")

    def test_status_json_output_format(self):
        """验证：JSON 输出格式正确"""
        repo_path = self.create_temp_repo()

        stdout, stderr, returncode = self.call_status(cwd=repo_path)

        assert returncode == 0, f"Expected exit code 0, got {returncode}"
        data = json.loads(stdout)

        # 验证必需字段
        required_fields = [
            "success", "repo", "branch", "state",
            "approved", "diff_hash", "cycle_count"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        assert data["success"] == True
        print("✅ test_status_json_output_format passed")

    def test_status_shows_idle_when_no_state_file(self):
        """验证：无状态文件时显示 IDLE"""
        repo_path = self.create_temp_repo()

        stdout, stderr, returncode = self.call_status(cwd=repo_path)

        assert returncode == 0
        data = json.loads(stdout)
        assert data["state"] == "IDLE"
        assert data["approved"] == False
        assert data["diff_hash"] == ""
        assert data["cycle_count"] == 0
        print("✅ test_status_shows_idle_when_no_state_file passed")

    def test_status_shows_pending_review_after_block(self):
        """验证：block 后状态显示 PENDING_REVIEW"""
        repo_path = self.create_temp_repo()

        # 获取实际 branch name（git branch --show-current 返回 master）
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo_path, capture_output=True, text=True
        )
        actual_branch = branch_result.stdout.strip() or "detached"

        # 手动创建状态文件（使用实际 repo_path 和 branch 计算 hash）
        real_home = get_real_home()
        repo_hash = hashlib.md5(str(repo_path).encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(actual_branch.encode()).hexdigest()[:8]
        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        state_file.write_text(json.dumps({
            "state": "PENDING_REVIEW",
            "approved": False,
            "diff_hash": "test_hash_123",
            "cycle_count": 2
        }))

        stdout, stderr, returncode = self.call_status(cwd=repo_path)

        assert returncode == 0
        data = json.loads(stdout)
        assert data["state"] == "PENDING_REVIEW"
        assert data["approved"] == False
        assert data["diff_hash"] == "test_hash_123"
        assert data["cycle_count"] == 2
        print("✅ test_status_shows_pending_review_after_block passed")

    def test_status_shows_approved_after_approve(self):
        """验证：approve 后状态显示 approved=true"""
        repo_path = self.create_temp_repo()

        # 获取实际 branch name
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo_path, capture_output=True, text=True
        )
        actual_branch = branch_result.stdout.strip() or "detached"

        # 手动创建已批准的状态文件（使用实际 repo_path 和 branch 计算 hash）
        real_home = get_real_home()
        repo_hash = hashlib.md5(str(repo_path).encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(actual_branch.encode()).hexdigest()[:8]
        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        state_file.write_text(json.dumps({
            "state": "PENDING_REVIEW",
            "approved": True,
            "diff_hash": "approved_hash_456",
            "cycle_count": 1
        }))

        stdout, stderr, returncode = self.call_status(cwd=repo_path)

        assert returncode == 0
        data = json.loads(stdout)
        assert data["state"] == "PENDING_REVIEW"
        assert data["approved"] == True
        assert data["diff_hash"] == "approved_hash_456"
        assert data["cycle_count"] == 1
        print("✅ test_status_shows_approved_after_approve passed")


if __name__ == "__main__":
    # 手动运行测试（不使用 pytest fixture）
    import sys
    test = TestReviewStatus()

    tests = [
        test.test_status_not_in_git_repo,
        test.test_status_json_output_format,
        test.test_status_shows_idle_when_no_state_file,
        test.test_status_shows_pending_review_after_block,
        test.test_status_shows_approved_after_approve,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1

    print(f"\n总计: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
