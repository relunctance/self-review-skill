#!/usr/bin/env python3
"""
self-review-skill: approve 脚本

功能：批准当前待审查的改动。

调用方式：
    python3 /path/to/review_approve.py

或者传入 JSON payload（从 stdin）获取 cwd：
    echo '{"cwd":"/path/to/repo"}' | python3 /path/to/review_approve.py
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


def get_repo_info(cwd: str | None = None) -> tuple[str, str, str, str]:
    """获取仓库和分支信息

    Args:
        cwd: 如果提供，在此目录下执行 git 命令

    分支检测逻辑需与 hooks/self-review-hook.sh 保持一致：
    - 使用 git symbolic-ref --short HEAD
    - 正常分支：返回分支名（如 master）
    - detached HEAD 或无 commits：返回 detached

    Raises:
        SystemExit: cwd 指定但目录不存在时退出
    """
    # cwd 必须存在，不允许降级
    if cwd is not None and not os.path.isdir(cwd):
        logger.error(f"指定的工作目录不存在: {cwd}")
        sys.exit(1)
    git_cwd = cwd if cwd else os.getcwd()

    try:
        repo_path = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=git_cwd
        ).strip()

        # 使用与 hook 相同的分支检测逻辑
        # 使用 git symbolic-ref --short HEAD 获取分支名
        # - 正常分支：返回分支名（如 master）
        # - detached HEAD 或无 commits：失败
        branch_result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            cwd=git_cwd
        )
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            branch = branch_result.stdout.strip()
        else:
            branch = "detached"

        repo_hash = hashlib.md5(repo_path.encode()).hexdigest()[:8]
        branch_hash = hashlib.md5(branch.encode()).hexdigest()[:8]
        return repo_path, branch, repo_hash, branch_hash
    except subprocess.CalledProcessError as e:
        logger.error(f"不在 git 仓库中: {e}")
        sys.exit(1)


def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description="self-review-skill approve 脚本")
    parser.add_argument("--cwd", help="指定工作目录")
    args = parser.parse_args()
    return args.cwd


def try_read_cwd_from_stdin() -> str | None:
    """尝试从 stdin 读取 JSON payload 并提取 cwd 字段"""
    try:
        # 检查 stdin 是否有数据
        if sys.stdin.isatty():
            return None

        # 读取 stdin
        stdin_data = sys.stdin.read().strip()
        if not stdin_data:
            return None

        payload = json.loads(stdin_data)
        cwd = payload.get("cwd", "")
        # cwd 必须存在，不允许降级
        if cwd and not os.path.isdir(cwd):
            logger.error(f"stdin payload 中指定的工作目录不存在: {cwd}")
            return None
        if cwd:
            return cwd
        return None
    except (json.JSONDecodeError, OSError):
        return None


def main():
    try:
        # 获取真实 home
        real_home = get_real_home()

        # 获取命令行参数
        cli_cwd = parse_args()
        if cli_cwd:
            logger.info(f"从命令行参数获取 cwd: {cli_cwd}")
            if not os.path.isdir(cli_cwd):
                logger.error(f"指定的工作目录不存在: {cli_cwd}")
                sys.exit(1)
            cwd = cli_cwd
        else:
            # 尝试从 stdin 获取 cwd
            cwd = try_read_cwd_from_stdin()
            if cwd:
                logger.info(f"从 stdin payload 获取 cwd: {cwd}")

        # 获取仓库和分支信息
        repo_path, branch, repo_hash, branch_hash = get_repo_info(cwd)

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
