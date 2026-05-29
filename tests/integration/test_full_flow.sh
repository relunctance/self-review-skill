#!/usr/bin/env bash
# self-review-skill: 完整流程集成测试

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 从 tests/integration/ 向上两级到达项目根目录
SKILL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK_SCRIPT="$SKILL_DIR/hooks/self-review-hook.sh"
APPROVE_SCRIPT="$SKILL_DIR/scripts/review_approve.py"

# 获取真实 home
REAL_HOME=$(getent passwd "$(whoami)" | cut -d: -f6)

echo "=== self-review-skill 完整流程集成测试 ==="
echo ""

# 创建临时 git 仓库
TESTDIR=$(mktemp -d)
cd "$TESTDIR"
git init -q
# 设置默认分支为 main
git config init.defaultBranch main 2>/dev/null || true
echo "hello" > file.txt
git add file.txt

REPO_HASH=$(echo "$TESTDIR" | md5sum | cut -c1-8)
BRANCH_HASH=$(echo "master" | md5sum | cut -c1-8)
STATE_DIR="$REAL_HOME/.hermes/review-states/$REPO_HASH/$BRANCH_HASH"
rm -rf "$STATE_DIR" 2>/dev/null || true

echo "测试目录: $TESTDIR"
echo ""

# 1. First commit blocked (payload 包含 cwd)
echo "步骤 1: 测试首次 commit 应该被 block"
payload="{\"tool_input\":{\"command\":\"git commit -m \\\"first\\\"\"},\"cwd\":\"$TESTDIR\"}"
result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")
action=$(echo "$result" | jq -r '.action // empty' 2>/dev/null || echo "")

if [ "$action" = "block" ]; then
    echo "✅ PASSED: 首次 commit 被 block"
else
    echo "❌ FAILED: 期望 block，实际 $result"
    rm -rf "$TESTDIR" "$STATE_DIR"
    exit 1
fi

# 2. Approve (通过 stdin 传递 cwd)
echo ""
echo "步骤 2: 测试 approve 脚本"
cd "$TESTDIR"
# 通过 stdin 传递 cwd 给 approve 脚本
echo "{\"cwd\":\"$TESTDIR\"}" | python3 "$APPROVE_SCRIPT" >/dev/null 2>&1
echo "✅ approve 脚本执行成功"

# 3. Second commit allowed (same diff, payload 包含 cwd)
echo ""
echo "步骤 3: 测试相同 diff 的第二次 commit 应该允许"
payload="{\"tool_input\":{\"command\":\"git commit -m \\\"first\\\"\"},\"cwd\":\"$TESTDIR\"}"
result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")
action=$(echo "$result" | jq -r '.action // empty' 2>/dev/null || echo "")

if [ -z "$action" ] || [ "$action" = "null" ]; then
    echo "✅ PASSED: 相同 diff 的 commit 被允许"
else
    echo "❌ FAILED: 期望 allow，实际 $result"
    rm -rf "$TESTDIR" "$STATE_DIR"
    exit 1
fi

# 4. Test diff change resets approved
echo ""
echo "步骤 4: 测试 diff 变化应该重置 approved"

# 添加新改动
echo "world" >> file.txt
git add file.txt

payload="{\"tool_input\":{\"command\":\"git commit -m \\\"second\\\"\"},\"cwd\":\"$TESTDIR\"}"
result=$(echo "$payload" | bash "$HOOK_SCRIPT" 2>/dev/null || echo "{}")
action=$(echo "$result" | jq -r '.action // empty' 2>/dev/null || echo "")

if [ "$action" = "block" ]; then
    echo "✅ PASSED: diff 变化后被 block"
else
    echo "❌ FAILED: 期望 block，实际 $result"
    rm -rf "$TESTDIR" "$STATE_DIR"
    exit 1
fi

# 清理
rm -rf "$TESTDIR" "$STATE_DIR"
rm -rf "$REAL_HOME/.hermes/review-states/*" 2>/dev/null || true

echo ""
echo "=== 集成测试全部通过 ==="
