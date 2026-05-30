---
name: self-review-skill
description: 每次 commit 前强制审查改动，减少 bug 率。触发条件：需要进行 git commit 前、发现潜在 bug 需要审查、多 Agent 并行提交需要锁保护。
version: "1.2.0"
author: relunctance
license: MIT
category: development
tags:
  - hermes
  - hook
  - git
  - quality
  - commit-review
trigger:
  - git commit 前
  - commit 前审查
  - 提交前检查
  - 每次 commit
  - 小步迭代
  - self-review
  - 强制审查
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
2. 🔴 **CHECKPOINT**：读取 `~/.hermes/review-states/{hash}/context.json` 审查 diff
3. 发现 bug → 修复 → 再次审查（回到步骤 2）
4. 🛑 **CHECKPOINT**：确认 diff 无变化后，执行 approve 脚本
5. 再次 commit → ✅ 放行

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

## 快速开始

### 1. 注册 Hook

编辑 `~/.hermes/profiles/baijie/config.yaml`，找到 `hooks: {}` 替换为：

```yaml
hooks:
  pre_tool_call:
    - matcher: terminal
      command: /home/gql/repos/self-review-skill/hooks/self-review-hook.sh
      timeout: 30
```

验证：
```bash
hermes hooks list          # 应显示 pre_tool_call
hermes hooks test pre_tool_call  # exit=0
```

### 2. 日常工作流

```
Agent: 修改代码 → git add → git commit
    │
    ├─ Hook 拦截 → 返回 {"action":"block","message":"请审查..."}
    │
    ├─ 🔴 CHECKPOINT：读取 ~/.hermes/review-states/{hash}/context.json
    │
    ├─ 审查 diff
    │   ├─ 发现 bug → 修复 → git add → git commit（再次拦截，回到上一步）
    │   └─ 无 bug → 继续
    │
    └─ 🛑 CHECKPOINT：确认 diff 无变化后，执行 approve：
       python3 ~/self-review-skill/scripts/review_approve.py

       然后重新 commit → ✅ Hook 放行
```

### 3. 查看审查状态

```bash
# JSON 格式输出
python3 ~/self-review-skill/scripts/review_status.py --json

# 人类可读格式
python3 ~/self-review-skill/scripts/review_status.py
```

### 4. 重置审查状态

```bash
python3 ~/self-review-skill/scripts/review_reset.py
```

---

## 脚本列表

| 脚本 | 用途 |
|------|------|
| `hooks/self-review-hook.sh` | 核心 hook（Hermes pre_tool_call） |
| `scripts/review_approve.py` | approve 审查完成 |
| `scripts/review_reset.py` | 重置审查状态 |
| `scripts/review_status.py` | 查询当前审查状态 |

---

## 测试套件

详见 [references/test-suites.md](references/test-suites.md)

**34/34 测试通过**

```bash
cd /home/gql/repos/self-review-skill
python3 -m pytest tests/ -v
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
│   ├── review_approve.py      # approve 脚本
│   ├── review_reset.py        # reset 脚本
│   └── review_status.py       # 状态查询 CLI
├── tests/
│   ├── unit/
│   │   ├── test_state_machine.py
│   │   ├── test_status.py
│   │   ├── test_review_reset.py
│   │   └── test_flock_race.py
│   └── integration/
│       ├── test_edge_cases.py
│       ├── test_multi_repo_isolation.py
│       ├── test_force_push_consistency.py
│       ├── test_reset_hard_state.py
│       └── test_real_hook_env.py
├── references/
│   └── test-suites.md         # 测试套件详情
└── learns/
    └── README.md              # 踩坑记录
```

---

## 关键约束

### ❌ 禁止行为（三段式 fallback）

| # | 禁止行为 | 触发条件 | 一线修复 | 仍失败兜底 |
|---|---------|---------|---------|-----------|
| 1 | 在 hook 中执行 `git commit` | 递归调用，死循环 | 只读取状态，不执行 commit | 检查调用栈深度，超阈值强制退出 |
| 2 | 直接修改 state.json | 状态不一致，审查失效 | 使用 approve 脚本或 reset 命令 | 删除状态文件重新开始：`rm -rf ~/.hermes/review-states/{hash}` |
| 3 | 跳过 approve 直接 commit | 绕过审查机制，bug 上线 | 必须先 approve 再 commit | hook 会持续 block，直到 approve |
| 4 | approve 后修改文件但不重新 approve | 漏审，bug 上线 | 修改后必须重新 approve | hook 检测到 diff 变化会重新 block |
| 5 | 多仓库共享同一个状态目录 | 状态混淆，误判 | 每个仓库有独立的 REPO_HASH | 用 `review_status.py --json` 确认当前仓库路径 |

---

## 参考

- [references/test-suites.md](references/test-suites.md) — 完整测试套件说明
- ~~ECC hookify~~（已废弃，仅作设计参考）
