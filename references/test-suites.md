# self-review-skill 测试套件

## 运行全部测试

```bash
cd /home/gql/repos/self-review-skill
python3 -m pytest tests/ -v
```

**当前：34/34 通过**

## 单元测试

### tests/unit/test_state_machine.py

状态机核心逻辑测试（9 tests）。

### tests/unit/test_status.py

`review_status.py` CLI 测试（5 tests）。

```bash
python3 -m pytest tests/unit/test_status.py -v
```

### tests/unit/test_review_reset.py

`review_reset.py` 测试（3 tests）。

### tests/unit/test_flock_race.py

并发锁测试（2 tests）。

## 集成测试

### tests/integration/test_edge_cases.py

边界条件测试（5 tests）：
- `test_empty_repo_first_commit_blocked` — 空仓库第一次提交被拦截
- `test_no_remote_repo_blocked` — 无远程仓库的提交也被拦截
- `test_detached_head_commit_blocked` — detached HEAD 状态下提交被拦截
- `test_empty_staged_commit_allowed` — 无 staged 内容时放行
- `test_only_unchanged_file_staged` — staged 后无实际改动

### tests/integration/test_multi_repo_isolation.py

多仓库/分支隔离测试（2 tests）：
- `test_different_repos_independent` — 不同仓库状态独立
- `test_same_repo_different_branches_independent` — 同仓库不同分支状态独立

### tests/integration/test_force_push_consistency.py

状态一致性测试（1 test）：
- `test_new_diff_after_existing_state` — 状态存在时新 diff 被正确识别

### tests/integration/test_reset_hard_state.py

reset --hard 行为测试（3 tests）：
- `test_reset_hard_discards_uncommitted_changes` — reset --hard 丢弃未提交改动
- `test_reset_hard_after_hook_block` — hook block 后 reset --hard 改动被丢弃
- `test_state_file_persists_after_reset_hard` — reset --hard 不影响状态文件

### tests/integration/test_real_hook_env.py

Hermes Hook 真实环境测试（4 tests）：
- `test_hermes_hook_registered` — 验证 Hermes hook 已注册
- `test_hermes_hook_test_passes` — 验证 `hermes hooks test pre_tool_call` 成功
- `test_hook_blocks_commit_in_clean_repo` — 干净仓库第一次提交被拦截
- `test_hook_allows_after_approved` — approved 后相同 diff 放行

**前提**：Hermes hook 已通过 config.yaml 注册：
```yaml
hooks:
  pre_tool_call:
    - matcher: terminal
      command: /home/gql/repos/self-review-skill/hooks/self-review-hook.sh
      timeout: 30
```

## 回归测试

```bash
# 快速回归
cd /home/gql/repos/self-review-skill
python3 -m pytest tests/unit/ tests/integration/ -v

# 完整回归（包含 hook 环境测试）
python3 -m pytest tests/ -v
```
