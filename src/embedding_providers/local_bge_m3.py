"""本地 BGE-M3 Embedding Provider

实现 EmbeddingProvider 接口。
默认模型：BAAI/bge-m3（1024维，中文最优）
"""

from src.interfaces import EmbeddingProvider


class LocalBGEEmbedder(EmbeddingProvider):
    """
    本地 BGE-M3 嵌入器。

    BGE-M3 特性：
      - 1024 维向量
      - 查询时需加 instruction prefix
      - 支持中英双语
    """

    # BGE-M3 推荐的查询 instruction prefix
    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu", batch_size: int = 32):
        self._model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device=self.device)
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """
        批量文档向量化。

        Args:
            texts: 文档文本列表
            batch_size: 覆盖默认 batch_size

        Returns:
            向量列表，每个元素是 1024 维 float 列表
        """
        if not texts:
            return []

        bs = batch_size or self.batch_size
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            # BGE-M3 文档 embedding 不需要 instruction prefix
            embeddings = self.model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            all_embeddings.extend(embeddings.tolist())

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """
        查询向量化。

        BGE-M3 查询时需要加 instruction prefix 以提升检索质量。
        """
        query_text = self.QUERY_INSTRUCTION + text
        embedding = self.model.encode(
            query_text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()
