# RAG 个人知识库系统 — 搭建规划文档 v3.0

> 版本：v3.0
> 修订范围：向量数据库选型替换 + 架构审视 + 落地细节补全
> 核心变动：
>   - **ChromaDB → LanceDB**（嵌入式列式存储，内置 FTS，数据可靠性显著提升）
>   - **Whoosh → LanceDB 内置 FTS**（减去一个依赖，混合搜索统一入口）
>   - 存储路径明确化（`data/lancedb/` + `data/rag.db`）
>   - 启动流程明确化（单命令 `make start` 同时拉起 FastAPI + Streamlit）
>   - 配置文件职责划分明确化（`.env` = secrets / `config.yaml` = 业务参数 / `profiles/*.yaml` = provider 组合）
>   - SQL Schema 补全（`chunk_progress` 新增 `embedding_model` 字段）
>   - 每个 Step 补全测试要求 + Phase 2/3 补全验收标准

---

## 零、变更记录

### v3.0 相对于 v2.0 的完整变更

| 变更项 | v2.0 | v3.0 | 原因 |
|--------|------|------|------|
| 向量数据库 | ChromaDB（SQLite 后端） | **LanceDB**（Lance 列式格式） | 数据可靠性。ChromaDB SQLite 后端有数据损坏风险，LanceDB 列式存储 + 版本化设计更可靠 |
| 关键词搜索 | Whoosh | **LanceDB 内置 FTS** | 减依赖。LanceDB 原生的 `add_fts()` 和 `hybrid_search()` 一把梭 |
| 混合搜索 | 向量 + Whoosh BM25 双路融合 | **LanceDB 原生 hybrid_search** | API 更简洁，单表管理向量 + 全文索引 |
| 存储路径 | 未指定 | `data/lancedb/` + `data/rag.db` | 明确约定防散乱 |
| 启动方式 | 未说明 | `make start`（单命令同时启动 FastAPI + Streamlit） | 解决"开两个终端"的困惑 |
| 配置文件分工 | 优先级链但不清楚放什么 | 三文件职责明确表 | 开源用户一看就懂 |
| chunk_progress 表 | 缺 embedding_model 字段 | 补上该字段 | 支撑模型版本变更检测 |
| 测试覆盖 | Step 2 有测试，其余无 | 每个 Step 明确测试要求 | 生产级质量 |
| Phase 2/3 验收 | 无 | 补全验收标准 | Gate 判断不主观 |
| 时间估算 | Phase 1 9 天 | Phase 1 9 天（不变） | LanceDB 开发体验和 ChromaDB 相当，不增减工期 |

---

## 一、项目定位

### 1.1 一句话定位

**面向 Obsidian 用户的个人知识库 RAG 系统：指定 vault 目录 → 自动索引 → 自然语言检索 → 带引用溯源的精准答案。**

### 1.2 与市面 RAG 项目的差异化

| 维度 | 市面通用 RAG 项目 | 本项目 |
|------|------------------|--------|
| 知识源 | 任意目录 MD | **Obsidian vault 优先**，理解 wikilink/frontmatter/tag/callout |
| 首次使用 | 需要手动跑脚本建索引 | **启动即自动索引**，UI 内进度可视化 |
| 索引可靠性 | 失败重来，浪费 API 费用 | **chunk-level 断点恢复**，只重试失败的 |
| 评估 | 无 | **内置 RAG 评估体系**（hit-rate / MRR / faithfulness） |
| 架构 | 单体 Streamlit | **FastAPI + Streamlit 分层**，API 可独立接入外部工具 |
| 配置 | 需编辑文件 | **UI 面板实时调整** + 配置持久化 |
| 嵌入模型 | 依赖云 API | **本地 BGE-M3 默认**，零 Embedding 费用 |
| 向量存储 | ChromaDB / FAISS / 自选 | **LanceDB**（嵌入式列式存储，内置 FTS，零额外依赖） |
| Obsidian 语法 | 当普通 MD 处理 | **提取 wikilink 做跨文档关联、frontmatter 做结构化过滤、tag 做元数据索引** |

### 1.3 核心目标

| 目标 | 优先级 | 说明 |
|------|--------|------|
| 自然语言检索 Obsidian vault | P0 | 指定 vault 路径 → 搜索 → 答案 + 来源引用 |
| 首次启动零手动步骤 | P0 | 启动 → 自动检测 vault → 自动索引 → 就绪 |
| 关键参数 UI 可配置 | P0 | Top-K / chunk_size / 搜索模式 / 模型选择 |
| 开源友好 | P0 | fork 后改一个路径 + 配 API Key 就能跑 |
| 内置评估体系 | P1 | hit-rate / MRR / faithfulness，配置变更前后 AB 对比 |
| 增量更新 | P1 | vault 内文件变更后自动重新索引变化部分 |
| 断点恢复 | P1 | 索引入库中断后从断点继续，不重复 Embedding |
| API 层 | P2 | FastAPI 端点供外部工具（Alfred / Raycast / iOS 快捷指令）调用 |

---

## 二、Obsidian 知识资产分析

### 2.1 你的 vault 资产盘点

```
~/xiaolei/Shaw/ (Obsidian vault)
├── Agent 落地12条.md               ~80行   ⭐⭐⭐⭐⭐
├── 新员工类比框架.md                ~60行   ⭐⭐⭐⭐⭐
├── 峰谷定价模型.md                  ~40行   ⭐⭐⭐⭐
├── Agent Runtime 组件表.md          ~40行   ⭐⭐⭐⭐⭐
├── *.excalidraw.md                 N个      ❌ 排除（JSON元数据）
└── 附件/                          少量图片  ⚠️ Phase 1 跳过

~/Desktop/rag/                    ~1800行  ⭐⭐⭐⭐⭐
~/Desktop/PM/                     ~2500行  ⭐⭐⭐⭐
~/Desktop/work/Agent/             ~6000行  ⭐⭐⭐⭐⭐
~/Desktop/work/Python基础/         ~620行   ⭐⭐⭐

总计有效 MD：~17篇，约 11,000+ 行
```

### 2.2 Obsidian 特有语法的 RAG 增强价值

