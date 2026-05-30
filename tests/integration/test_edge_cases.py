#!/usr/bin/env python3
"""
self-review-skill: 边界条件测试
TDD 模式：先写测试，再写实现
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.review_approve import get_real_home


class TestEdgeCases:
    """边界条件测试"""

    HOOK_SCRIPT = "/home/gql/repos/self-review-skill/hooks/self-review-hook.sh"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每个测试前后清理"""
        self.test_id = f"test_edge_{os.getpid()}"
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

    def create_temp_repo(self, with_remote: bool = False) -> Path:
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

        if with_remote:
            remote_path = Path(tmpdir) / "remote.git"
            subprocess.run(
                ["git", "clone", "--bare", repo_path, remote_path],
                check=True, capture_output=True
            )
            subprocess.run(
                ["git", "remote", "add", "origin", str(remote_path)],
                cwd=repo_path, check=True, capture_output=True
            )

        return repo_path

    def call_hook(self, repo_path: Path, command: str) -> str:
        """调用 hook，返回 stdout"""
        payload = json.dumps({
            "tool_input": {"command": command},
            "cwd": str(repo_path)
        })
        result = subprocess.run(
            [self.HOOK_SCRIPT],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(repo_path)
        )
        return result.stdout

    def test_empty_repo_first_commit_blocked(self):
        """验证：空仓库第一次提交被拦截"""
        repo_path = self.create_temp_repo(with_remote=True)

        (repo_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        result = self.call_hook(repo_path, "git commit -m 'first commit'")
        assert '"action":"block"' in result, f"First commit in empty repo should be blocked, got: {result}"
        print("✅ test_empty_repo_first_commit_blocked passed")

    def test_no_remote_repo_blocked(self):
        """验证：无远程仓库的提交也被拦截"""
        repo_path = self.create_temp_repo(with_remote=False)

        (repo_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        result = self.call_hook(repo_path, "git commit -m 'commit without remote'")
        assert '"action":"block"' in result, f"Commit without remote should still be blocked, got: {result}"
        print("✅ test_no_remote_repo_blocked passed")

    def test_detached_head_commit_blocked(self):
        """验证：detached HEAD 状态下提交被拦截"""
        repo_path = self.create_temp_repo(with_remote=True)

        # 先做一次提交
        (repo_path / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)

        # 进入 detached HEAD
        subprocess.run(
            ["git", "checkout", "--detach", "HEAD"],
            cwd=repo_path, check=True, capture_output=True
        )

        # 提交
        (repo_path / "file.txt").write_text("v2 in detached")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        result = self.call_hook(repo_path, "git commit -m 'detached commit'")
        assert '"action":"block"' in result, f"Detached HEAD commit should be blocked, got: {result}"
        print("✅ test_detached_head_commit_blocked passed")

    def test_empty_staged_commit_allowed(self):
        """验证：无 staged 内容的提交被放行"""
        repo_path = self.create_temp_repo(with_remote=True)

        # 先做一次提交
        (repo_path / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)

        # 无 staged 内容
        result = self.call_hook(repo_path, "git commit -m 'empty commit'")
        assert result.strip() in ("", "{}"), f"Commit without staged content should be allowed, got: {result}"
        print("✅ test_empty_staged_commit_allowed passed")

    def test_only_unchanged_file_staged(self):
        """验证：staged 后没有实际改动的文件"""
        repo_path = self.create_temp_repo(with_remote=True)

        # 提交初始版本
        (repo_path / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)

        # add 同样的内容（无实际变化）
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        # 检查 staged 是否有变化
        staged_result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=repo_path, capture_output=True, text=True
        )

        # 如果没有 staged 变化，hook 应该放行
        if not staged_result.stdout.strip():
            result = self.call_hook(repo_path, "git commit -m 'no change'")
            assert result.strip() in ("", "{}"), \
                f"Commit with no actual staged changes should be allowed, got: {result}"
            print("✅ test_only_unchanged_file_staged passed")
        else:
            # 有变化则应该 block
            result = self.call_hook(repo_path, "git commit -m 'no change'")
            assert '"action":"block"' in result, f"Commit with staged changes should be blocked, got: {result}"
            print("✅ test_only_unchanged_file_staged passed (has staged changes)")


if __name__ == "__main__":
    import sys
    test = TestEdgeCases()

    tests = [
        test.test_empty_repo_first_commit_blocked,
        test.test_no_remote_repo_blocked,
        test.test_detached_head_commit_blocked,
        test.test_empty_staged_commit_allowed,
        test.test_only_unchanged_file_staged,
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
