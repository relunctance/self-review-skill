#!/usr/bin/env bash
# self-review-skill: Hook 脚本
# 功能：拦截 git commit，强制审查改动
#
# 用法：作为 Hermes pre_tool_call hook 使用
# 配置：hermes hooks add --event pre_tool_call --matcher terminal --command "path/to/self-review-hook.sh"

set -euo pipefail

# === 获取真实 home（避免 Hermes profile 篡改 Path.home()）===
REAL_HOME=$(getent passwd "$(whoami)" | cut -d: -f6)

# === Hook 触发日志 ===
LOG_DIR="$REAL_HOME/.hermes/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pre-tool-hook.log"

log_hook() {
    local level="$1"
    local cmd="$2"
    local action="$3"
    local message="${4:-}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] cmd='$cmd' action='$action' $message" >> "$LOG_FILE"
}

# === 解析命令 ===
payload="$(cat -)"
cmd=$(echo "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# 只处理 git commit 命令
if [ -z "$cmd" ] || ! echo "$cmd" | grep -qE '^git commit'; then
    log_hook "INFO" "$cmd" "skip" "not a git commit"
    printf '{}\n'
    exit 0
fi

log_hook "INFO" "$cmd" "triggered" "hook triggered"

# === 从 payload 获取工作目录 ===
# Hermes 在 payload 中提供了 cwd 字段，优先使用它
# 格式：{"tool_input":{"command":"..."}, "cwd":"/path/to/repo", ...}
PAYLOAD_CWD=$(echo "$payload" | jq -r '.cwd // empty' 2>/dev/null || echo "")

# === 检查是否是 git 仓库 ===
# 优先使用 payload 中的 cwd，否则使用当前目录
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then
    REPO_PATH=$(git -C "$PAYLOAD_CWD" rev-parse --show-toplevel 2>/dev/null || echo "unknown")
else
    # 降级：使用当前目录
    REPO_PATH=$(git -C . rev-parse --show-toplevel 2>/dev/null || echo "unknown")
    PAYLOAD_CWD="."  # 降级时使用当前目录
fi

if [ "$REPO_PATH" = "unknown" ]; then
    log_hook "WARN" "$cmd" "skip" "not a git repository"
    printf '{}\n'
    exit 0
fi

# === 隔离：仓库 + 分支 + 锁 ===
# 注意：git 命令输出可能包含换行符，必须用 echo -n 计算 hash
REPO_HASH=$(echo -n "$REPO_PATH" | md5sum | cut -d' ' -f1 | cut -c1-8)
# 使用 git -C "$PAYLOAD_CWD" 获取分支名
# - 有 commit 后：返回分支名（如 master, main）
# - 无 commit 时：返回空字符串，此时用 "detached"
BRANCH=$(git -C "$PAYLOAD_CWD" branch --show-current 2>/dev/null || echo "detached")
[ -z "$BRANCH" ] && BRANCH="detached"
# 注意：BRANCH 变量可能包含换行符，必须用 echo -n 计算 hash
BRANCH_HASH=$(echo -n "$BRANCH" | md5sum | cut -d' ' -f1 | cut -c1-8)
STATE_DIR="$REAL_HOME/.hermes/review-states/$REPO_HASH/$BRANCH_HASH"
mkdir -p "$STATE_DIR"

LOCK_FILE="$STATE_DIR/.lock"
exec 3>"$LOCK_FILE"

# 获取锁，超时 30 秒
flock -w 30 3 || {
    log_hook "WARN" "$cmd" "blocked" "another commit in review"
    printf '{"action":"block","message":"另一个 commit 正在审查中，请稍后再试"}\n'
    exit 0
}

# === 检查是否有 staged 内容 ===
STAGED=$(git -C "$PAYLOAD_CWD" diff --cached --stat 2>/dev/null)
if [ -z "$STAGED" ]; then
    # 无 staged 内容，跳过检查
    log_hook "INFO" "$cmd" "skip" "no staged content"
    printf '{}\n'
    exit 0
fi

log_hook "INFO" "$cmd" "review_required" "staged content detected"

# === 状态机逻辑 ===
STATE_FILE="$STATE_DIR/state.json"
CONTEXT_FILE="$STATE_DIR/context.json"

STATE="{}"
[ -f "$STATE_FILE" ] && STATE=$(cat "$STATE_FILE")
STATE=${STATE:-'{"state":"IDLE","approved":false,"cycle_count":0}'}

CURRENT_STATE=$(echo "$STATE" | jq -r '.state')
APPROVED=$(echo "$STATE" | jq -r '.approved')
CYCLE_COUNT=$(echo "$STATE" | jq -r '.cycle_count // 0')

DIFF=$(git -C "$PAYLOAD_CWD" diff --cached --stat 2>/dev/null)
# 注意：git diff 输出可能包含换行符，必须用 echo -n 计算 hash
DIFF_HASH=$(echo -n "$DIFF" | md5sum | cut -d' ' -f1)
SAVED_HASH=$(echo "$STATE" | jq -r '.diff_hash // ""')

log_hook "DEBUG" "$cmd" "state_check" "current_state=$CURRENT_STATE approved=$APPROVED cycle=$CYCLE_COUNT diff_hash=$DIFF_HASH saved_hash=$SAVED_HASH"

# === 循环检测：连续 3 次 diff 相同，强制放行 ===
if [ "$DIFF_HASH" = "$SAVED_HASH" ] && [ "$CYCLE_COUNT" -ge 2 ]; then
    log_hook "INFO" "$cmd" "force_allow" "cycle_count=$CYCLE_COUNT, forcing allow"
    # 方案B：保留 diff_hash，设置 approved=true，避免下次相同 diff 重新计数
    echo "{\"state\":\"IDLE\",\"approved\":true,\"diff_hash\":\"$DIFF_HASH\",\"cycle_count\":0}" > "$STATE_FILE"
    printf '{}\n'
    exit 0
fi

# diff 有变化，重置状态（新修改）
if [ "$DIFF_HASH" != "$SAVED_HASH" ]; then
    echo "$DIFF" > "$CONTEXT_FILE"
    # diff 变化时重置 cycle_count（新修改，不需要累加）
    echo "{\"state\":\"PENDING_REVIEW\",\"approved\":false,\"diff_hash\":\"$DIFF_HASH\",\"cycle_count\":0}" > "$STATE_FILE"
    log_hook "INFO" "$cmd" "blocked" "diff changed, new review"
    MSG="待审查改动已写入 $CONTEXT_FILE\n审查完成后，运行：python3 $REAL_HOME/self-review-skill/scripts/review_approve.py 2>/dev/null || python3 ~/self-review-skill/scripts/review_approve.py"
    printf '{"action":"block","message":"%s"}\n' "$MSG"
    exit 0
fi

# diff 无变化，检查 approved
if [ "$CURRENT_STATE" = "PENDING_REVIEW" ] && [ "$APPROVED" = "false" ]; then
    # 循环检测：diff 无变化但未 approved，每次都增加 cycle_count
    NEW_CYCLE=$((CYCLE_COUNT + 1))
    echo "{\"state\":\"PENDING_REVIEW\",\"approved\":false,\"diff_hash\":\"$DIFF_HASH\",\"cycle_count\":$NEW_CYCLE}" > "$STATE_FILE"
    log_hook "WARN" "$cmd" "blocked" "pending review, not approved, cycle=$NEW_CYCLE"
    if [ "$NEW_CYCLE" -ge 2 ]; then
        log_hook "INFO" "$cmd" "force_allow" "cycle_count=$NEW_CYCLE >= 2, forcing allow"
        # 方案B：保留 diff_hash，设置 approved=true，避免下次相同 diff 重新计数
        echo "{\"state\":\"IDLE\",\"approved\":true,\"diff_hash\":\"$DIFF_HASH\",\"cycle_count\":0}" > "$STATE_FILE"
        printf '{}\n'
        exit 0
    fi
    MSG="请先运行 approve：python3 $REAL_HOME/self-review-skill/scripts/review_approve.py 2>/dev/null || python3 ~/self-review-skill/scripts/review_approve.py"
    printf '{"action":"block","message":"%s"}\n' "$MSG"
    exit 0
fi

# 已 approve，允许通过
log_hook "INFO" "$cmd" "allowed" "approved=true, diff unchanged"
echo '{"state":"IDLE","approved":false,"diff_hash":"","cycle_count":0}' > "$STATE_FILE"
printf '{}\n'

# === 清理 7 天前的状态文件 ===
find "$REAL_HOME/.hermes/review-states" -type f -name "state.json" -mtime +7 -delete 2>/dev/null || true
find "$REAL_HOME/.hermes/review-states" -type d -empty -delete 2>/dev/null || true
