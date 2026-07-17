<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/xiaoleishaw/retrivault/main/assets/banner-dark.png">
  <img alt="Retrivault" src="https://raw.githubusercontent.com/xiaoleishaw/retrivault/main/assets/banner-light.png">
</picture>

# Retrivault

> **Obsidian-first RAG system** — Point it at your vault, search in natural language, get answers with citations.

[![Tests](https://img.shields.io/badge/tests-131_passing-brightgreen)](https://github.com/xiaoleishaw/retrivault/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-purple)](https://github.com/astral-sh/ruff)
[![LanceDB](https://img.shields.io/badge/vector-LanceDB-orange)](https://lancedb.github.io/lancedb/)

---

## Features

- **Obsidian-aware** — Parses wikilinks, tags, frontmatter, callouts, embeds. Understands your vault, not just plain Markdown.
- **SSE streaming pipeline** — Every step (rewrite → embed → retrieve → rerank → generate) streams to your browser in real time. No black box.
- **Hybrid search** — LanceDB vector + FTS fused. Semantic understanding meets keyword precision.
- **Smart chunking** — MD structure-aware splitting with auto-merge of tiny fragments. No more 10-character chunks.
- **Query rewriting** — DeepSeek Flash generates 3 alternative phrasings, expands the query, validates output, falls back gracefully.
- **Reranking** — BGE-Reranker-v2-m3 Cross-Encoder re-ranks results by true relevance.
- **Built-in evaluation** — Hit Rate, MRR, Recall@5, NDCG@5. Run benchmarks from the UI.
- **Provider-agnostic** — Swap LLM (DeepSeek / OpenAI / Ollama), Embedding (local BGE-M3 / API), and Vector Store via clean ABC interfaces.
- **Index lifecycle** — First index, incremental updates, crash recovery, embedding model change detection. All automatic.

---

## Quick Start (5 minutes)

```bash
# 1. Clone
git clone https://github.com/xiaoleishaw/retrivault.git
cd retrivault

# 2. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure (edit this single file)
cp .env.example .env
# Edit .env — at minimum set your LLM API key:
#   LLM_API_KEY=sk-your-key
#   OBSIDIAN_VAULT_PATH=~/your-obsidian-vault

# 4. Launch
make start
# → Browser opens at http://localhost:8000
# → First visit auto-indexes your vault
# → Start searching
```

> **No vault? No problem.** Retrivault ships with 6 sample documents in `docs/samples/`. Just skip `OBSIDIAN_VAULT_PATH` and it'll use those.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     Browser (Pure HTML/CSS/JS)                  │
│  Home → Search box  |  Results → SSE pipeline console          │
└────────────────────────┬───────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────┴───────────────────────────────────────┐
│                       FastAPI Layer                              │
│  POST /api/search    |  GET /api/search/stream  (SSE events)    │
│  POST /api/index     |  GET /api/status        |  POST /api/eval│
└────────────────────────┬───────────────────────────────────────┘
                         │
┌────────────────────────┴───────────────────────────────────────┐
│                    RAG Pipeline                                  │
│                                                                  │
│  Scanner ──► Parser ──► Chunker ──► Embedder ──► LanceDB        │
│     ↑                      │                    (Vector + FTS)  │
│   Obsidian              Merge tiny              ┌─────────┐     │
│   vault                 fragments               │ Retriever│     │
│                                                 └────┬────┘     │
│    Query Rewriter ──► Reranker ──► Generator ──► SSE │          │
│    (DeepSeek Flash)   (BGE-Reranker) (Your LLM)    Result       │
└─────────────────────────────────────────────────────────────────┘
```

### Pipeline steps visualized

| Step | Model | Latency (avg) |
|------|-------|--------------|
| Query Rewrite | DeepSeek Flash (3 variants) | ~200ms |
| Embedding | BGE-M3 (1024d) | ~400ms |
| Retrieval | LanceDB hybrid search | ~10ms |
| Reranking | BGE-Reranker-v2-m3 | ~350ms |
| Generation | DeepSeek / OpenAI / Ollama | ~4s |
| **Total** | | **~5s** |

---

## Configuration

| File | Purpose | Example |
|------|---------|---------|
| `.env` | Secrets + paths | `LLM_API_KEY`, `OBSIDIAN_VAULT_PATH` |
| `config/config.yaml` | Business params | `chunk_size`, `top_k`, `temperature` |
| `profiles/*.yaml` | Provider presets | `default` (DeepSeek+BGE-M3), `ollama-offline` |

**Priority chain** (latter wins):
```
Defaults < profiles/*.yaml < config/config.yaml < .env < UI panel
```

---

## Evaluation

Retrivault includes a built-in RAG evaluation suite. Open `http://localhost:8000/eval` and click **Run Evaluation**.

```
Hit Rate:   100%   ━━━━━━━━━━━━━━━━━━━━━━
MRR:        1.00   ━━━━━━━━━━━━━━━━━━━━━━
Recall@5:   100%   ━━━━━━━━━━━━━━━━━━━━━━
NDCG@5:     1.00   ━━━━━━━━━━━━━━━━━━━━━━
```

---

## Development

```bash
make test       # 131 tests, ~40s
make test-cov   # With coverage report
make lint       # ruff + mypy
make fix        # Auto-fix code style
```

---

## Project Structure

```
src/
├── interfaces/          # ABC contracts (VectorStore / LLM / Embedding)
├── pipeline/            # Scanner → Parser → Chunker → Retriever → Generator
├── api/                 # FastAPI: routes, models, dependency injection
├── frontend/            # Pure HTML/CSS/JS (no framework dependency)
├── vector_stores/       # LanceDB implementation
├── llm_providers/       # OpenAI-compatible (DeepSeek / OpenAI / Ollama)
├── embedding_providers/ # Local BGE-M3 + API embedder
├── db/                  # SQLite index state management
├── eval/                # Metrics (Hit Rate / MRR / NDCG) + Runner
└── config_loader.py     # 4-layer priority config merge

tests/
├── unit/                # 20+ test files covering every module
├── integration/         # End-to-end pipeline tests
└── fixtures/            # Sample vault + golden dataset
```

---

## FAQ

**Why not just use Obsidian's built-in search?**  
Obsidian search is keyword-based (BM25). Retrivault gives you **semantic search** — it understands intent, not just exact words. Ask "what's the best vector DB for my use case" and it finds the right doc even if no doc says exactly that.

**Do I need an API key?**  
For LLM generation, yes (DeepSeek / OpenAI). For embedding, you can use the local BGE-M3 model for free (requires ~2.2GB download), or the API-based embedder with a SiliconFlow key.

**Is my data sent to third parties?**  
Only what you configure. With local embedding + Ollama LLM, everything stays on your machine.

---

## Roadmap

- [x] Core RAG pipeline (scanner → generator)
- [x] Obsidian syntax parsing (wikilinks, tags, frontmatter)
- [x] SSE streaming with real-time pipeline visualization
- [x] Query rewriting (3-way, validated)
- [x] Built-in evaluation suite
- [ ] Streaming LLM generation (token-by-token)
- [ ] Multi-turn conversation context
- [ ] Multi-modal (images in vaults)
- [ ] Docker support

---

## License

MIT © 2026 [Xiaolei Shaw](LICENSE)
