#!/usr/bin/env bash
# self-review-skill: Hook 脚本单元测试

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
HOOK_SCRIPT="$SKILL_DIR/hooks/self-review-hook.sh"

# 获取真实 home
REAL_HOME=$(getent passwd "$(whoami)" | cut -d: -f6)

echo "=== self-review-skill Hook 脚本测试 ==="
echo ""

test_blocks_non_git_commands() {
    echo "测试：非 git commit 命令应该跳过"
    payload='{"tool_input":{"command":"ls -la"}}'
    result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")
    if [ "$result" = "{}" ]; then
        echo "✅ PASSED: 非 git 命令被正确跳过"
    else
        echo "❌ FAILED: 期望 {}，实际 $result"
        return 1
    fi
}

test_allows_empty_staged() {
    echo ""
    echo "测试：无 staged 内容应该跳过"

    # 创建临时 git 仓库
    TESTDIR=$(mktemp -d)
    cd "$TESTDIR"
    git init -q

    # 无 staged 内容
    payload='{"tool_input":{"command":"git commit -m \"empty\""}}'
    result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")

    # 清理
    rm -rf "$TESTDIR"

    if [ "$result" = "{}" ]; then
        echo "✅ PASSED: 无 staged 内容被正确跳过"
    else
        echo "❌ FAILED: 期望 {}，实际 $result"
        return 1
    fi
}

test_blocks_new_commit() {
    echo ""
    echo "测试：有 staged 内容的 commit 应该被 block"

    # 创建临时 git 仓库
    TESTDIR=$(mktemp -d)
    cd "$TESTDIR"
    git init -q
    echo "hello" > file.txt
    git add file.txt

    payload='{"tool_input":{"command":"git commit -m \"first\""}}'
    result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")

    # 清理
    rm -rf "$TESTDIR"
    # 清理测试状态
    rm -rf "$REAL_HOME/.hermes/review-states/*" 2>/dev/null || true

    action=$(echo "$result" | jq -r '.action // empty' 2>/dev/null || echo "")
    if [ "$action" = "block" ]; then
        echo "✅ PASSED: 新 commit 被正确 block"
    else
        echo "❌ FAILED: 期望 block，实际 $result"
        return 1
    fi
}

test_hook_log_created() {
    echo ""
    echo "测试：Hook 触发后应该创建日志"

    LOG_FILE="$REAL_HOME/.hermes/logs/pre-tool-hook.log"
    rm -f "$LOG_FILE" 2>/dev/null || true

    # 创建临时 git 仓库
    TESTDIR=$(mktemp -d)
    cd "$TESTDIR"
    git init -q
    echo "hello" > file.txt
    git add file.txt

    payload='{"tool_input":{"command":"git commit -m \"log test\""}}'
    echo "$payload" | bash "$HOOK_SCRIPT" >/dev/null 2>&1 || true

    # 清理
    rm -rf "$TESTDIR"
    rm -rf "$REAL_HOME/.hermes/review-states/*" 2>/dev/null || true

    if [ -f "$LOG_FILE" ]; then
        echo "✅ PASSED: Hook 日志已创建"
    else
        echo "❌ FAILED: Hook 日志未创建"
        return 1
    fi
}

# 运行测试
failed=0

test_blocks_non_git_commands || failed=$((failed+1))
test_allows_empty_staged || failed=$((failed+1))
test_blocks_new_commit || failed=$((failed+1))
test_hook_log_created || failed=$((failed+1))

echo ""
echo "=== 测试结果 ==="
if [ $failed -eq 0 ]; then
    echo "✅ 全部通过 ($failed failed)"
    exit 0
else
    echo "❌ $failed 个测试失败"
    exit 1
fi
