---
title: Obsidian 高效工作流
tags: [obsidian, productivity, workflow]
created: 2026-05-10
aliases: [Obsidian技巧, 笔记工作流]
---

# Obsidian 高效工作流

## 核心原则

Obsidian 的价值不在于你写了多少，而在于你能否**快速找到**之前写过的内容。

### 1. 原子化笔记

每条笔记只讲一个概念。这看起来浪费，但长期来看让检索更容易：

```
✅ 好的做法：
  - embedding-guide.md（只讲 Embedding）
  - vector-db-comparison.md（只讲数据库选型）

❌ 不推荐：
  - AI 完整学习笔记.md（什么都写，什么都找不到）
```

原子化笔记与 [[RAG 基础知识]] 中的分块策略高度吻合——越小越精准。

### 2. 标签体系

使用分级标签（Nested Tags）维护知识图谱：

```
#rag/basics     基础概念
#rag/advanced   进阶技巧
#rag/infra      基础设施选型
#agent/runtime  Agent 运行时
#agent/tools    工具调用
```

### 3. 双向链接

利用 `[[wikilink]]` 建立笔记间的关联。当你在阅读时，Obsidian 会显示：
- 当前笔记引用了哪些笔记（出链）
- 哪些笔记引用了当前笔记（反链）

> [!tip] 小技巧
> 每次新建笔记时，问自己三个问题：
> 1. 这篇笔记和哪些已有笔记相关？
> 2. 应该打什么标签？
> 3. 别人搜索什么关键词时会需要这篇笔记？

### 4. Dataview 查询

```dataview
TABLE file.ctime as "创建时间", tags
FROM #rag
SORT file.ctime DESC
```

### 5. 搜索策略对比

| 方式 | 速度 | 理解能力 | 适合场景 |
|------|------|----------|----------|
| Obsidian 原生搜索(Cmd+Shift+F) | 快 | 关键词匹配 | 已知内容的精确定位 |
| Retrivault RAG 搜索 | 中等 | 语义理解 | 模糊查询、跨主题关联 |

> [!note] 结论
> 两者互补——原生搜索做"记住位置"的精确定位，RAG 搜索做"模糊记忆"的语义发现。

#obsidian/workflow #productivity