| Obsidian 语法 | 原始形态 | 分块时提取 | RAG 检索收益 |
|-------------|---------|-----------|-------------|
| `[[wikilink]]` | `[[Agent 架构选型]]` | 链接目标文件名 | 跨文档关联检索 |
| `![[embed]]` | `![[Runtime框架#组件表]]` | 嵌入目标 + 章节锚点 | 被嵌入段落加入当前 chunk 上下文 |
| `#tag` | `#agent/runtime` | 分级标签 | metadata filtering |
| frontmatter | `---\ntags: [a,b]\naliases: [x]\n---` | 结构化字段 | 多维过滤 + 别名归一化 |
| callout | `> [!note] 核心原则` | callout 类型 + 内容 | 保留语义块完整性 |
| dataview | `\`\`\`dataview\n...\n\`\`\`` | 跳过或标记 | 查询语句无知识价值，可标记类型 |

### 2.3 排除规则

```
scanner 默认排除：
  - *.excalidraw.md        # Excalidraw 绘图元数据（JSON）
  - .obsidian/workspace*.json
  - .obsidian/workspace.json
  - .trash/                # Obsidian 回收站
  - .DS_Store
  - 图片/视频/音频          # Phase 1 跳过二进制文件，Phase 2 接入多模态
```

---

## 三、存储路径约定（v3.0 新增）

所有运行时数据统一存放在项目根目录下的 `data/` 目录，`data/` 追加到 `.gitignore`。

```
rag-personal-knowledge-system/
├── data/                      ← .gitignore，所有运行时数据
│   ├── lancedb/               # LanceDB 向量 + 全文索引
│   │   ├── chunks.lance/      #   主表：chunk 向量 + FTS 索引 + metadata
│   │   └── _versions/         #   LanceDB 自动版本管理
│   └── rag.db                 # SQLite（索引状态 + 配置 + 搜索历史）
├── config/
├── src/
└── ...
```

| 数据 | 存储位置 | 格式 | 说明 |
|------|----------|------|------|
| 向量索引 + 全文索引 | `data/lancedb/` | Lance 列式 | LanceDB 管理，包含 chunk 向量、全文索引、metadata |
| 索引状态 + chunk 进度 | `data/rag.db` | SQLite | 三张表：index_state / chunk_progress / doc_manifest |
| 搜索历史 | `data/rag.db` | SQLite | search_history 表 |
| 配置持久化 | `data/rag.db` | SQLite | config_profiles 表 |

---

## 四、配置文件职责划分（v3.0 新增）

三个配置文件分工明确，用户不会困惑"我该改哪个"。

| 文件 | 放什么 | 不放过什么 | 示例 |
|------|--------|-----------|------|
| `.env` | **Secrets + 个人路径** | 业务参数（chunk_size、top_k） | `OBSIDIAN_VAULT_PATH`、`LLM_API_KEY`、`ANYSEARCH_API_KEY` |
| `config/config.yaml` | **业务配置** | Secrets | `chunk_size: 512`、`top_k: 5`、`model: deepseek-v4-pro`、`temperature: 0.3` |
| `profiles/*.yaml` | **Provider 组合预设** | Secrets | 套餐 A：LanceDB + DeepSeek + BGE-M3；套餐 B：LanceDB + Ollama + BGE-M3 |

**优先级链（后者覆盖前者）：**

```
代码默认值 < profiles/*.yaml < config/config.yaml < .env < UI 面板实时调整
```

**为什么这样分：**

- `.env` 不进 Git（`gitignore`），secrets 安全
- `config/config.yaml` 进 Git，团队共享同一套参数基线
- `profiles/*.yaml` 是**套餐**概念：用户不改 YAML 细节，只在 `.env` 里选套餐名

```bash
# .env 示例
OBSIDIAN_VAULT_PATH=~/xiaolei/Shaw
LLM_API_KEY=sk-xxxx
PROFILE=default          # 使用 profiles/default.yaml 的 provider 组合
```

---

## 五、首次使用全流程体验设计

**用户从克隆到搜出第一个结果，全程不离开 UI，零手动脚本步骤。**

### 5.1 用户视角全流程

```
Step 1: 克隆安装
  git clone https://github.com/xxx/rag-pkm
  cd rag-pkm
  pip install -r requirements.txt

Step 2: 配置（只改一个文件）
  cp .env.example .env
  # 编辑 .env：
  #   OBSIDIAN_VAULT_PATH=~/xiaolei/Shaw     ← 只需改这一个
  #   LLM_API_KEY=sk-xxxx                    ← 可选，不配也能看示例

Step 3: 启动
  make start
  # 或手动：python scripts/start.py
  # 内部逻辑：同时启动 FastAPI(8000) + Streamlit(8501)，浏览器自动打开 Streamlit

  ┌────────────────────────────────────────────────────────┐
  │  🧠 RAG Personal Knowledge Manager                     │
  │                                                        │
  │  ┌──────────────────────────────────────────────────┐  │
  │  │  🔍 检测到 Obsidian vault：~/xiaolei/Shaw          │  │
  │  │                                                    │  │
  │  │  📂 扫描完成：17 篇文档，342 个文本块               │  │
  │  │  🔢 正在向量化...  ████████░░  180/342 (52%)       │  │
  │  │  ⏱ 预计剩余 45 秒                                  │  │
  │  │                                                    │  │
  │  │  💡 首次索引只需一次，后续启动增量更新，秒级完成     │  │
  │  └──────────────────────────────────────────────────┘  │
  │                                                        │
  │  （索引期间搜索框置灰，完成后自动激活）                  │
  └────────────────────────────────────────────────────────┘
```

### 5.2 启动脚本（scripts/start.py）

```python
"""启动脚本：同时拉起 FastAPI + Streamlit，浏览器自动打开 Streamlit"""
import subprocess, time, sys, webbrowser

def start():
    # 启动 FastAPI（后台）
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--port", "8000"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    # 等待 FastAPI 就绪
    for _ in range(30):
        try:
            import httpx
            httpx.get("http://localhost:8000/api/status", timeout=1)
            break
        except:
            time.sleep(1)
    else:
        print("⚠️ FastAPI 启动超时，请检查日志")
        api.kill()
        return

    # 启动 Streamlit
    streamlit = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "src/ui/app.py", "--server.port", "8501"]
    )

    # 打开浏览器
    time.sleep(2)
    webbrowser.open("http://localhost:8501")

    print("✅ FastAPI: http://localhost:8000 | Streamlit: http://localhost:8501")
    api.wait()
    streamlit.wait()

if __name__ == "__main__":
    start()
```

### 5.3 索引状态管理（SQLite）

