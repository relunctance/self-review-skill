# self-review-skill 踩坑沉淀

## 🏷️ 按标签索引

## #hermes-hook
### Hermes Hook block 机制验证
- **日期**：2026-05-29
- **问题**：不确定 Hermes pre_tool_call 的 block 行为
- **结论**：已验证 block 机制完全可用，返回 `{"action":"block","message":"..."}` 格式
- **依据**：`shell_hooks.py` L528-533

## #home-path
### HOME 被篡改问题
- **日期**：2026-05-29
- **问题**：`Path.home()` 在 Hermes profile 下返回 `~/.hermes/profiles/baijie/home/`
- **解决**：hook 脚本中使用 `getent passwd "$(whoami)" | cut -d: -f6` 获取真实 home
- **教训**：所有涉及状态文件路径的地方都要用真实 home

## #payload-structure
### pre_tool_call payload 结构
- **日期**：2026-05-29
- **验证**：payload 结构为 `{"tool_name":"terminal","tool_input":{"command":"..."}}`
- **依据**：`shell_hooks.py` L474-481

## #git-output-newline
### git 命令输出包含换行符
- **日期**：2026-05-30
- **问题**：Hook 和 Approve 计算的路径 hash 不一致，导致状态文件无法匹配
- **根本原因**：
  - `git rev-parse --show-toplevel` 输出包含换行符
  - `echo "$VAR" | md5sum` 会把换行符也计算进去
  - 正确做法：`echo -n "$VAR" | md5sum`
- **教训**：所有涉及 git 命令输出的 hash 计算都要用 `echo -n`

## #git-c-flag
### git -C 指定工作目录的正确用法
- **日期**：2026-05-30
- **问题**：Hook 运行时工作目录是 skill 目录，不是 git 仓库目录
- **解决**：所有 git 命令使用 `git -C "$PAYLOAD_CWD"` 指定工作目录
- **教训**：不要依赖当前工作目录，始终显式指定

## #branch-detection
### 分支检测逻辑
- **日期**：2026-05-30
- **问题**：`git symbolic-ref --short HEAD` 在无 commit 时失败，`git branch --show-current` 更可靠
- **选择**：使用 `git branch --show-current`，为空时返回 "detached"
- **注意**：`git branch --show-current` 输出也包含换行符

## #cycle-detection-bug
### 循环检测 bug 修复
- **日期**：2026-05-30
- **问题**：cycle_count 在 diff 无变化时没有增加，导致连续多次相同 commit 无法触发强制放行
- **根因**：之前的代码只在 diff 变化时更新 cycle_count，diff 无变化时直接返回 block
- **修复**：
  - diff 无变化但未 approved 时，每次都增加 cycle_count
  - diff 变化时，重置 cycle_count 为 0（因为是新修改）
- **教训**：循环计数应该在所有"需要再次审查"的情况下累加，不只是 diff 变化时
