---
name: self-review-skill
description: 每次 commit 前强制审查改动，减少 bug 率
version: "1.0.0"
author: relunctance
license: MIT
category: development
tags:
  - hermes
  - hook
  - git
  - quality
  - commit-review
metadata:
  hermes:
    platforms:
      hermes: true
    related_skills: [git-standards-skill]
---

# self-review-skill

> 每次 commit 前强制审查改动，确保无 bug 才提交

## 设计原则

**能用 SOP + LLM 解决的，坚决不加代码。代码越多 bug 越多。**

| 该用代码 | 该用 SOP / LLM |
|---------|----------------|
| 精确计算（diff hash、状态文件读写） | 决策判断（是否有 bug、是否通过审查） |
| 文件 I/O（确定性读写） | 工作流编排（hook 拦截 → 审查 → approve → 提交） |

**操作顺序**：
1. Hook 拦截 git commit
2. LLM 读取 diff 内容审查
3. 发现 bug → 修复 → 再次审查
4. 无 bug → 执行 approve 脚本
5. 再次 commit → 通过

---

## 核心机制

### 状态机

```
IDLE
  │
  │ Agent 执行 git commit
  ▼
PENDING_REVIEW
  │
  │ diff 有变化？
  │ ├─ 是：更新临时文件，block + 提示
  │ └─ 否（diff 无变化）：检查 approved 标志
  │
  │         approved = true?
  │           ├─ 是 → IDLE（允许通过）
  │           └─ 否 → 继续 block
  │
  ▼
Agent 调用 approve 脚本
  │
  │ approved = true
  │ diff 无变化？
  │   ├─ 是 → IDLE（允许通过）
  │   └─ 否 → 继续 PENDING_REVIEW
```

### Shell Hook 协议

**stdin — hook 收到的 payload**：
```json
{
  "hook_event_name": "pre_tool_call",
  "tool_name": "terminal",
  "tool_input": {"command": "git commit -m '...'"},
  "session_id": "sess_abc123",
  "cwd": "/home/user/project",
  "extra": {}
}
```

**stdout — hook 的响应**：
```jsonc
// Block
{"action": "block", "message": "请审查改动"}
// 放行
{}
```

---

## 触发条件

- 小步迭代开发，每次 commit 前审查
- 需要强制 self-review 的场景
- 多 Agent 并行开发，需要统一提交规范

---

## 安装流程

### 方式1：手动安装

```bash
# 1. Clone skill repo
git clone https://github.com/relunctance/self-review-skill.git ~/self-review-skill

# 2. Make scripts executable
chmod +x ~/self-review-skill/hooks/self-review-hook.sh
chmod +x ~/self-review-skill/scripts/review_approve.py

# 3. Register hook via hermes CLI
hermes hooks add --event pre_tool_call \
  --matcher terminal \
  --command "~/self-review-skill/hooks/self-review-hook.sh"

# 4. Accept the hook when prompted (or use --accept-hooks flag)
```

### 方式2：通过 skill-created 自动安装

```bash
hermes chat -s self-review-skill
```

---

## 使用方法

### Agent 工作流

```
Agent: 修改代码（Write/Edit）
    ↓
Agent: git add file.py
    ↓
Agent: git commit -m "..."
    │
    ├─ Hook: 状态=PENDING_REVIEW
    │       diff 写入 ~/.hermes/review-states/{hash}/context.json
    │       返回 block + "请审查，完成后运行 approve 脚本"
    │
    ▼
Agent: 读取 context.json 审查改动
Agent: 审查改动
    │
    ├─ 发现 bug
    │   ↓
    │   Agent: 修复 bug
    │   Agent: git add + git commit（再次触发 hook）
    │   ↓
    │   Hook: diff 有变化 → 更新临时文件 + block
    │   （循环，直到无 bug）
    │
    └─ 无 bug
        ↓
Agent: execute_code(approve 脚本)
Agent: git commit -m "..."
    │
    └─ Hook: approved=true, diff 无变化 → 允许通过
```

