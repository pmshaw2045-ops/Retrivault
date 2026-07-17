# Retrivault 开发进展报告

> 阶段：v0.1 内测版 · 2026-07-17
> 状态：**已通过完整评测验证**，项目达到开源可发布质量

---

## 一、当前状态总览

| 维度 | 状态 | 详情 |
|------|------|------|
| 代码行数 | 4,251 (Python) + 2,066 (HTML/CSS/JS) | 102 个跟踪文件 |
| 测试 | 131 通过（127 单元 + 4 集成）| ruff 干净，CI 3 Python 版本 |
| 文档 | 10 篇样本文档 | 覆盖 RAG/Agent/深度学习/量子力学/二战 |
| 评测 | 32 用例金标数据集 | Hit Rate 88%, Recall@5 88%, MRR 0.82 |
| 提交 | 42 次 | 信息清晰，历史可追溯 |
| 部署 | Dockerfile + docker-compose.yml | 一行命令启动 |

## 二、核心架构

```
用户输入 ──► Query Rewriter (DeepSeek Flash 3路)
                │
                ▼
            Embedding (BGE-M3 via 硅基API)
                │
                ▼
            Retriever (LanceDB 混合搜索)
                │  └─ rescale_score(k=5) 内部排序
                ▼
            Reranker (BGE-Reranker-v2-m3)
                │
                ▼
            Generator (DeepSeek V4 Pro)
                │
                ▼
            SSE 流式输出 ──► 前端控制台
```

**分数体系（关键设计决策）：**

| 层 | 函数 | 参数 | 范围 | 用途 |
|----|------|------|------|------|
| 排序 | `rescale_score()` | k=5, midpoint=0.3 | 0.18~0.75 | 阈值过滤、reranker 输入 |
| 展示 | `display_score(sqrt)` | power=0.5 | 0.42~0.87 | 用户可见分数 |

阈值比较统一在 **display_score 空间**进行，用户设 0.35 = 能看到 0.46+ 的结果。

## 三、本阶段完成事项（2026-07-17）

### 产品与体验
- 4 篇长文档（深度学习演进、多 Agent 协作、二战转折点、量子力学）
- 32 用例金标数据集（24 正向 + 8 负向/边界）
- Eval 面板：Delta 对比、坏案例聚合、配置快照、5 指标一行展示
- 参数设置弹窗：严格模态、12px 标签、12 种设置项
- 搜索输入 IME 兼容（中文输入不误触搜索）

### 核心修复
- Eval 指标使用用户设定的 top_k 而非硬编码 5
- Hit Rate / MRR 限制在 top_k 范围内计算
- Recall/Precision/NDCG 文件级去重（同文件多 chunk 只算一次命中）
- Sigmoid k=30→k=5 恢复分数区分度
- 检索去重按 section 维度（同文件不同小节可共存）
- Token 截断增加英文句号和换行符边界
- 断点恢复只扫 pending 文件，避免全量扫描

### 基础设施
- GitHub Actions CI（3 Python 版本、ruff + pytest）
- Dockerfile + docker-compose.yml
- pre-commit 钩子（ruff + 基础检查）
- CHANGELOG 维护

### 工程清理
- 删除死文件 `config/config.schema.json`
- 删除 `start.py` 中误导的 `HF_HUB_OFFLINE` 环境变量
- 修复 `start.py` PIPE 死锁（后台线程消费输出）
- 组件初始化失败改为打印具体原因

## 四、已知短板（待解决）

| 优先级 | 问题 | 影响 | 预估工作量 |
|--------|------|------|-----------|
| P0 | 无 Docker 发布 | Dockerfile 已就绪但未推送镜像到 registry | 低 |
| P1 | 无 API 鉴权 | CORS `allow_origins=["*"]`，端点到部署无保护 | 低 |
| P1 | 无结构化日志 | 错误仅 `print()` 到 stdout | 低 |
| P2 | 无速率限制 | 大并发请求直接打爆 uvicorn | 中 |
| P2 | 集成测试需 API Key | CI 中无法运行 | 中 |
| P3 | 无多轮对话 | 搜索为单次调用，无上下文 | 高 |

## 五、样本文档列表

| 文件 | 领域 | 字数 | 关键内容 |
|------|------|------|---------|
| 01-rag-basics.md | RAG 基础 | ~600 | RAG 核心概念、与微调对比 |
| 02-agent-architecture.md | AI Agent | ~900 | Agent 核心组件（推理/记忆/工具/规划）|
| 03-embedding-guide.md | Embedding | ~700 | BGE-M3 对比、维度与相似度 |
| 04-vector-db-comparison.md | 向量数据库 | ~800 | LanceDB vs FAISS vs Qdrant vs Pinecone |
| 05-obsidian-workflow.md | Obsidian | ~700 | 原子化笔记、标签、双向链接 |
| 06-prompt-engineering.md | Prompt | ~900 | Few-shot、角色设定、格式约束 |
| 07-deep-learning-evolution.md | 深度学习 | ~1,800 | CNN/RNN/Transformer/GPT/MoE/多模态 |
| 08-multi-agent-collaboration.md | 多 Agent | ~1,800 | 编排器/对话式/市场模式、通信协议、冲突解决 |
| 09-wwii-turning-points.md | 二战 | ~1,600 | 不列颠/斯大林格勒/诺曼底/中途岛/原子弹 |
| 10-quantum-mechanics.md | 量子力学 | ~1,800 | 波粒二象性/不确定性原理/纠缠/隧穿/量子计算 |

## 六、评测指标基线（Retrivault-Comprehensive 数据集）

| 指标 | 值 | 说明 |
|------|-----|------|
| Hit Rate | 88% | 28/32 命中（4 个负向用例正确拒绝） |
| MRR | 0.82 | 第一个相关文档平均在 Top-2 |
| Precision@5 | 18% | 每 query 平均 1 篇相关文档 / 5 |
| Recall@5 | 88% | 文件级去重 |
| NDCG@5 | 0.83 | 归一化折损累积增益 |

配置：mode=hybrid, top_k=5, threshold=0.1, rerank=enabled, rewrite=enabled
