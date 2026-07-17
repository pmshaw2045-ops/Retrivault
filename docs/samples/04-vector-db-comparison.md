---
title: 向量数据库选型对比
tags: [vector-db, database, architecture]
created: 2026-04-01
aliases: [向量数据库对比, LanceDB vs FAISS]
---

# 向量数据库选型对比

## 市场方案一览

| 方案 | 部署方式 | 内置 FTS | 可靠性 | 入门成本 |
|------|---------|----------|--------|----------|
| **LanceDB** | 嵌入式 | ✅ 原生支持 | 高（列式存储） | 零（pip install） |
| **FAISS** | 嵌入式 | ❌ 需额外集成 | 中（需自己管理） | 零 |
| **ChromaDB** | 嵌入式 | ⚠️ 实验性 | 低（SQLite 损坏风险） | 零 |
| **Qdrant** | 独立服务 | ❌ | 高 | 需 Docker |
| **Milvus** | 独立集群 | ❌ | 非常高 | 运维复杂 |
| **Weaviate** | 独立服务 | ✅ | 高 | 需 Docker |

## 为什么选择 LanceDB

### 核心优势

1. **零外部依赖**：不需要 Docker / 独立服务，pip install 即可用
2. **列式存储（Lance 格式）**：比 SQLite 可靠得多，没有数据损坏风险
3. **内置 FTS**：向量检索 + 全文搜索一把梭，不需要 Whoosh / Elasticsearch
4. **混合搜索**：`table.search(vector, fts_columns=["content"]).hybrid_search()`
5. **版本化**：自动管理数据版本，支持时间旅行查询

### 局限性

- 🔸 单机部署，不支持分布式
- 🔸 个人知识库场景无影响（10 万级文档）

## 索引策略对比

```python
# Flat（暴力搜索）
# 精度最高，速度最慢。适合 < 10K 数据
table.search(query_vector).limit(5)

# IVF_PQ（索引搜索）
# 精度略降，速度提升 10-100x。适合 > 100K 数据
table.create_index(num_sub_vectors=96)
table.search(query_vector).limit(5)
```

## 混合搜索原理

[[RAG 基础知识]] 中提到，混合搜索 = 向量搜索 + 关键词搜索。

LanceDB 的实现方式：
1. 向量搜索找出语义相似文档
2. FTS（全文搜索）找出关键词匹配文档
3. 两者结果融合排序

> [!note] 实践建议
> 对于个人知识库（文档量 < 10 万），直接用 flat 搜索 + 混合模式即可，不需要建立索引，省去维护成本。

#rag/infra #vector-db #architecture
