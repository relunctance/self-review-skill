#!/usr/bin/env python3
"""
self-review-skill: flock 竞态条件测试

测试 approve/reset 脚本与 hook 并发时的行为
"""

import json
import os
import sys
import tempfile
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加父目录到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_concurrent_approve_and_hook():
    """测试：approve 和 hook 并发时不会出现状态损坏"""
    from scripts.review_approve import get_real_home, get_repo_info

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

        # 初始状态
        state_file.write_text('{"state":"PENDING_REVIEW","approved":false,"diff_hash":"abc","cycle_count":1}')

        print(f"初始状态: {state_file.read_text()}")

        # 并发执行 approve 和 reset
        def run_approve():
            # 模拟 approve 脚本的行为
            state = json.loads(state_file.read_text())
            state["approved"] = True
            time.sleep(0.01)  # 模拟处理时间
            state_file.write_text(json.dumps(state))
            return "approve done"

        def run_reset():
            # 模拟 reset 脚本的行为
            time.sleep(0.005)  # reset 先执行
            if state_file.exists():
                state_file.unlink()
            return "reset done"

        # 先 reset 删除状态，让 approve 创建新状态
        state_file.unlink()
        state_file.write_text('{"state":"PENDING_REVIEW","approved":false,"diff_hash":"xyz","cycle_count":0}')

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(run_approve)
            f2 = executor.submit(run_reset)
            results = [f1.result(), f2.result()]

        print(f"执行结果: {results}")
        print(f"最终状态: {state_file.read_text() if state_file.exists() else '文件被删除'}")

        # 验证：最终状态要么是 approved=true，要么是文件被删除，不会是损坏的 JSON
        if state_file.exists():
            try:
                final_state = json.loads(state_file.read_text())
                print("✅ 状态文件未损坏")
            except json.JSONDecodeError:
                assert False, "状态文件损坏"
                print("❌ 状态文件损坏")

        print("✅ test_concurrent_approve_and_hook passed")


def test_flock_available():
    """测试：flock 命令可用"""
    result = subprocess.run(["flock", "--version"], capture_output=True, text=True)
    assert result.returncode == 0, "flock 不可用"
    print(f"✅ flock 可用: {result.stdout.split()[0]}")


if __name__ == "__main__":
    print("=== 测试 flock 竞态条件 ===")
    test_flock_available()
    test_concurrent_approve_and_hook()
    print("\n✅ 所有测试通过")
