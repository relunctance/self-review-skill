#!/usr/bin/env python3
"""
self-review-skill: approve 脚本

功能：批准当前待审查的改动。

Agent 调用方式（通过 execute_code 工具）：
    python3 /path/to/review_approve.py

或者手动在终端执行：
    python3 /path/to/review_approve.py
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[review-approve] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def get_real_home() -> str:
    """获取真实 home 目录，避免 Hermes profile 篡改 Path.home()"""
    user = os.environ.get("USER") or subprocess.check_output(
        ["whoami"], text=True
    ).strip()
    return subprocess.check_output(
        ["getent", "passwd", user], text=True
    ).split(":")[5]


def get_repo_info() -> tuple[str, str, str, str]:
    """获取仓库和分支信息"""
    try:
        repo_path = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip() or "detached"
        repo_hash = hashlib.md5(repo_path.encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(branch.encode()).hexdigest()[:8]
        return repo_path, branch, repo_hash, branch_hash
    except subprocess.CalledProcessError as e:
        logger.error(f"不在 git 仓库中: {e}")
        sys.exit(1)


def main():
    try:
        # 获取真实 home
        real_home = get_real_home()

        # 获取仓库和分支信息
        repo_path, branch, repo_hash, branch_hash = get_repo_info()

        # 构建状态文件路径
        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        # 读取当前状态
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                logger.info(f"当前状态: {state.get('state')}, approved: {state.get('approved')}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"状态文件损坏，使用新状态: {e}")
                state = {"state": "PENDING_REVIEW", "approved": True, "diff_hash": "", "cycle_count": 0}
        else:
            state = {"state": "PENDING_REVIEW", "approved": True, "diff_hash": "", "cycle_count": 0}

        # 更新 approved 标志
        state["approved"] = True
        state["state"] = "PENDING_REVIEW"  # 保持 PENDING_REVIEW，等待 diff 无变化时允许通过

        # 写入状态文件
        state_file.write_text(json.dumps(state))

        print(f"✅ Approved: {repo_path} ({branch})")
        print(f"📁 State file: {state_file}")

    except Exception as e:
        logger.error(f"approve 失败: {e}")
        raise


if __name__ == "__main__":
    main()
