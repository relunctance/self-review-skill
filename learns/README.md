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