```sql
-- 索引状态表：启动时先查这个表决定行为
CREATE TABLE index_state (
    id          INTEGER PRIMARY KEY,
    vault_path  TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL,  -- 'idle' | 'indexing' | 'ready' | 'error'
    doc_count   INTEGER,
    chunk_count INTEGER,
    started_at  TEXT,
    finished_at TEXT,
    error_msg   TEXT
);

-- Chunk 级别进度表：支撑断点恢复
CREATE TABLE chunk_progress (
    chunk_id        TEXT PRIMARY KEY,     -- hash(source_file + chunk_index)
    source_file     TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content_hash    TEXT NOT NULL,        -- sha256(chunk_content)
    embedding_model TEXT NOT NULL,        -- ★ v3.0 新增：记录 Embedding 模型版本
    status          TEXT NOT NULL,        -- 'pending' | 'embedded' | 'skipped'
    created_at      TEXT
);

-- 文档清单表：支撑增量更新判断
CREATE TABLE doc_manifest (
    source_file  TEXT PRIMARY KEY,
    file_hash    TEXT NOT NULL,           -- sha256(文件内容)
    file_mtime   REAL NOT NULL,
    chunk_count  INTEGER,
    indexed_at   TEXT
);
```

**embedding_model 字段使用场景：**

```
用户从 BGE-M3 切换到 BGE-large 后启动：
  → IndexManager 读取 chunk_progress，发现 embedding_model 不一致
  → 自动触发全量重索引（向量维度/语义空间变了，旧向量无效）
  → 未配置切换的用户无影响，字段始终为 'BAAI/bge-m3'
```

### 5.4 启动时的判断逻辑（index_manager.py 核心）

```python
class IndexManager:
    def on_startup(self, vault_path: str) -> IndexDecision:
        """
        返回四种决策之一：
        - FIRST_INDEX:   首次启动，state 表无记录 → 全量索引
        - INCREMENTAL:   有记录，但文件有变更 → 只索引变更文件
        - RESUME:        上次索引中断 → 从断点继续
        - REINDEX:       检测到 embedding_model 变更 → 全量重建
        - SKIP:          无变更 → 直接就绪
        """
        state = self.db.get_index_state(vault_path)

        if state is None:
            return IndexDecision.FIRST_INDEX

        if state.status == 'indexing':
            return IndexDecision.RESUME

        # ★ v3.0：检测 embedding 模型是否变更
        current_model = self.embedder.model_name
        last_model = self.db.get_last_embedding_model()
        if last_model and last_model != current_model:
            return IndexDecision.REINDEX

        changed_files = self._detect_changes(vault_path, state)
        if changed_files:
            return IndexDecision.INCREMENTAL

        return IndexDecision.SKIP
```

### 5.5 增量更新策略（基于 chunk hash 的内容寻址）

```
检测到 3 个文件变更：
  agent.md (修改) → 重新分块 → 12 chunks
  new-note.md (新增) → 分块 → 5 chunks
  old-note.md (删除) → 从 DB 中查其 chunks → 3 个旧 chunk_id

增量更新流程：
  ① agent.md 的 12 个新 chunk：
     - chunk_hash 匹配 DB 中已有的 → status='skipped'（跳过 Embedding）
     - chunk_hash 不匹配 → status='pending' → Embedding → 入库
  ② new-note.md 的 5 个新 chunk：
     - DB 中无此文件记录 → 全部 status='pending' → Embedding → 入库
  ③ old-note.md 的 3 个旧 chunk：
     - 新分块结果中不存在 → 从 LanceDB 中删除
```

### 5.6 断点恢复（chunk-level 幂等）

```
场景：全量索引进行到 200/342 chunks 时网络断开（BGE-M3 本地模型不会断网，
      但进程可能因 OOM / 系统休眠 / 手动 kill 而中断）

状态：
  chunk_progress 表：
    c001~c200  status='embedded'
    c201~c342  status='pending'

下次启动时：
  IndexManager.on_startup() → 读 state.status='indexing' → RESUME
  → 查询 chunk_progress WHERE status='pending'
  → 只处理 c201~c342，已经 embedded 的不重复处理
  → 全部完成后 state.status='ready'
```

---

## 六、系统架构设计

### 6.1 组件全景

```
┌──────────────────────────────────────────────────────────────┐
│                     用户界面层（Streamlit）                     │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌────────────┐ │
│  │ 检索面板  │  │ 配置面板    │  │ 文档管理  │  │ 索引进度    │ │
│  │          │  │            │  │          │  │            │ │
│  │ 问答+引用 │  │ chunk/size │  │ 文档列表  │  │ 进度条+状态 │ │
│  │ 来源跳转  │  │ search模式  │  │ 重新索引  │  │ 错误重试    │ │
│  │ 评估模式  │  │ 模型/温度   │  │ 排除规则  │  │ 增量状态    │ │
│  └─────┬────┘  └─────┬──────┘  └────┬─────┘  └──────┬─────┘ │
│        │             │              │               │        │
└────────┼─────────────┼──────────────┼───────────────┼────────┘
         │             │              │               │
         └─────────────┴──────┬───────┴───────────────┘
                              │  HTTP (localhost)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     API 层（FastAPI）                          │
│                                                              │
│  GET  /api/status            → 索引状态 + 文档统计             │
│  POST /api/search            → 检索 + LLM 生成 + 引用          │
│  POST /api/index             → 触发索引（全量/增量）            │
│  GET  /api/index/progress    → 索引进度查询                    │
│  POST /api/evaluate          → 评估检索质量                    │
│  GET  /api/documents         → 已索引文档列表                  │
│                                                              │
│  （Streamlit 通过 httpx 调用这些端点，不直连 pipeline）         │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                      RAG 编排层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ 检索路由  │  │ 混合搜索  │  │ Prompt 组装   │  │ 评估引擎   │ │
│  │          │  │          │  │              │  │           │ │
│  │ 向量搜索  │  │LanceDB   │  │ 引用注入      │  │ hit-rate   │ │
│  │ FTS 搜索 │  │hybrid    │  │ 来源标注      │  │ MRR       │ │
│  │ 混合模式  │  │search()  │  │ token 裁剪   │  │ faithful  │ │
│  └──────────┘  └──────────┘  └──────────────┘  └───────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                      数据管道层                                │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │扫描器    │  │分块引擎   │  │Embedding   │  │索引管理器     │ │
│  │          │  │          │  │            │  │              │ │
│  │vault扫描 │  │MD结构感知 │  │本地BGE-M3  │  │状态检测       │ │
│  │wikilink  │  │递归切割   │  │批量+重试   │  │增量判断       │ │
│  │排除规则  │  │frontmatter│  │缓存去重    │  │断点恢复       │ │
│  │变更检测  │  │tag提取    │  │            │  │模型版本检测    │ │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────┐
│                         存储层                                 │
│  ┌─────────────────┐  ┌────────────────┐  ┌──────────────┐   │
│  │ LanceDB          │  │ SQLite         │  │ 源文件 (.md) │   │
│  │                  │  │                │  │              │   │
│  │ 向量索引          │  │ index_state    │  │ 文件系统只读  │   │
│  │ 全文索引（FTS）   │  │ chunk_progress │  │              │   │
│  │ metadata         │  │ doc_manifest   │  │              │   │
│  │ data/lancedb/    │  │ search_history │  │              │   │
│  │                  │  │ config_profiles│  │              │   │
│  │                  │  │ data/rag.db    │  │              │   │
│  └─────────────────┘  └────────────────┘  └──────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 数据流（检索路径）

```
用户输入 Query: "Agent 架构选型时应该怎么考虑存储？"
    │
    ▼
