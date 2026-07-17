"""抽象接口层 — Provider 协议定义

所有 Provider 实现只需遵循对应的 ABC 接口。
扩展新 Provider（如 Qdrant、Milvus、Ollama）时只需实现这些接口，
在 Provider 注册工厂中注册即可，不改任何其他代码。
"""

from abc import ABC, abstractmethod


# ============================================================
# VectorStore — 向量存储接口
# ============================================================
class VectorStore(ABC):
    """向量数据库抽象。

    默认实现：LanceVectorStore（src/vector_stores/lance_store.py）
    扩展方式：实现此接口 → 在 vector_stores/__init__.py 注册
    """

    @abstractmethod
    def add_chunks(self, chunks: list[dict]) -> None:
        """批量写入 chunks。每个 chunk 包含：id, vector, content, metadata。

        LanceDB 实现：table.add() 写入是原子的。
        """
        ...

    @abstractmethod
    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """向量搜索。返回 top_k 个最相似的 chunk，每个包含 content + metadata + _distance。

        Phase 1: 纯向量搜索
        Phase 2: 子类可 override 为 hybrid_search
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空向量库"""
        ...

    @abstractmethod
    def delete_by_source(self, source_file: str) -> int:
        """删除指定源文件的所有 chunk。返回删除数量。"""
        ...

    @abstractmethod
    def count(self) -> int:
        """返回表中 chunk 总数"""
        ...


# ============================================================
# LLMProvider — 大语言模型接口
# ============================================================
class LLMProvider(ABC):
    """LLM 调用抽象。

    默认实现：DeepSeekProvider（src/llm_providers/deepseek.py）
    扩展方式：实现此接口 → 在 llm_providers/__init__.py 注册
    """

    @abstractmethod
    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048
    ) -> str:
        """调用 LLM 生成回答。

        Args:
            system_prompt: 系统角色指令
            user_prompt: 用户提示（含知识片段 + 问题）
            temperature: 生成温度
            max_tokens: 最大输出 token 数

        Returns:
            LLM 生成的文本回答
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """估算文本的 token 数（用于 Prompt 预算管理）。

        不同 Provider 的 tokenizer 不同，各自实现估算逻辑。
        """
        ...


# ============================================================
# EmbeddingProvider — 嵌入模型接口
# ============================================================
class EmbeddingProvider(ABC):
    """Embedding 模型抽象。

    默认实现：LocalBGEM3Embedder（src/embedding_providers/local_bge_m3.py）
    扩展方式：实现此接口 → 在 embedding_providers/__init__.py 注册
    """

    @abstractmethod
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """批量文档向量化。

        Args:
            texts: 文档文本列表
            batch_size: 每批处理的文本数量

        Returns:
            向量列表，每个向量维度由模型决定
        """
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化。

        BGE-M3 查询时需加 instruction prefix：
        "为这个句子生成表示以用于检索相关文章：" + text
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回模型名称（如 'BAAI/bge-m3'）。
        用于 chunk_progress 表的 embedding_model 字段，支撑模型变更检测。
        """
        ...
