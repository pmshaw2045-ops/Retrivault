# Git 高级工作流

## 分支策略

### Git Flow

- **main**：生产分支，只接受从 release 和 hotfix 的合并
- **develop**：开发主分支
- **feature/***：特性分支，从 develop 分出，合并回 develop
- **release/***：发布准备分支，测试和修复后合并到 main 和 develop
- **hotfix/***：紧急修复，从 main 分出，合并回 main 和 develop

### Trunk-Based Development

- 所有开发者直接在主干（main）上工作或创建短命分支
- 分支存活不超过 1-2 天
- 配合特性开关（Feature Flag）控制发布

## 交互式变基

```bash
git rebase -i HEAD~5   # 交互式变基最近5个提交
# 常用操作：pick / squash / fixup / reword / drop
```

**squash** 和 **fixup** 的区别：squash 保留提交信息，fixup 丢弃。

## 合并 vs 变基

```bash
git merge feature    # 创建合并提交，保留完整历史
git rebase main      # 线性历史，提交更清晰
```

### 何时用变基

- 推送前整理本地提交
- 将功能分支更新到最新的 main
- **不要对已推送的公共分支变基**

## Cherry-Pick

```bash
git cherry-pick commit_hash  # 挑选某个提交应用到当前分支
```

适用于：hotfix 从 main 同步到 release 分支、挑选特定功能到其他版本。

## Git Hooks

- **pre-commit**：提交前运行 lint/测试
- **commit-msg**：校验提交信息格式
- **pre-push**：推送前运行完整测试
