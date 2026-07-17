---
title: Embedding 模型选型指南
tags: [embedding, llm, vector-search]
created: 2026-02-20
aliases: [Embedding对比, 文本向量化]
---

# Embedding 模型选型指南

## 主流 Embedding 模型对比

| 模型 | 维度 | 特点 | 适用场景 |
|------|------|------|----------|
| **BGE-M3** | 1024 | 多语言（中英文最佳），密集向量+稀疏向量双模式 | 中文知识库检索 |
| **text-embedding-3-large** | 3072 | OpenAI 出品，通用能力强，但需要 API Key | 英文文档检索 |
| **intfloat/multilingual-e5-large** | 1024 | 多语言支持好，指令可调 | 多语言混合文档 |
| **GTE-Qwen2** | 1792 | 阿里巴巴出品，中文理解强 | 中文长文档 |

> [!tip] 选型建议
> BGE-M3 是目前中文检索场景的性价比之王——1024维平衡精度与存储，零 API 费用（本地运行），且支持混合检索（密集+稀疏）。

## Embedding 的核心概念

### 1. 向量维度与性能

维度越高 → 表达能力越强 → 检索精度越高 → 存储和计算成本越大。

```python
# BGE-M3: 1024 维向量
# 10 万篇文档 × 1024 维 × 4 字节 = ~400MB
num_docs = 100_000
dim = 1024
storage_gb = (num_docs * dim * 4) / (1024**3)
print(f"存储需求: {storage_gb:.2f} GB")
```

### 2. 查询 vs 文档向量

BGE-M3 在向量化查询时，需要添加指令前缀：

```
"为这个句子生成表示以用于检索相关文章：" + 查询文本
```

这是 [[RAG 基础知识]] 中提到的重要细节。

## 如何评估 Embedding 质量

1. **MTEB 基准**：包含 8 个任务的综合评测
2. **自己的数据 + 金标数据集**：用 Hit Rate / MRR 衡量
3. **A/B 测试**：在真实搜索场景对比不同模型

#rag/advanced #embedding #vector-search
