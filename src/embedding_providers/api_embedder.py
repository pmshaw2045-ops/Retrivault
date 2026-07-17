"""API Embedding Provider — 调用远程 Embedding API

支持所有 OpenAI 兼容接口：
  - 硅基流动: https://api.siliconflow.cn/v1
  - DeepSeek:   https://api.deepseek.com/v1
  - OpenAI:     https://api.openai.com/v1
  - 任意兼容服务
"""
from openai import OpenAI

from src.interfaces import EmbeddingProvider


class APIEmbedder(EmbeddingProvider):
    """
    远程 Embedding API Provider。

    配置示例（.env）：
      EMBEDDING_API_KEY=sk-xxx
      EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
      EMBEDDING_MODEL=BAAI/bge-m3

    用户无需下载 2.2GB 本地模型，有 API key 即可用。
    """

    def __init__(self, api_key: str, base_url: str,
                 model: str = "BAAI/bge-m3", batch_size: int = 32):
        self._model_name = model
        self.batch_size = batch_size
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: list[str],
                        batch_size: int | None = None) -> list[list[float]]:
        """批量文档向量化"""
        if not texts:
            return []

        bs = batch_size or self.batch_size
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), bs):
            batch = texts[i:i + bs]
            resp = self.client.embeddings.create(
                model=self._model_name,
                input=batch,
            )
            all_embeddings.extend([d.embedding for d in resp.data])

        return all_embeddings

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化（API 模式不需要 instruction prefix）"""
        resp = self.client.embeddings.create(
            model=self._model_name,
            input=[text],
        )
        return resp.data[0].embedding