┌──────────────┐
│ API 层接收    │ → POST /api/search {query, config}
└──────┬───────┘
       ▼
┌──────────────┐
│ Query 预处理  │ → Phase 1: 直接使用; Phase 2: 改写/扩展
└──────┬───────┘
       ▼
┌──────────────┐
│ Embedding    │ → BGE-M3 本地模型 → query_vector
└──────┬───────┘
       ▼
┌──────────────┐
│ LanceDB       │ → Phase 1: table.search(query_vector).limit(top_k)
│ 向量检索      │     返回 top_k 个最相似 chunk + metadata
│              │
│ 混合检索      │ → Phase 2: table.search(query_vector, "content", query_text)
│ （Phase 2）   │     .hybrid_search().limit(top_k)
│              │     LanceDB 在内部同时跑向量 + FTS，返回融合排序结果
│              │     不需要独立的 Whoosh / BM25 组件
└──────┬───────┘
       ▼
┌──────────────┐
│ Prompt 组装   │ → 系统角色 + chunks + 引用格式要求
│              │ → Token 预算检查：超出则裁剪低分 chunk
└──────┬───────┘
       ▼
┌──────────────┐
│ LLM 生成      │ → DeepSeek API (或其他配置的模型)
└──────┬───────┘
       ▼
┌──────────────┐
│ 引用注入      │ → 在答案中插入 [1] [2] 标记
│              │ → 附带来源信息：[1] agent-12-principles.md § 存储选型
└──────┬───────┘
       ▼
┌──────────────┐
│ 响应返回      │ → JSON: {answer, sources, retrieval_stats}
└──────────────┘
```

### 6.3 LanceDB 表设计

```python
import lancedb
import pyarrow as pa

db = lancedb.connect("data/lancedb")

# 主表 schema
schema = pa.schema([
    ("vector", pa.list_(pa.float32(), 1024)),  # BGE-M3 默认 1024 维
    ("content", pa.string()),                   # chunk 文本（用于 FTS）
    ("source_file", pa.string()),
    ("heading_path", pa.string()),
    ("chunk_index", pa.int32()),
    ("chunk_hash", pa.string()),
    ("tags", pa.string()),                      # JSON array as string
    ("wikilinks", pa.string()),                 # JSON array as string
    ("frontmatter", pa.string()),               # JSON object as string
    ("char_count", pa.int32()),
])

table = db.create_table("chunks", schema=schema)

# Phase 1: 向量索引 + FTS 索引同时建
# 原因：FTS 索引对已有数据写开销可忽略，Phase 1 建了 Phase 2 直接用
#      避免 Phase 2 schema migration 的兼容性问题
table.create_index(num_sub_vectors=96)
table.create_fts_index("content")

# Phase 1: 只调向量搜索
# results = table.search(query_vector).limit(5).to_list()

# Phase 2: 切换为混合搜索一行代码
# results = table.search(query_vector).hybrid_search("content", query_text).limit(5).to_list()
```

**为什么 LanceDB 比 ChromaDB 更适合这个项目：**

| 维度 | ChromaDB | LanceDB | 影响 |
|------|----------|---------|------|
| 存储引擎 | SQLite（行式） | Lance（列式，Apache Arrow 原生） | 向量数据天然适合列式存储 |
| 数据可靠性 | 有损坏报告 | 版本化设计，写入原子 | 个人 vault 越长越重要 |
| 全文搜索 | 无（需 Whoosh） | **内置 FTS** | 减一个依赖 |
| 混合搜索 | 自己融合两路结果 | **原生 hybrid_search()** | API 更干净 |
| 嵌入方式 | pip install | pip install | 同为嵌入式，零额外依赖 |
| 索引方式 | 自动 IVFFlat | 可选手动/自动 | 小数据集无差异 |
| 社区成熟度 | 更老（2022） | 更年轻（2023） | 个人量级无差异 |
| 备份 | 复制 persist 目录 | 复制 data/lancedb/ | 无差异 |

---

## 七、技术选型

### 7.1 选型总表

| 组件 | v2.0 选型 | v3.0 选型 | 变动原因 |
|------|----------|----------|----------|
| 向量数据库 | ChromaDB | **LanceDB** | 数据可靠性 + 内置 FTS |
| 关键词搜索 | Whoosh | **LanceDB 内置 FTS** | 减依赖，统一入口 |
| Embedding | 本地 BGE-M3 | **本地 BGE-M3**（不变） | |
| LLM | DeepSeek API | **DeepSeek API**（不变） | |
| UI | Streamlit | **Streamlit**（不变） | |
| API 层 | 无 → FastAPI | **FastAPI**（不变） | |
| 配置校验 | Pydantic v2 | **Pydantic v2**（不变） | |
| 增量监听 | watchdog | **watchdog + chunk hash**（不变） | |
| 重排 | BGE-Reranker 本地 (P2) | **BGE-Reranker 本地**（不变） | |

### 7.2 为什么不直接用 LangChain / LlamaIndex

| 维度 | LangChain/LlamaIndex | 自封装 |
|------|---------------------|--------|
| 学习曲线 | 高（框架概念多） | 低（就是 Python 函数调用） |
| 调试透明度 | 低（黑盒抽象层） | 高（每一步可见、可打断点） |
| 定制灵活性 | 受框架约束 | 完全自由 |
| Obsidian 语法解析 | 不支持，需自己写 loader | 原生支持 |
| 依赖体积 | 大（100+ 传递依赖） | 小（10 个以内核心依赖） |
| 本项目匹配度 | 不适合 | **完全匹配** |

### 7.3 核心依赖清单（Phase 1）

```
# 向量存储 + 全文搜索
lancedb>=0.12.0
pyarrow>=15.0.0

