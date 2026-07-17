# Changelog

## 0.1.0 (2026-07-17)

### Features

- 核心 RAG 管线：扫描 → 解析 → 分块 → Embedding → 检索 → 重排 → 生成
- Obsidian 语法解析：wikilink、tag、frontmatter、callout、embed
- SSE 流式搜索管线，浏览器实时展示每一步
- DeepSeek Flash 3 路 Query 改写 + 输出验证 + 异常回退
- BGE-Reranker-v2-m3 Cross-Encoder 重排序（仅排序不改分）
- 混合搜索（LanceDB 向量 + FTS）
- Markdown 结构感知分块 + 自动合并碎片
- 索引生命周期管理（首次/增量/断点恢复/模型变更检测）
- 参数设置弹窗（Top-K / 检索模式 / Temperature / 相似度阈值 / 重排序 / Query改写）
- 内置 RAG 评测面板（Hit Rate / MRR / Precision@K / Recall@K / NDCG@K + Delta 对比）
- Provider 无关架构（可切换 DeepSeek / OpenAI / Ollama）
- 图片文件名注入搜索（`![[架构图.png]]` → `[图片: 架构图]`）

### Improvements

- 模块化弹窗：严格模态行为，进度中不可关闭
- 配置优先级链：代码默认值 < profiles/*.yaml < config/config.yaml < .env < UI 面板
- Vault 路径不存在时自动 fallback 到示例文档
- .env.example 按三种方案分类管理
- 中文 README / CONTRIBUTING
- IME 输入法兼容：中文输入时 Enter 不误触搜索

### Fixes

- LazyEmbedder base_url 未 fallback 到 config.yaml
- Rerank/Query 开关关闭后前端仍显示"运行中"
- Python bool 型 query param 的 `bool("false") == True` 陷阱
- Eval 指标使用用户设定的 top_k 而非硬编码 5
- Hit Rate / MRR 未限制在 top_k 范围内计算
- Eval 前后对比 Delta 显示优化
- 参数配置跨标签页共享（sessionStorage → localStorage）

### CI & Docs

- GitHub Actions CI（3 个 Python 版本，ruff + pytest）
- MIT License
- 4 张产品截图
- 5 个真实徽章（CI / Python / License / Last commit / Stars）
