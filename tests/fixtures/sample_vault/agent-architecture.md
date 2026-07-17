---
title: Agent 架构选型
tags: [agent, architecture]
created: 2026-03-15
---

# Agent 架构选型

## 存储组件

Agent 的存储组件应该支持以下能力：

- 短期记忆（当前会话上下文）
- 长期记忆（跨会话知识积累）
- 工具调用结果的持久化
- 向量化检索

推荐使用 **LanceDB** 作为嵌入式向量数据库，搭配 SQLite 做结构化管理。

## 通信模式

Agent 间通信推荐使用 Redis Pub/Sub 或 NATS。

### 相关笔记

- [[Agent Runtime 组件表]]
- [[Agent 落地12条]]

#agent/runtime #architecture