# Embedding
sentence-transformers>=3.0.0

# API + UI
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
streamlit>=1.33.0
httpx>=0.27.0

# LLM
openai>=1.30.0  # DeepSeek API 兼容 OpenAI 协议

# 配置
pyyaml>=6.0
pydantic>=2.0
python-dotenv>=1.0

# 工具
watchdog>=4.0

# 去掉了：chromadb, whoosh
```

---

## 八、分阶段执行计划

### Phase 1：MVP —「开箱即搜」（预计 9 天）

#### 目标

用户克隆项目 → 配 vault 路径 → `make start` → 自动索引 → 自然语言检索 → 带引用答案。

#### 技术范围

- 向量搜索 only（Phase 2 再加混合搜索）
- 本地 BGE-M3 Embedding
- LanceDB 嵌入式向量存储（`data/lancedb/`）
- SQLite 索引状态管理（`data/rag.db`）
- FastAPI + Streamlit 分层
- 首次启动自动索引 + 断点恢复
- `scripts/start.py` 一键启动
- 基础评估端点（hit-rate / MRR）

#### 执行步骤

**Step 1：项目骨架 + 配置系统（1.5 天）**

目标：完整的项目目录 + 配置加载 + 校验 + Profile 切换 + 启动脚本。

产出：
```
rag-personal-knowledge-system/
├── config/
│   ├── config.yaml              # 主配置（vault路径、LLM provider、chunk参数）
│   ├── config.schema.json       # JSON Schema 校验
│   └── config_schema.py         # Pydantic v2 模型 + 校验逻辑
├── profiles/
│   ├── default.yaml             # LanceDB + DeepSeek + BGE-M3 本地
│   ├── ollama-offline.yaml      # LanceDB + Ollama + BGE-M3 本地（完全离线）
│   └── openai.yaml              # LanceDB + OpenAI + OpenAI Embedding
├── .env.example                 # API Key 模板（提交 Git）
├── .env                         # 实际 Key + OBSIDIAN_VAULT_PATH（gitignore）
├── .gitignore                   # 含 data/ 目录
├── README.md
├── requirements.txt
├── pyproject.toml
├── Makefile                     # make start / make test / make clean
├── scripts/
│   └── start.py                 # ★ v3.0 新增：一键启动 FastAPI + Streamlit
├── tests/                       # 测试目录（Phase 1 从 Step 1 开始建）
│   ├── __init__.py
│   ├── conftest.py              # 共享 fixtures
│   ├── unit/
│   │   ├── test_config_loader.py
│   │   ├── test_scanner.py
│   │   ├── test_obsidian_parser.py
│   │   ├── test_chunker.py
│   │   ├── test_embedder.py
│   │   ├── test_index_manager.py
│   │   ├── test_retriever.py
│   │   └── test_generator.py
│   ├── integration/
│   │   ├── test_lancedb_store.py
│   │   ├── test_index_pipeline.py
│   │   └── test_search_pipeline.py
│   └── fixtures/
│       └── sample_vault/        # 模拟 Obsidian vault 结构
├── docs/
│   └── samples/                 # 开源示例知识库
│       ├── 01-rag-basics.md
│       ├── 02-agent-architecture.md
│       └── 03-embedding-guide.md
└── src/
    ├── __init__.py
    ├── config_loader.py
    │
    ├── interfaces/              # 抽象接口层
    │   ├── __init__.py
    │   ├── vector_store.py      #   VectorStore(ABC)
    │   ├── llm.py               #   LLMProvider(ABC)
    │   └── embedding.py         #   EmbeddingProvider(ABC)
    │
    ├── vector_stores/
    │   ├── __init__.py          #   Provider 注册工厂
    │   └── lance_store.py       # ★ 默认实现（替换 chroma_store.py）
    │
    ├── llm_providers/
    │   ├── __init__.py
    │   ├── deepseek.py
    │   └── openai_compatible.py
    │
    ├── embedding_providers/
    │   ├── __init__.py
    │   └── local_bge_m3.py      # sentence-transformers 本地 BGE-M3
    │
    ├── pipeline/
    │   ├── __init__.py
    │   ├── scanner.py           # Obsidian vault 扫描器
    │   ├── obsidian_parser.py   # wikilink/frontmatter/tag 解析
    │   ├── chunker.py           # MD 结构感知分块引擎
    │   ├── embedder.py          # Embedding 批量处理 + 重试
    │   ├── indexer.py           # 索引编排（扫描→分块→Embed→入库）
    │   ├── index_manager.py     # 索引生命周期管理（含 embedding_model 版本检测）
    │   ├── retriever.py         # 检索引擎（Phase 1: 向量搜索; Phase 2: 混合搜索）
    │   └── generator.py         # Prompt 组装 + LLM 调用 + 引用注入
    │
    ├── api/                     # FastAPI 层
    │   ├── __init__.py
    │   ├── main.py              # FastAPI app + 路由注册
    │   ├── routes/
    │   │   ├── search.py
    │   │   ├── index.py
    │   │   ├── status.py
    │   │   └── evaluate.py
    │   └── models.py            # Pydantic 请求/响应模型
    │
    ├── ui/
    │   └── app.py               # Streamlit（通过 httpx 调 FastAPI）
    │
    ├── db/                      # SQLite 管理
    │   ├── __init__.py
    │   ├── connection.py
    │   └── schema.py            # 建表 + 迁移（含 embedding_model 字段）
    │
    └── utils/
        ├── __init__.py
        └── logger.py
```

**测试要求：**
- `test_config_loader.py`：验证三层优先级链（profiles < config.yaml < .env）+ Schema 校验

---

**Step 2：Obsidian 扫描器 + MD 分块引擎（1.5 天）**

目标：扫描 vault 目录，解析 Obsidian 语法，产出结构化 chunks。

**scanner.py 核心逻辑：**

```python
class ObsidianScanner:
    def scan(self, vault_path: str) -> list[ScannedDocument]:
        """
        1. 递归扫描 vault_path 下所有 .md 文件
        2. 应用排除规则
        3. 对每个 .md 文件：
           a. 读取全文
           b. 提取 frontmatter
           c. 提取 [[wikilink]] 链接列表
           d. 提取 #tag 标签列表
        4. 返回 ScannedDocument 列表
        """
