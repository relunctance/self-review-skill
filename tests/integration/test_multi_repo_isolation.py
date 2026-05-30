#!/usr/bin/env python3
"""
self-review-skill: 多仓库/分支隔离测试
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


class TestMultiRepoIsolation:
    """多仓库/分支隔离测试"""

    HOOK_SCRIPT = "/home/gql/repos/self-review-skill/hooks/self-review-hook.sh"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        self.test_id = f"test_isolation_{os.getpid()}"
        self.temp_dirs = []
        yield
        # 清理
        real_home = get_real_home()
        review_states = Path(real_home) / ".hermes" / "review-states"
        if review_states.exists():
            for item in review_states.iterdir():
                if self.test_id in item.name:
                    shutil.rmtree(item, ignore_errors=True)
        for td in self.temp_dirs:
            shutil.rmtree(td, ignore_errors=True)

    def create_repo_with_remote(self, name: str) -> tuple:
        """创建带远程的临时仓库，返回 (repo_path, remote_path)"""
        tmpdir = tempfile.mkdtemp(prefix=f"self_review_{self.test_id}_{name}_")
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

        remote_path = Path(tmpdir) / "remote.git"
        subprocess.run(
            ["git", "clone", "--bare", repo_path, remote_path],
            check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_path)],
            cwd=repo_path, check=True, capture_output=True
        )

        return repo_path, remote_path

    def call_hook(self, repo_path: Path, command: str) -> str:
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

    def test_different_repos_independent(self):
        """验证：不同仓库状态独立"""
        repo_a, _ = self.create_repo_with_remote("repo_a")
        repo_b, _ = self.create_repo_with_remote("repo_b")

        # repo-A: 第一次提交，block
        (repo_a / "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo_a, check=True, capture_output=True)
        result_a1 = self.call_hook(repo_a, "git commit -m 'repo-a commit 1'")
        assert '"action":"block"' in result_a1, f"Repo-A first commit should be blocked, got: {result_a1}"

        # repo-B: 第一次提交，应该独立 block
        (repo_b / "b.txt").write_text("world")
        subprocess.run(["git", "add", "b.txt"], cwd=repo_b, check=True, capture_output=True)
        result_b1 = self.call_hook(repo_b, "git commit -m 'repo-b commit 1'")
        assert '"action":"block"' in result_b1, f"Repo-B first commit should be blocked independently, got: {result_b1}"

        # repo-A: 第二次提交，相同 diff，应该累加 cycle_count
        (repo_a / "a.txt").write_text("hello again")
        subprocess.run(["git", "add", "a.txt"], cwd=repo_a, check=True, capture_output=True)
        result_a2 = self.call_hook(repo_a, "git commit -m 'repo-a commit 2'")
        assert '"action":"block"' in result_a2, f"Repo-A second commit should still be blocked"

        # repo-B 不受影响，仍然是第一次
        (repo_b / "b.txt").write_text("world again")
        subprocess.run(["git", "add", "b.txt"], cwd=repo_b, check=True, capture_output=True)
        result_b2 = self.call_hook(repo_b, "git commit -m 'repo-b commit 2'")
        assert '"action":"block"' in result_b2, f"Repo-B should still be at first cycle, got: {result_b2}"

        print("✅ test_different_repos_independent passed")

    def test_same_repo_different_branches_independent(self):
        """验证：同一仓库不同分支状态独立"""
        repo, _ = self.create_repo_with_remote("repo")

        # main 分支：第一次提交
        (repo / "main.txt").write_text("main content")
        subprocess.run(["git", "add", "main.txt"], cwd=repo, check=True, capture_output=True)
        result_main = self.call_hook(repo, "git commit -m 'main commit'")
        assert '"action":"block"' in result_main, f"Main branch first commit should be blocked, got: {result_main}"

        # 创建 feature 分支
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=repo, check=True, capture_output=True
        )

        # feature 分支：第一次提交，应该独立于 main
        (repo / "feature.txt").write_text("feature content")
        subprocess.run(["git", "add", "feature.txt"], cwd=repo, check=True, capture_output=True)
        result_feature = self.call_hook(repo, "git commit -m 'feature commit'")
        assert '"action":"block"' in result_feature, f"Feature branch should have independent state, got: {result_feature}"

        print("✅ test_same_repo_different_branches_independent passed")


if __name__ == "__main__":
    import sys
    test = TestMultiRepoIsolation()

    tests = [
        test.test_different_repos_independent,
        test.test_same_repo_different_branches_independent,
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
