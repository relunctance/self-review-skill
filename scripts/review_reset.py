#!/usr/bin/env python3
"""
self-review-skill: review_reset.py

功能：重置审查状态，清除指定仓库/分支的 state.json

用法：
    python3 scripts/review_reset.py
    python3 scripts/review_reset.py --cwd /path/to/repo
    echo '{"cwd":"/path/to/repo"}' | python3 scripts/review_reset.py
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
    format='[review-reset] %(levelname)s: %(message)s'
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

    Returns:
        (repo_path, branch, repo_hash, branch_hash)

    Raises:
        SystemExit: 不在 git 仓库中时退出
    """
    git_cwd = cwd if cwd else os.getcwd()

    try:
        repo_path = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=git_cwd
        ).strip()

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
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"不在 git 仓库中: {e}")
        sys.exit(1)


def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description="self-review-skill reset 脚本")
    parser.add_argument("--cwd", help="指定工作目录")
    args = parser.parse_args()
    return args.cwd


def try_read_cwd_from_stdin() -> str | None:
    """尝试从 stdin 读取 JSON payload 并提取 cwd 字段"""
    try:
        if sys.stdin.isatty():
            return None

        stdin_data = sys.stdin.read().strip()
        if not stdin_data:
            return None

        payload = json.loads(stdin_data)
        cwd = payload.get("cwd", "")
        if cwd and os.path.isdir(cwd):
            return cwd
        return None
    except (json.JSONDecodeError, OSError):
        return None


def reset_review_state(cwd: str) -> bool:
    """重置审查状态

    Args:
        cwd: 仓库路径

    Returns:
        True 如果状态被重置，False 如果没有状态需要重置

    Raises:
        SystemExit: cwd 不存在或非 git 仓库时退出
    """
    real_home = get_real_home()

    # 获取仓库信息
    repo_path, branch, repo_hash, branch_hash = get_repo_info(cwd)

    # 构建状态文件路径
    state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
    state_file = state_dir / "state.json"

    if not state_file.exists():
        logger.info(f"无状态需要重置: {repo_path} ({branch})")
        print(f"ℹ️ 无状态需要重置: {repo_path} ({branch})")
        return False

    # 读取旧状态
    try:
        old_state = json.loads(state_file.read_text())
        old_state_str = json.dumps(old_state, ensure_ascii=False)
    except (json.JSONDecodeError, OSError):
        old_state_str = "(损坏的 JSON)"

    # 删除状态文件
    state_file.unlink()
    logger.info(f"已重置状态: {repo_path} ({branch}), 旧状态: {old_state_str}")
    print(f"✅ 已重置状态: {repo_path} ({branch})")

    # 尝试删除空的父目录
    try:
        state_dir.rmdir()
    except OSError:
        pass  # 目录非空，忽略

    return True


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
            else:
                # 使用当前目录
                cwd = os.getcwd()

        # 验证 cwd 是否存在
        if not os.path.isdir(cwd):
            logger.error(f"工作目录不存在: {cwd}")
            sys.exit(1)

        # 重置状态
        reset_review_state(cwd)

    except Exception as e:
        logger.error(f"reset 失败: {e}")
        raise


if __name__ == "__main__":
    main()
