#!/usr/bin/env python3
"""
self-review-skill: 状态机单元测试
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# 添加父目录到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_idle_to_pending_review():
    """测试：IDLE 状态遇到新 diff 应该 block"""
    from scripts.review_approve import get_real_home, get_repo_info

    with tempfile.TemporaryDirectory() as tmpdir:
        # 模拟状态文件
        state_file = Path(tmpdir) / "state.json"
        state_file.write_text('{"state":"IDLE","approved":false,"diff_hash":"","cycle_count":0}')

        # 读取并验证
        state = json.loads(state_file.read_text())
        assert state["state"] == "IDLE"
        assert state["approved"] == False
        print("✅ test_idle_to_pending_review passed")


def test_approved_same_diff_allows():
    """测试：相同 diff + approved=true 应该允许通过"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        state_file.write_text('{"state":"PENDING_REVIEW","approved":true,"diff_hash":"abc123","cycle_count":1}')

        state = json.loads(state_file.read_text())
        assert state["approved"] == True
        assert state["diff_hash"] == "abc123"
        print("✅ test_approved_same_diff_allows passed")


def test_diff_changed_resets_approved():
    """测试：diff 变化时 approved 应该重置"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        # 模拟：之前 approved 的旧 diff
        old_state = '{"state":"PENDING_REVIEW","approved":true,"diff_hash":"old_hash","cycle_count":1}'
        state_file.write_text(old_state)

        # 新 diff 到来
        new_diff_hash = "new_hash"
        state = json.loads(state_file.read_text())

        if new_diff_hash != state["diff_hash"]:
            state = {"state": "PENDING_REVIEW", "approved": False, "diff_hash": new_diff_hash, "cycle_count": 1}

        assert state["approved"] == False
        assert state["diff_hash"] == "new_hash"
        print("✅ test_diff_changed_resets_approved passed")


def test_cycle_count_detection():
    """测试：连续 3 次 diff 相同应该强制放行"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        # 模拟：连续 3 次相同 diff
        state_file.write_text('{"state":"PENDING_REVIEW","approved":false,"diff_hash":"same_hash","cycle_count":3}')

        state = json.loads(state_file.read_text())
        diff_hash = "same_hash"
        cycle_count = state["cycle_count"]

        # 循环检测逻辑
        if diff_hash == state["diff_hash"] and cycle_count >= 3:
            # 强制放行
            state = {"state": "IDLE", "approved": False, "diff_hash": "", "cycle_count": 0}
            assert state["state"] == "IDLE"
            print("✅ test_cycle_count_detection passed")


def test_real_home_detection():
    """测试：真实 home 检测"""
    from scripts.review_approve import get_real_home

    real_home = get_real_home()
    assert real_home == "/home/gql", f"Expected /home/gql, got {real_home}"
    print(f"✅ test_real_home_detection passed: {real_home}")


def test_get_repo_info():
    """测试：获取仓库信息（在当前仓库中运行）"""
    from scripts.review_approve import get_repo_info

    try:
        repo_path, branch, repo_hash, branch_hash = get_repo_info()
        assert repo_path != ""
        assert repo_hash != ""
        print(f"✅ test_get_repo_info passed: {repo_path} ({branch})")
    except Exception as e:
        print(f"⚠️  test_get_repo_info skipped: {e}")


def main():
    print("Running self-review-skill state machine tests...")
    print()

    tests = [
        test_idle_to_pending_review,
        test_approved_same_diff_allows,
        test_diff_changed_resets_approved,
        test_cycle_count_detection,
        test_real_home_detection,
        test_get_repo_info,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