```

**obsidian_parser.py 核心逻辑：**

```python
class ObsidianParser:
    def parse(self, content: str, file_path: str) -> ParsedDocument:
        """
        - frontmatter: 正则匹配 ^---\n(.*?)\n---
        - wikilinks:   正则匹配 \[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]
        - tags:        正则匹配 (?<!\S)#([a-zA-Z\u4e00-\u9fa5][\w/-]*)
        - callouts:    正则匹配 > \[!(\w+)\]([+-]?)\s*(.*)
        - embeds:      正则匹配 !\[\[([^\]]+)\]\]
        """
```

**chunker.py 核心逻辑——MD 结构感知分块：**

```
分块规则（优先级从高到低）：

1. 以 ## 二级标题为逻辑分界点（保留 heading_path 作为 chunk metadata）
2. 每个 ## section 内按 \n\n（段落）拆分
3. 段落 < chunk_size → 合并相邻段落直到接近 chunk_size
4. 段落 > chunk_size → 按 sentence（。！？\n）拆分
5. 句子 > chunk_size（代码块等极端情况） → 按字符截断
6. overlap：相邻 chunk 间以完整 sentence 为单位重叠（overlap_sentences = 2）

chunk metadata:
{
  "source_file": "Agent-Runtime框架.md",
  "heading_path": "Agent Runtime > 组件时序表 > 存储组件",
  "chunk_index": 7,
  "chunk_hash": "sha256...",
  "tags": ["agent/runtime", "architecture"],
  "wikilinks": ["Agent架构选型", "本体论框架"],
  "frontmatter": {"title": "Agent Runtime", "created": "2026-03-15"}
}
```

**测试要求：**
- `test_scanner.py`：用 `tests/fixtures/sample_vault/` 验证扫描 + 排除规则
- `test_obsidian_parser.py`：验证 5 种语法（wikilink/frontmatter/tag/callout/embed）提取准确性
- `test_chunker.py`：验证标题层级保持、overlap 边界、代码块不拦腰截断、单段落 > chunk_size 时的 sentence 级拆分

---

**Step 3：Embedding + LanceDB 入库管道（1.5 天）**

目标：本地 BGE-M3 批量 Embedding，LanceDB 幂等入库 + FTS 索引建立，失败可恢复。

**关键代码：**

```python
# lance_store.py
class LanceVectorStore(VectorStore):
    def __init__(self, db_path: str = "data/lancedb"):
        self.db = lancedb.connect(db_path)
        self.table = None  # 懒初始化

    def ensure_table(self, dim: int = 1024):
        if self.table is None:
            schema = pa.schema([
                ("id", pa.string()),
                ("vector", pa.list_(pa.float32(), dim)),
                ("content", pa.string()),
                ("source_file", pa.string()),
                # ... 其他 metadata 字段
            ])
            self.table = self.db.create_table("chunks", schema, exist_ok=True)

    def add_chunks(self, chunks: list[dict]):
        """批量写入。LanceDB 写入是原子的——不会出现'部分写入'的中间态"""
        self.table.add(chunks)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """向量搜索"""
        return self.table.search(query_vector).limit(top_k).to_list()

    def search_hybrid(self, query_vector, query_text, top_k=5) -> list[dict]:
        """混合搜索（Phase 2 启用）"""
        return (self.table
                .search(query_vector)
                .hybrid_search("content", query_text)
                .limit(top_k)
                .to_list())
```

**测试要求：**
- `test_lancedb_store.py`：验证表创建、chunk 写入、向量搜索返回正确结果、重复写入同一 chunk 的去重行为
- `test_embedder.py`：验证批量 Embedding 维度正确（1024）、batch_size 分批、单 batch 失败重试
- `test_index_manager.py`：验证四种启动决策（FIRST_INDEX / INCREMENTAL / RESUME / SKIP）+ embedding_model 变更触发 REINDEX

---

**Step 4：检索 + LLM 生成引擎（1 天）**

目标：LanceDB 向量检索 + Prompt 组装 + 引用注入 + Token 预算管理 + 检索失败短路。

**retriever.py：**

```python
class Retriever:
    def search(self, query: str, top_k: int = 5,
               mode: str = "vector",
               similarity_threshold: float = 0.6,
               tag_filter: list[str] | None = None
               ) -> list[SearchResult]:
        """
        Phase 1: vector search only
        Phase 2: + hybrid search (LanceDB native)
        tag_filter 示例：['agent/runtime'] → 只检索该标签下的文档
        """

    async def search_async(self, query: str, ...) -> list[SearchResult]:
        """
        ★ v3.0 新增：async 包装。
        LanceDB Python 客户端是同步的，FastAPI 里直接调用会阻塞事件循环。
        用 asyncio.to_thread 把同步调用丢到线程池执行。
        """
        return await asyncio.to_thread(self.search, query, ...)
```

**generator.py —— Prompt 模板：**

```python
SYSTEM_PROMPT = """你是 Obsidian 个人知识库助手。你的回答严格基于以下检索到的知识片段。
如果知识片段不包含回答所需信息，直接说"我的知识库中没有相关信息"，绝不编造。

## 回答规则
1. 用自然、专业的中文回答用户问题
2. 在答案中使用 [N] 标注引用来源（N 是知识片段的编号）
3. 如果多个片段涉及同一观点，可以引用多个编号
4. 不引入知识片段中没有的外部知识
5. 知识片段可能包含 Obsidian 特有的链接语法 [[xxx]]，在回答中保留为纯文本"""

USER_PROMPT_TEMPLATE = """## 知识片段
{sources}

## 用户问题
{query}

请基于以上知识片段回答问题，并在答案中标注引用来源。"""
```

**Token 预算管理：**

```python
def _assemble_prompt(self, chunks: list[SearchResult],
                     query: str, max_tokens: int = 6000) -> str:
    """
    1. 按分数从高到低排列 chunk
    2. 逐个添加 chunk → 计算当前 prompt token 数
    3. 超出 max_tokens → 丢弃低分 chunk
    4. 保证至少保留 3 个 chunk：
       - 如果不足 3 个 chunk：对最长 chunk 按句子截断，腾出空间
       - LLM 需要至少 3 个上下文片段才能做出有区分度的判断
       - 只有 1~2 个 chunk 时截断也比全丢弃好
    """
