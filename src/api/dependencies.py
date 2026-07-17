"""依赖注入 — 组件 wiring

FastAPI 端点通过此模块获取已初始化的组件实例。
所有组件在应用启动时创建，关闭时清理。
"""
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.config_loader import AppConfig, get_config
from src.db.schema import init_db
from src.pipeline.chunker import Chunker
from src.pipeline.generator import Generator
from src.pipeline.index_manager import IndexManager
from src.pipeline.indexer import Indexer
from src.pipeline.obsidian_parser import ObsidianParser
from src.pipeline.reranker import Reranker
from src.pipeline.retriever import Retriever
from src.pipeline.scanner import ObsidianScanner
from src.vector_stores.lance_store import LanceVectorStore


class LazyEmbedder:
    """延迟加载的 Embedder 包装器——支持本地模型或远程 API，线程安全"""

    def __init__(self, provider: str, model_name: str,
                 device: str = "cpu", batch_size: int = 32,
                 api_key: str = "", base_url: str = ""):
        self._provider = provider
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._api_key = api_key
        self._base_url = base_url
        self._embedder = None
        import threading
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load_embedder(self):
        if self._embedder is None:
            with self._lock:
                if self._embedder is None:
                    if self._provider == "api":
                        from src.embedding_providers.api_embedder import APIEmbedder
                        self._embedder = APIEmbedder(
                            api_key=self._api_key,
                            base_url=self._base_url,
                            model=self._model_name,
                            batch_size=self._batch_size,
                        )
                    else:
                        from src.embedding_providers.local_bge_m3 import LocalBGEEmbedder
                        self._embedder = LocalBGEEmbedder(
                            model_name=self._model_name,
                            device=self._device,
                            batch_size=self._batch_size,
                        )
        return self._embedder

    def embed_query(self, text: str) -> list:
        return self._load_embedder().embed_query(text)

    def embed_documents(self, texts: list[str], batch_size: int | None = None) -> list:
        return self._load_embedder().embed_documents(texts, batch_size=batch_size)


@dataclass
class AppComponents:
    """应用组件容器"""
    config: AppConfig
    db: sqlite3.Connection
    embedder: LazyEmbedder
    vector_store: LanceVectorStore
    scanner: ObsidianScanner
    parser: ObsidianParser
    chunker: Chunker
    index_manager: IndexManager
    indexer: Indexer
    retriever: Retriever
    reranker: Reranker | None   # BGE-Reranker Cross-Encoder
    generator: Generator | None
    vault_path: str


_components: AppComponents | None = None


def init_components() -> AppComponents:
    """初始化所有组件"""
    global _components

    config = get_config()
    vault_path = _resolve_vault_path()

    # 数据库
    db = init_db(config.paths.sqlite_db)

    # Embedding（延迟加载，provider 来源：.env > config.yaml > 默认 local）
    embedder_provider = os.getenv("EMBEDDING_PROVIDER") or config.embedding.provider
    embedder = LazyEmbedder(
        provider=embedder_provider,
        model_name=config.embedding.model,
        device=config.embedding.device,
        batch_size=config.embedding.batch_size,
        api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", "")),
        base_url=os.getenv("EMBEDDING_BASE_URL") or config.embedding.base_url,
    )

    # 向量存储
    vector_store = LanceVectorStore(db_path=config.paths.lancedb_dir)

    # Pipeline 组件
    scanner = ObsidianScanner()
    parser = ObsidianParser()
    chunker = Chunker(
        chunk_size=config.rag.chunk_size,
        chunk_overlap=config.rag.chunk_overlap,
    )
    index_manager = IndexManager(db, embedder.model_name)
    indexer = Indexer(scanner, parser, chunker, embedder, vector_store, index_manager)
    retriever = Retriever(
        vector_store,
        default_top_k=config.rag.top_k,
        similarity_threshold=config.rag.similarity_threshold,
    )

    # Reranker
    reranker = _init_reranker(config)

    # LLM
    generator = _init_generator(config)

    _components = AppComponents(
        config=config, db=db, embedder=embedder, vector_store=vector_store,
        scanner=scanner, parser=parser, chunker=chunker,
        index_manager=index_manager, indexer=indexer, retriever=retriever,
        reranker=reranker, generator=generator, vault_path=vault_path,
    )
    return _components


def get_components() -> AppComponents:
    global _components
    if _components is None:
        return init_components()
    return _components


def _resolve_vault_path() -> str:
    path = os.getenv("OBSIDIAN_VAULT_PATH", "")
    if path:
        return str(Path(path).expanduser().resolve())
    samples = Path(__file__).resolve().parent.parent.parent / "docs" / "samples"
    if samples.exists():
        return str(samples)
    return ""


def _init_reranker(config: AppConfig):
    """初始化 Reranker"""
    if not config.rerank.enabled:
        return None
    rerank_key = os.getenv("RERANK_API_KEY",
                           os.getenv("EMBEDDING_API_KEY",
                                     os.getenv("LLM_API_KEY", "")))
    if not rerank_key or rerank_key.startswith("sk-your-"):
        return None
    try:
        from src.pipeline.reranker import Reranker
        return Reranker(
            api_key=rerank_key,
            base_url=config.rerank.base_url,
            model=config.rerank.model,
        )
    except Exception:
        return None


def _init_generator(config: AppConfig) -> Generator | None:
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key.startswith("sk-your-"):
        return None
    try:
        from src.llm_providers.openai_compatible import OpenAICompatibleProvider
        provider = os.getenv("LLM_PROVIDER", "deepseek")
        if provider == "deepseek":
            llm = OpenAICompatibleProvider(api_key=api_key, base_url="https://api.deepseek.com/v1", model=config.llm.model)
        elif provider == "openai":
            llm = OpenAICompatibleProvider(api_key=api_key, base_url="https://api.openai.com/v1", model=config.llm.model)
        elif provider == "ollama":
            llm = OpenAICompatibleProvider(api_key="ollama", base_url="http://localhost:11434/v1", model=config.llm.model)
        else:
            return None
        return Generator(llm=llm)
    except Exception:
        return None
