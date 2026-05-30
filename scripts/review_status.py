#!/usr/bin/env python3
"""
self-review-skill: 状态查询脚本

用法：
    python3 scripts/review_status.py
    python3 scripts/review_status.py --json

退出码：
    0 - 成功
    1 - 不在 git 仓库
    2 - 其他错误
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='[review-status] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def get_real_home() -> str:
    """获取真实 home 目录"""
    return subprocess.check_output(
        ["getent", "passwd", os.environ.get("USER", "") or subprocess.check_output(["whoami"]).decode().strip()],
        text=True
    ).split(":")[5]


def get_repo_info(cwd: str = None) -> tuple:
    """获取仓库路径和分支名"""
    try:
        repo_path = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            cwd=cwd
        ).decode().strip()

        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            cwd=cwd
        ).decode().strip() or "detached"

        return repo_path, branch
    except subprocess.CalledProcessError as e:
        logger.error(f"不在 git 仓库中: {e}")
        return None, None


def compute_hashes(repo_path: str, branch: str) -> tuple:
    """计算 repo 和 branch 的 hash"""
    repo_hash = hashlib.md5(repo_path.encode()).hexdigest()[:8]
    branch_hash = hashlib.md5(branch.encode()).hexdigest()[:8]
    return repo_hash, branch_hash


def read_state_file(state_file: Path) -> Optional[dict]:
    """读取状态文件"""
    if not state_file.exists():
        return None

    try:
        return json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"状态文件损坏: {e}")
        return {"state": "CORRUPTED", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="查询 self-review-skill 状态")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--cwd", default=None, help="指定仓库路径")
    args = parser.parse_args()

    # 获取仓库信息
    cwd = args.cwd or os.getcwd()
    repo_path, branch = get_repo_info(cwd)

    if repo_path is None:
        error_result = {
            "success": False,
            "error": "NOT_IN_GIT_REPO",
            "message": "当前目录不是 git 仓库"
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 计算 hash
    repo_hash, branch_hash = compute_hashes(repo_path, branch)

    # 读取状态文件
    real_home = get_real_home()
    state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
    state_file = state_dir / "state.json"
    context_file = state_dir / "context.json"

    state = read_state_file(state_file)

    # 构建结果
    result = {
        "success": True,
        "repo": repo_path,
        "branch": branch,
        "state": state.get("state") if state else "IDLE",
        "approved": state.get("approved", False) if state else False,
        "diff_hash": state.get("diff_hash", "") if state else "",
        "cycle_count": state.get("cycle_count", 0) if state else 0,
        "context_file": str(context_file) if context_file.exists() else None,
        "last_updated": datetime.fromtimestamp(state_file.stat().st_mtime).isoformat()
                       if state_file.exists() else None
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 友好文本输出
        print(f"=== self-review-skill 状态 ===")
        print(f"仓库: {result['repo']}")
        print(f"分支: {result['branch']}")
        print(f"状态: {result['state']}")
        print(f"已批准: {result['approved']}")
        print(f"Diff Hash: {result['diff_hash'] or '(无)'}")
        print(f"循环计数: {result['cycle_count']}")
        print(f"上下文文件: {result['context_file'] or '(无)'}")
        print(f"最后更新: {result['last_updated'] or '(无)'}")

        if not state:
            print("\n状态: IDLE (无待审查改动)")

    sys.exit(0)


if __name__ == "__main__":
    main()
