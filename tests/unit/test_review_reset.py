#!/usr/bin/env python3
"""
self-review-skill: review_reset.py 单元测试
TDD RED 阶段：先写测试，验证 reset 功能
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# 添加父目录到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_reset_deletes_state_file():
    """测试：reset 应该删除指定仓库/分支的 state.json"""
    from scripts.review_reset import get_real_home, get_repo_info, reset_review_state

    with tempfile.TemporaryDirectory() as tmpdir:
        # 模拟仓库结构
        repo_dir = Path(tmpdir) / "test_repo"
        repo_dir.mkdir()
        (repo_dir / "file.txt").write_text("test")

        # 初始化 git 仓库
        os.system(f"git init -q {repo_dir}")
        os.system(f"git -C {repo_dir} config user.email 'test@test.com'")
        os.system(f"git -C {repo_dir} config user.name 'test'")
        os.system(f"git -C {repo_dir} add .")
        os.system(f"git -C {repo_dir} commit -m 'init'")

        # 手动创建状态文件
        real_home = get_real_home()
        repo_path, branch, repo_hash, branch_hash = get_repo_info(str(repo_dir))
        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"
        state_file.write_text('{"state":"PENDING_REVIEW","approved":false,"diff_hash":"abc","cycle_count":2}')

        # 验证状态文件存在
        assert state_file.exists(), f"状态文件应该存在: {state_file}"
        print(f"✅ 状态文件存在: {state_file}")

        # 执行 reset
        result = reset_review_state(str(repo_dir))

        # 验证状态文件被删除
        assert not state_file.exists(), f"状态文件应该被删除: {state_file}"
        print("✅ test_reset_deletes_state_file passed")


def test_reset_nonexistent_repo():
    """测试：不存在的仓库路径应该报错"""
    from scripts.review_reset import reset_review_state

    try:
        reset_review_state("/nonexistent/path")
        assert False, "应该抛出异常"
    except SystemExit as e:
        assert e.code == 1
        print("✅ test_reset_nonexistent_repo passed")


def test_reset_without_git_repo():
    """测试：非 git 仓库应该报错"""
    from scripts.review_reset import reset_review_state

    with tempfile.TemporaryDirectory() as tmpdir:
        not_git_dir = Path(tmpdir) / "not_git"
        not_git_dir.mkdir()

        try:
            reset_review_state(str(not_git_dir))
            assert False, "应该抛出异常"
        except SystemExit as e:
            assert e.code == 1
            print("✅ test_reset_without_git_repo passed")


if __name__ == "__main__":
    print("=== TDD RED: 运行测试 ===")
    test_reset_deletes_state_file()
    test_reset_nonexistent_repo()
    test_reset_without_git_repo()
    print("\n✅ 所有测试通过")
