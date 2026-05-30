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
import fcntl
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

    Returns:
        (repo_path, branch, repo_hash, branch_hash)

    Raises:
        SystemExit: cwd 指定但目录不存在时退出
    """
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
    parser = argparse.ArgumentParser(description="self-review-skill approve 脚本")
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
        if cwd and not os.path.isdir(cwd):
            logger.error(f"stdin payload 中指定的工作目录不存在: {cwd}")
            return None
        if cwd:
            return cwd
        return None
    except (json.JSONDecodeError, OSError):
        return None


def read_state_with_lock(state_file: Path, timeout: int = 30) -> dict | None:
    """读取状态文件，使用 flock 保护（与 hook 行为一致）

    Args:
        state_file: 状态文件路径
        timeout: flock 超时秒数

    Returns:
        状态字典，如果文件不存在返回 None

    Raises:
        SystemExit: 获取锁失败时退出
    """
    if not state_file.exists():
        return None

    lock_file = state_file.parent / ".lock"
    lock_file.touch(exist_ok=True)

    try:
        with open(lock_file, "w") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            try:
                if state_file.exists():
                    with open(state_file) as f:
                        return json.load(f)
                return None
            finally:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
    except (IOError, OSError) as e:
        if "Resource temporarily unavailable" in str(e) or "Lock wait timeout" in str(e):
            logger.error(f"获取锁超时（{timeout}秒）：另一个进程正在操作状态文件")
            sys.exit(1)
        raise


def write_state_with_lock(state_file: Path, state: dict, timeout: int = 30) -> None:
    """写入状态文件，使用 flock 保护（与 hook 行为一致）

    Args:
        state_file: 状态文件路径
        state: 要写入的状态字典
        timeout: flock 超时秒数

    Raises:
        SystemExit: 获取锁失败时退出
    """
    lock_file = state_file.parent / ".lock"
    lock_file.touch(exist_ok=True)

    try:
        with open(lock_file, "w") as lock_fd:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            try:
                state_file.write_text(json.dumps(state))
            finally:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
    except (IOError, OSError) as e:
        if "Resource temporarily unavailable" in str(e) or "Lock wait timeout" in str(e):
            logger.error(f"获取锁超时（{timeout}秒）：另一个进程正在操作状态文件")
            sys.exit(1)
        raise


def main():
    try:
        real_home = get_real_home()

        cli_cwd = parse_args()
        if cli_cwd:
            logger.info(f"从命令行参数获取 cwd: {cli_cwd}")
            if not os.path.isdir(cli_cwd):
                logger.error(f"指定的工作目录不存在: {cli_cwd}")
                sys.exit(1)
            cwd = cli_cwd
        else:
            cwd = try_read_cwd_from_stdin()
            if cwd:
                logger.info(f"从 stdin payload 获取 cwd: {cwd}")

        repo_path, branch, repo_hash, branch_hash = get_repo_info(cwd)

        state_dir = Path(real_home) / ".hermes" / "review-states" / repo_hash / branch_hash
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "state.json"

        # 读取当前状态用于日志
        old_state = read_state_with_lock(state_file)
        if old_state:
            logger.info(f"当前状态: {old_state.get('state')}, approved: {old_state.get('approved')}")
        else:
            logger.info("无现有状态，创建新状态")

        # 更新 approved 标志
        state = {"state": "PENDING_REVIEW", "approved": True, "diff_hash": "", "cycle_count": 0}

        # 使用 flock 写入状态文件
        write_state_with_lock(state_file, state)

        print(f"✅ Approved: {repo_path} ({branch})")
        print(f"📁 State file: {state_file}")

    except Exception as e:
        logger.error(f"approve 失败: {e}")
        raise


if __name__ == "__main__":
    main()
