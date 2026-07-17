---
title: Agent 架构选型指南
tags: [agent, architecture, llm]
created: 2026-03-15
aliases: [Agent选型, AI Agent 架构]
---

# Agent 架构选型指南

## 核心组件

一个完整的 AI Agent 系统通常包含以下核心组件：

| 组件 | 职责 | 推荐方案 |
|------|------|----------|
| 推理引擎 | 理解任务并制定执行计划 | LLM（如 DeepSeek） |
| 记忆系统 | 短期/长期记忆管理 | LanceDB + SQLite |
| 工具调用 | 执行外部操作 | Function Calling |
| 规划器 | 任务分解与编排 | ReAct / Plan-Execute |

## 存储组件选型

Agent 的存储组件是最容易被低估的部分，但它直接影响系统的可维护性。

### 需求分析

一个好的 Agent 存储方案需要支持：

- **短期记忆**：当前会话的对话历史
- **长期记忆**：跨会话的知识积累
- **工具调用结果**：执行结果的持久化
- **向量化检索**：基于语义相似度查找历史经验

### 推荐方案

```
LanceDB（向量存储 + 全文检索）
    +
SQLite（结构化状态管理）
```

> [!warning] 避坑
> 不要用 ChromaDB 做长期存储——它的 SQLite 底层有数据损坏风险。LanceDB 使用列式存储格式，可靠性更高。

## 通信模式

Agent 各组件间的通信推荐使用 **事件驱动架构**：

```python
# 发布事件
event_bus.publish("task.completed", {"task_id": "123", "result": "..."})

# 订阅事件
@event_bus.subscribe("task.completed")
async def on_task_done(event):
    await notify_user(event.data)
```

## 相关笔记

- [[RAG 基础知识]]
- [[Embedding 模型选型]]

#agent/runtime #architecture #storage
