# 参与 Retrivault 开发

感谢你的关注！以下是如何参与项目开发的指引。

## 快速开始

```bash
git clone https://github.com/xiaoleishaw/retrivault.git
cd retrivault
python3 -m venv .venv && source .venv/bin/activate
make install
```

## 开发流程

1. 开始前先**查看已有 Issue**，避免重复工作。
2. **创建分支**：`git checkout -b feat/你的功能`
3. **修改代码**，保持改动聚焦、原子化。
4. **运行测试**：`make test`（必须全部通过）
5. **代码检查**：`make lint`（不能有新增警告）
6. **推送并创建 PR**。

## 代码规范

- **Python 3.10+** — 充分利用现代类型注解。
- **Ruff** — 用 `make fix` 自动格式化。每行 100 字符。
- **mypy** — `strict = false` 但 `warn_return_any = true`。所有公开 API 需要类型注解。
- **测试** — 每个新功能必须配套测试。使用 `pytest` + `pytest-asyncio`。
- **禁止循环引用** — 保持依赖方向：`interfaces ← pipeline ← api ← frontend`。

## 新增 Provider

所有 Provider 需实现 `src/interfaces/` 中的 ABC 接口：

1. 实现 ABC（如 `class MyVectorStore(VectorStore):`）
2. 在对应的 `__init__.py` 工厂中注册
3. 在 `config/config_schema.py` 中添加配置字段
4. 在 `src/api/dependencies.py` 中注入

## 提交信息格式

遵循[约定式提交（Conventional Commits）](https://www.conventionalcommits.org/zh-hans/)：

```
feat(scanner): 添加 .excalidraw.md 排除规则
fix(chunker): 合并过小的标题碎片
docs(readme): 补充架构图
test(retriever): 增加混合搜索边界用例
```

## PR 检查清单

- [ ] 测试通过（`make test`）
- [ ] 代码检查通过（`make lint`）
- [ ] 没有无故新增 `# type: ignore`
- [ ] 新增功能同步更新 README
- [ ] 如有必要，添加 CHANGELOG 条目

## 问题反馈

在 GitHub 上提交 [Discussion](https://github.com/xiaoleishaw/retrivault/discussions) 或 [Issue](https://github.com/xiaoleishaw/retrivault/issues)。
