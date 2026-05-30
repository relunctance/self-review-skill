# self-review-skill

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/Version-1.1.0-green.svg)](https://github.com/relunctance/self-review-skill)
[![Platforms](https://img.shields.io/badge/Platforms-Hermes%20%7C%20WSL-blue.svg)](https://github.com/relunctance)
[![Category](https://img.shields.io/badge/Category-Development%20Safety-blue.svg)](#)
[![Stage: Production](https://img.shields.io/badge/Stage-Production-brightgreen)](https://github.com/relunctance/self-review-skill)
[![Last Updated](https://img.shields.io/badge/Updated-2026--05--30-orange)](https://github.com/relunctance/self-review-skill)

> 🤖 **每次 commit 前强制审查改动，减少 bug 率**
>
> 小步迭代开发模式：改动越小 → 审查越快 → Bug 发现率越高

## 🎯 触发条件

当需要进行以下操作时使用：
- 任何项目的 commit 前
- 需要确保代码改动经过自检
- 需要记录每次 commit 的审查轨迹

## 🎯 核心功能

| 功能 | 说明 |
|------|------|
| **Hook 拦截** | 拦截 `git commit`，强制审查后再提交 |
| **状态机** | IDLE → PENDING_REVIEW → approved → IDLE |
| **循环检测** | 连续 3 次相同 diff 强制放行（第3次触发），避免死循环 |
| **分支隔离** | 每个仓库 + 分支有独立状态，互不干扰 |
| **触发日志** | 记录每次 hook 触发，便于观察和调试 |

## 📖 工作原理

```
Agent: 修改代码
    ↓
Agent: git add + git commit
    │
    ├─ Hook 拦截
    │   diff 写入 context.json
    │   返回 block + 提示
    │
    ▼
Agent: 读取 context.json 审查
    │
    ├─ 发现 bug → 修复 → 再次审查
    └─ 无 bug → 执行 approve 脚本
    ↓
Agent: 再次 commit → 通过 ✅
```

## 🚀 快速开始

### 安装

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

### 使用

1. **修改代码**后执行 `git add` + `git commit`
2. Hook 会 **block** 并提示审查
3. Agent **读取** `~/.hermes/review-states/{hash}/context.json` 审查改动
4. **无 bug** 时，执行 approve：
   ```bash
   echo '{"cwd":"<repo_path>"}' | python3 ~/self-review-skill/scripts/review_approve.py
   ```
5. **再次 commit** → 通过 ✅

## 📁 文件结构

```
self-review-skill/
├── SKILL.md                    # Skill 定义
├── README.md                   # 本文档
├── LICENSE                     # MIT License
├── hooks/
│   └── self-review-hook.sh    # 核心 hook 脚本
├── scripts/
│   └── review_approve.py      # approve 脚本
└── tests/
    ├── unit/                   # 单元测试
    └── integration/            # 集成测试
```

## 🧪 测试

```bash
cd ~/self-review-skill

# 单元测试
python3 -m pytest tests/unit/test_state_machine.py -v
bash tests/unit/test_hook_script.sh

# 集成测试
bash tests/integration/test_full_flow.sh

# 回归测试
python3 -m pytest tests/unit/ -v && bash tests/unit/*.sh && bash tests/integration/*.sh
```

## 📊 临时文件

| 文件 | 路径 |
|------|------|
| 状态文件 | `~/.hermes/review-states/{repo_hash}/{branch_hash}/state.json` |
| 上下文 | `~/.hermes/review-states/{repo_hash}/{branch_hash}/context.json` |
| Hook 日志 | `~/.hermes/logs/pre-tool-hook.log` |

## 🔧 配置

### 多 Agent 并行

| 场景 | 行为 |
|------|------|
| 不同分支 | ✅ 完全并行 |
| 同一分支 | ⚠️ 串行（flock 锁） |
| 同一分支 + 同时 | 第二个被 block，提示"稍后再试" |

### TTL 清理

Hook 脚本自动清理 **7 天前**的状态文件。

## 🐛 踩坑

| 坑 | 解决 |
|----|------|
| git 命令输出包含换行符 | 使用 `echo -n` 计算 hash |
| Hook 运行在 skill 目录而非 git 仓库 | 从 payload cwd 字段获取实际路径 |
| 分支检测在无 commit 时失败 | 使用 `git branch --show-current` |
| Python 和 Shell 路径 hash 不一致 | 统一使用 `echo -n \| md5sum` |

## 📚 参考

- [Hermes Shell Hooks](https://github.com/relunctance/hermes-agent) — Hook 机制
- ~~[ECC hookify](https://github.com/relunctance/ecc)~~（已废弃，仅作设计参考）

## 📝 Changelog

### v1.0.1 (2026-05-30)

- fix: 修复 git 命令输出换行符导致的 hash 不一致

### v1.0.0 (2026-05-30)

- 🎉 初始版本
- ✅ Hook 拦截 git commit
- ✅ 状态机（PENDING_REVIEW）
- ✅ approve 脚本
- ✅ 循环检测（连续 3 次强制放行，第3次触发）
- ✅ 分支隔离 + flock 锁
- ✅ TTL 清理
- ✅ Hook 触发日志
