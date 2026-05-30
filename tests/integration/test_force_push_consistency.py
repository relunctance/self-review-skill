#!/usr/bin/env python3
"""
self-review-skill: force-push 状态一致性测试
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.review_approve import get_real_home


class TestForcePushConsistency:
    """force-push 后状态一致性测试"""

    HOOK_SCRIPT = "/home/gql/repos/self-review-skill/hooks/self-review-hook.sh"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        self.test_id = f"test_forcepush_{os.getpid()}"
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

    def get_branch_name(self, repo_path: Path) -> str:
        """获取分支名"""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path, capture_output=True, text=True
        )
        return result.stdout.strip() or "detached"

    def test_new_diff_after_existing_state(self):
        """验证：状态存在时，新 diff 应该被识别并重新 block"""
        repo_path, _ = self.create_repo_with_remote()
        branch = self.get_branch_name(repo_path)

        # === 阶段1：手动建立状态文件（模拟之前有提交）===
        real_home = get_real_home()
        repo_hash = hashlib.md5(str(repo_path).encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(branch.encode()).hexdigest()[:8]
        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        # 用 v1 内容的 diff_hash 作为"旧状态"
        (repo_path / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)
        diff_v1_result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=repo_path, capture_output=True, text=True
        )
        diff_v1_hash = hashlib.md5(diff_v1_result.stdout.encode()).hexdigest()

        state_file.write_text(json.dumps({
            "state": "PENDING_REVIEW",
            "diff_hash": diff_v1_hash,
            "approved": False,
            "cycle_count": 2,
            "last_updated": "2026-01-01T00:00:00Z"
        }))

        # === 阶段2：准备新 diff（v2 不同于 v1）===
        (repo_path / "file.txt").write_text("v2 different content")
        subprocess.run(["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True)

        # === 阶段3：hook 应该识别为新 diff 并 block ===
        result = self.call_hook(repo_path, "git commit -m 'v2'")
        assert '"action":"block"' in result, f"New diff after existing state should be blocked, got: {result}"

        # 验证 diff_hash 确实变了
        state = json.loads(state_file.read_text())
        assert state["diff_hash"] != diff_v1_hash, "diff_hash should update for new content"

        print("✅ test_new_diff_after_existing_state passed")


if __name__ == "__main__":
    import sys
    test = TestForcePushConsistency()

    tests = [
        test.test_new_diff_after_existing_state,
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