```

**检索失败短路逻辑（★ v3.0 新增）：**

```python
# generator.py — retriever 返回空结果时直接返回，不调用 LLM
def generate(self, query: str, config: SearchConfig) -> SearchResponse:
    results = self.retriever.search(query, **config.dict())

    # 短路：空结果不调 LLM，省 token + 避免 LLM 面对空上下文时自由发挥
    if not results:
        return SearchResponse(
            answer="我的知识库中没有相关信息。",
            sources=[],
            retrieval_stats={"chunks_found": 0}
        )

    prompt = self._assemble_prompt(results, query)
    answer = self._call_llm(prompt)
    # ... 引用注入 + 响应组装
```

> 设计理由：system prompt 中虽然有"不编造"的约束，但 LLM 面对空上下文时的行为不够确定——有些模型会坦承不知道，有些会开始自由发挥。代码层面短路是最可靠的。

**测试要求：**
- `test_retriever.py`：验证 top_k 截断、similarity_threshold 过滤、tag_filter 过滤、空结果返回空列表
- `test_generator.py`：验证 prompt 模板正确组装、token 预算超限时低分 chunk 被裁剪但至少保留 3 个、空 chunk 列表时不调用 LLM 直接返回"无相关信息"

---

**Step 5：FastAPI 层 + Streamlit 界面（2 天）**

目标：API 端点全部可用，Streamlit 界面调用 API，首次启动自动索引体验完整。

**测试要求：**
- `test_search_pipeline.py`（集成测试）：用 `tests/fixtures/sample_vault/` 索引 → POST /api/search → 验证返回 JSON 结构（answer + sources + stats）
- `test_index_pipeline.py`（集成测试）：全量索引 → kill 进程 → 重启 → 验证断点恢复

---

**Step 6：示例知识库 + 启动引导脚本（1.5 天）**

目标：用户不配 Obsidian vault 也能看效果；配了 vault 的体验全自动。

**启动体验决策树：**

```
make start
    │
    ├─ .env 中配置了 OBSIDIAN_VAULT_PATH？
    │   ├─ 是 → 扫描 vault → 自动索引 → 就绪
    │   └─ 否
    │       ├─ docs/samples/ 存在？
    │       │   ├─ 是 → 自动索引示例数据 → 显示提示
    │       │   └─ 否 → 提示用户配置
    │
    └─ 已索引过？文件有变更？
        └─ 是 → 增量更新（秒级完成）
```

#### Phase 1 验收标准

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | 首次启动自动索引 | `make start` 后自动完成全量索引，搜索框自动激活 |
| 2 | 断点恢复 | 索引进度 50% 时强制 kill，重启后从 50% 继续 |
| 3 | 增量更新 | vault 新增 1 篇 MD → 重启后只索引新文件 |
| 4 | Embedding 模型变更检测 | 切换 embedding_model → 自动全量重索引 |
| 5 | 基础检索 | "Agent 架构选型" → 返回相关段落 |
| 6 | 答案引用 | 答案附带 [1] [2] 标记 + 来源文件路径 + 章节标题 |
| 7 | 参数配置 | 修改 Top-K / chunk_size → 检索结果变化 |
| 8 | 配置持久化 | 重启应用后上次修改的参数仍然生效 |
| 9 | API 独立可用 | `curl -X POST localhost:8000/api/search -d '{"query":"RAG"}'` 返回 JSON |
| 10 | 示例数据可用 | 不配 vault 路径也能搜示例知识库 |
| 11 | 一键启动 | `make start` 同时拉起 FastAPI + Streamlit |
| 12 | 测试通过 | `make test` 全部通过（含单元 + 集成） |

---

### Phase 2：进阶 RAG —「搜得准+看得清」（预计 5 天）

#### 新增组件

| 组件 | 说明 | v3.0 变化 |
|------|------|-----------|
| Query 改写 | 用户模糊提问 → LLM 改写为更精确的搜索 Query | 不变 |
| 混合搜索 | ~~Whoosh BM25 + 向量搜索双路融合~~ → **LanceDB 原生 hybrid_search** | ★ 简化：一个 API 调搞定 |
| 重排 | 本地 BGE-Reranker 对 Top-K 结果重排序 | 不变 |
| 检索详情面板 | 展示命中块列表 + 分数分布 + 来源分布 | 不变 |
| AB 对比模式 | 同一 Query 两种配置并排显示 | 不变 |
| 历史记录 | SQLite 保存搜索历史 + 可回溯 | 不变 |

**混合搜索实现变化：**

```
v2.0 方案（复杂）：
  向量搜索(ChromaDB) → 结果1
  BM25搜索(Whoosh)  → 结果2
  → RRF 融合 → Top-K
  → （可选）BGE-Reranker 重排

v3.0 方案（简洁）：
  LanceDB.table.search(query_vector)
    .hybrid_search("content", query_text)
    .limit(top_k)
    .to_list()
  → （可选）BGE-Reranker 重排
