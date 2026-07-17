---
title: RAG 基础知识
tags: [rag, knowledge-base]
created: 2026-04-01
aliases: [检索增强生成, RAG入门]
---

# RAG 基础知识

## 什么是 RAG

RAG（Retrieval-Augmented Generation）是一种结合信息检索和文本生成的技术架构。

> [!note] 核心原理
> 先从知识库中检索相关文档片段，再将片段作为上下文注入 LLM 的 Prompt 中。

## 关键组件

1. **文档分块**：将长文档切分为可检索的片段
2. **向量化**：使用 Embedding 模型将文本转为向量
3. **向量检索**：通过相似度搜索找到最相关的片段
4. **Prompt 组装**：将检索结果与用户问题组合提交 LLM

## 分块策略

分块大小时需要考虑：
- 太小：丢失上下文
- 太大：检索精度下降

推荐 512 tokens 作为起点。

#rag/basics