### Agent 调用 approve 的方式

审查完成后，通过 `execute_code` 工具执行：

```python
import subprocess
result = subprocess.run(
    ["python3", "~/self-review-skill/scripts/review_approve.py"],
    capture_output=True, text=True
)
print(result.stdout)
```

---

## 文件结构

```
self-review-skill/
├── SKILL.md                    # 本文件
├── README.md                   # 用户文档
├── LICENSE                    # MIT License
├── hooks/
│   └── self-review-hook.sh    # 核心 hook 脚本
├── scripts/
│   └── review_approve.py      # approve 脚本
├── tests/
│   ├── unit/
│   │   ├── test_state_machine.py
│   │   └── test_hook_script.sh
│   └── integration/
│       └── test_full_flow.sh
└── learns/
    └── README.md              # 踩坑记录
```

---

## 测试套件

### 单元测试

```bash
# 状态机测试
python3 -m pytest tests/unit/test_state_machine.py -v

# Hook 脚本测试
bash tests/unit/test_hook_script.sh
```

### 集成测试

```bash
# 完整流程测试
bash tests/integration/test_full_flow.sh
```

### 回归测试

```bash
cd /home/gql/repos/self-review-skill
python3 -m pytest tests/unit/ -v
bash tests/unit/test_hook_script.sh
bash tests/integration/test_full_flow.sh
```

---

## 临时文件

| 文件 | 用途 |
|------|------|
| `~/.hermes/review-states/{repo_hash}/{branch_hash}/state.json` | 状态机状态（含 cycle_count） |
| `~/.hermes/review-states/{repo_hash}/{branch_hash}/context.json` | 待审查的 diff 内容 |
| `~/.hermes/review-states/{repo_hash}/{branch_hash}/.lock` | 锁文件 |
| `~/.hermes/logs/pre-tool-hook.log` | Hook 触发日志 |

---

## 多仓库 + 分支隔离 + 锁

```bash
# 按仓库 + 分支隔离
REPO_HASH=$(echo "$REPO_PATH" | md5sum | cut -c1-8)
BRANCH_HASH=$(echo "$BRANCH" | md5sum | cut -c1-8)

# 加锁（同一分支串行）
LOCK_FILE="$STATE_DIR/.lock"
flock -w 30 3 || {
    printf '{"action":"block","message":"另一个 commit 正在审查中，请稍后再试"}'
    exit 0
}
```

---

## 循环检测

连续 3 次 diff 相同，强制放行避免死循环：

```bash
if [ "$DIFF_HASH" = "$SAVED_HASH" ] && [ "$CYCLE_COUNT" -ge 3 ]; then
    echo '{"state":"IDLE","approved":false,"diff_hash":"","cycle_count":0}' > "$STATE_FILE"
    printf '{}\n'
    exit 0
fi
```

---

## TTL 清理

Hook 脚本自动清理 7 天前的状态文件：

```bash
find "$REAL_HOME/.hermes/review-states" -type f -name "state.json" -mtime +7 -delete
find "$REAL_HOME/.hermes/review-states" -type d -empty -delete
```

---

## 与 ECC hookify 的区别

| 维度 | ECC 原版 | self-review-skill |
|------|---------|------------------|
| 目标 | 防止危险操作 | 强制提交前自我审查 |
| 触发 | PreToolUse 拦截工具 | pre_tool_call 拦截 commit |
| 状态管理 | 无 | 状态机 + 临时文件 + cycle_count |
| 循环终止 | 无 | cycle_count 检测（连续 3 次强制放行） |
| 状态清理 | 无 | TTL 7 天自动清理 |

---

## 参考

- ECC hookify: https://github.com/relunctance/ecc
- Hermes Hooks: `shell_hooks.py`
- gql-bots #147: https://github.com/relunctance/gql-bots/issues/147