```

#### Phase 2 验收标准

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | 混合搜索生效 | 同一 Query 在 hybrid 模式下召回率 > 纯向量模式 |
| 2 | Query 改写 | 模糊输入 "那个存储的东西怎么写来着" → 自动改写为 "Agent 架构中的存储组件选型" |
| 3 | 重排提升 | BGE-Reranker 重排后 Top-3 相关度 > 重排前 |
| 4 | AB 对比 | 并排展示两种配置的结果，差异可视化 |
| 5 | 检索详情面板 | 展示命中块分数条形图 + 来源文件分布饼图 |
| 6 | 历史记录 | 搜索历史可回溯，点击历史项重新加载 |

---

### Phase 3：生产加固（预计 3 天，可选）

| 功能 | 说明 | v3.0 变化 |
|------|------|-----------|
| 增量监听 | watchdog 监听 vault 文件变更 → 自动增量索引 | 不变 |
| 语义缓存 | 相似 Query 直接返回缓存结果 | 不变 |
| 评估面板 | UI 内使用内置评估体系对检索质量打分 | 不变 |
| 配置 Profile 管理 | 保存/切换/导出 Profile | 不变 |
| 导出报告 | 检索结果导出 Markdown | 不变 |
| LanceDB 数据备份 | `make backup` 一键备份 `data/` 目录 | ★ 新增 |

#### Phase 3 验收标准

| # | 验收项 | 通过标准 |
|---|--------|----------|
| 1 | 自动增量索引 | vault 文件保存后 5 秒内自动更新索引 |
| 2 | 语义缓存 | 重复 Query 命中缓存，响应时间 < 100ms |
| 3 | 评估面板 | UI 内运行评估，显示 hit-rate / MRR / faithfulness |
| 4 | Profile 切换 | 切换 Profile 后检索行为发生变化 |
| 5 | 数据备份恢复 | `make backup` → 删除 data/ → `make restore` → 索引恢复 |

---

## 九、开源化设计

### 9.1 用户上手路径（5 分钟）

```
git clone → pip install → 改 .env 里一个路径 → make start → 自动索引 → 搜索
```

### 9.2 Provider 扩展接口

任何人实现 `VectorStore` / `LLMProvider` / `EmbeddingProvider` 接口即可注册新 Provider。默认提供：

| Provider | 接口 | 实现 |
|----------|------|------|
| LanceVectorStore | VectorStore(ABC) | `src/vector_stores/lance_store.py` |
| DeepSeekProvider | LLMProvider(ABC) | `src/llm_providers/deepseek.py` |
| OpenAICompatibleProvider | LLMProvider(ABC) | `src/llm_providers/openai_compatible.py` |
| LocalBGEM3Embedder | EmbeddingProvider(ABC) | `src/embedding_providers/local_bge_m3.py` |

---

## 十、关键设计决策记录

| 决策 | v2.0 | v3.0 | 变动原因 |
|------|------|------|----------|
| 向量数据库 | ChromaDB | **LanceDB** | 数据可靠性 + 内置 FTS |
| 关键词搜索 | Whoosh | **LanceDB 内置 FTS** | 减依赖，统一入口 |
| 混合搜索实现 | 双路 RRF 融合 | **LanceDB hybrid_search()** | API 简洁 |
| RAG 框架 | 自封装 | 自封装（不变） | |
| Embedding | 本地 BGE-M3 | 本地 BGE-M3（不变） | |
| LLM | DeepSeek API | DeepSeek API（不变） | |
| UI | Streamlit + FastAPI | Streamlit + FastAPI（不变） | |
| 索引触发 | 首次启动自动检测 | 首次启动自动检测（不变） | |
| 索引可靠性 | chunk-level 断点恢复 | chunk-level 断点恢复 + **模型版本检测** | |
| 增量更新 | chunk hash 内容寻址 | chunk hash 内容寻址（不变） | |
| 启动方式 | 未明确 | **`make start` 一键启动** | |
| 存储路径 | 未指定 | **`data/lancedb/` + `data/rag.db`** | |
| 配置文件 | 三层但界限模糊 | **三层职责明确表** | |
| 测试 | Phase 1 起建 tests/ | Phase 1 起建 tests/ + **每个 Step 明确测试要求 + 集成测试** | |
| 时间估算 | Phase 1 9天 | Phase 1 9天（不变） | |

---

## 十一、风险与避坑

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| 首次启动全量索引耗时过长 | 中 | 高 | 进度条 + 预计剩余时间 + 后台运行不阻塞 UI |
| ~~ChromaDB 数据损坏~~ | ~~中~~ | ~~高~~ | ★ **已规避**：LanceDB 版本化列式存储，写入原子，可靠性显著优于 ChromaDB |
| LanceDB 版本升级不兼容 | 低 | 中 | `requirements.txt` 锁定版本；data/ 目录可删除重建（源文件是 ground truth） |
| 更换 Embedding 模型（向量不兼容） | 低 | 高 | chunk_progress 表记录 embedding_model，版本变化自动全量重索引 |
| BGE-M3 本地加载内存不足 | 低 | 中 | 自动降级到 BGE-small（384维，内存 < 500MB） |
| Streamlit 并发 session 混乱 | 中 | 中 | 文档说明单用户场景；Phase 3 考虑 FastAPI + React |
| 开源用户 vault 很大（1000+篇） | 中 | 中 | 分块时展示进度 + 可中断 + 断点恢复 |
| 增量更新时用户正在检索 | 低 | 中 | Phase 3 加读写锁；Phase 1 文档说明 |
| 配置文件格式错误 | 低 | 中 | Pydantic 校验在启动时报人类可读错误 |

---

## 十二、落地路线图

```
Day 1-2       Day 3-4       Day 5-6        Day 7-8        Day 9-10
  ┌────┐       ┌────┐       ┌────┐         ┌────┐         ┌────┐
  │Step1│      │Step2│      │Step3│        │Step4│        │Step5│
  │  项目 │────▶│扫描+│─────▶│Embed│───────▶│检索+│───────▶│FastAPI│
  │  骨架 │     │解析+│      │+ 入库│       │LLM生成│      │+ UI  │
  │ 1.5天 │     │分块 │      │1.5天│        │ 1天  │       │ 2天  │
  └────┘       │1.5天│      └────┘         └────┘         └────┘
                └────┘
                                                              │
                    Day 11-12              ┌─────────────────┘
                     ┌────┐                ▼
                     │Step6│          Gate: 用真实 Query
                     │示例+│          通过 12 项验收标准
                     │引导 │          后进入 Phase 2
                     │1.5天│
                     └────┘
                         │
                         ▼
                Phase 1 交付物：
                - 完整 Obsidian-first RAG 系统
                - 首次启动自动索引 + 断点恢复
                - LanceDB 向量存储 + FTS 索引
                - FastAPI + Streamlit 分层 + 一键启动
                - 内置评估端点
                - 示例知识库 + 启动引导
                - tests/ 单元 + 集成测试覆盖
                - README + 5 分钟上手体验
```

---

## 十三、下一步行动

确认本规划后，按 Step 1 → 6 顺序逐步产出代码：

1. [ ] Step 1: 项目骨架 + 配置系统 + `make start` 启动脚本
2. [ ] Step 2: Obsidian 扫描器 + MD 分块引擎 + 单元测试
3. [ ] Step 3: 本地 BGE-M3 Embedding + LanceDB 入库 + index_manager（含模型版本检测 + 集成测试）
4. [ ] Step 4: 检索引擎（LanceDB 向量搜索）+ LLM 生成 + Prompt 模板 + 引用注入 + 单元测试
5. [ ] Step 5: FastAPI 端点 + Streamlit UI（含首次启动自动索引体验 + 集成测试）
6. [ ] Step 6: docs/samples/ 示例知识库 + 环境检测引导 + README
7. [ ] Gate: 12 项验收标准逐一通过

---

*PLAN v3.0 结束。变更摘要：ChromaDB→LanceDB（数据可靠性+内置FTS）、Whoosh→LanceDB原生FTS（减依赖）、存储路径明确化（data/lancedb/+data/rag.db）、一键启动（make start）、配置文件职责划分、SQL Schema补全embedding_model、全Step补测试要求、Phase2/3补验收标准。*
