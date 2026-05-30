#!/usr/bin/env python3
"""
self-review-skill: Hermes Hook 环境集成测试
TDD 模式：验证真实 Hermes hook 环境

注意：此测试需要 Hermes hook 已注册（hermes hooks list 应显示 pre_tool_call）
运行：hermes hooks test pre_tool_call 验证环境
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


class TestRealHookEnv:
    """Hermes Hook 真实环境集成测试"""

    HOOK_SCRIPT = "/home/gql/repos/self-review-skill/hooks/self-review-hook.sh"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        self.test_id = f"test_hook_env_{os.getpid()}"
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

    def create_repo_with_remote(self) -> tuple:
        """创建带远程的临时仓库"""
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

    def test_hermes_hook_registered(self):
        """验证：Hermes hook 已在 config.yaml 中注册"""
        result = subprocess.run(
            ["hermes", "hooks", "list"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"hermes hooks list failed: {result.stderr}"
        assert "pre_tool_call" in result.stdout, \
            f"pre_tool_call hook not registered, got: {result.stdout}"
        print("✅ test_hermes_hook_registered passed")

    def test_hermes_hook_test_passes(self):
        """验证：hermes hooks test pre_tool_call 成功"""
        result = subprocess.run(
            ["hermes", "hooks", "test", "pre_tool_call"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"hermes hooks test failed: {result.stderr}"
        assert "exit=0" in result.stdout, f"Hook test should exit 0, got: {result.stdout}"
        print("✅ test_hermes_hook_test_passes passed")

    def test_hook_blocks_commit_in_clean_repo(self):
        """验证：干净仓库第一次提交被 hook 拦截"""
        repo_path, _ = self.create_repo_with_remote()

        (repo_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        result = self.call_hook(repo_path, "git commit -m 'first commit'")
        assert '"action":"block"' in result, f"First commit should be blocked, got: {result}"
        print("✅ test_hook_blocks_commit_in_clean_repo passed")

    def test_hook_allows_after_approved(self):
        """验证：approved 后 hook 放行（相同 diff_hash 时）"""
        repo_path, _ = self.create_repo_with_remote()

        # 第一次提交，建立状态
        (repo_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo_path, check=True, capture_output=True)

        # 第二次提交，建立状态（diff_hash_2）
        (repo_path / "file.txt").write_text("world")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        result1 = self.call_hook(repo_path, "git commit -m 'v2'")
        assert '"action":"block"' in result1, f"Second commit should be blocked, got: {result1}"

        # 确认状态文件
        import hashlib
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path, capture_output=True, text=True
        )
        branch = branch_result.stdout.strip() or "detached"
        repo_hash = hashlib.md5(str(repo_path).encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(branch.encode()).hexdigest()[:8]
        state_dir = Path(get_real_home()) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_file = state_dir / "state.json"

        # 模拟 approved：approved=true，保留相同的 diff_hash
        state = json.loads(state_file.read_text())
        state["approved"] = True
        state_file.write_text(json.dumps(state))

        # 重新提交相同 diff，应该放行
        # 先 reset staged
        subprocess.run(["git", "reset", "HEAD"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        result2 = self.call_hook(repo_path, "git commit -m 'v2 approved'")
        assert result2.strip() in ("", "{}"), f"Approved commit should be allowed, got: {result2}"
        print("✅ test_hook_allows_after_approved passed")


if __name__ == "__main__":
    test = TestRealHookEnv()

    tests = [
        test.test_hermes_hook_registered,
        test.test_hermes_hook_test_passes,
        test.test_hook_blocks_commit_in_clean_repo,
        test.test_hook_allows_after_approved,
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
