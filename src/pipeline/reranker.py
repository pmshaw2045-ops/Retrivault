"""Reranker — 对检索结果重排序

支持 OpenAI 兼容 Rerank API：
  - 硅基流动: https://api.siliconflow.cn/v1/rerank
  - Cohere / Jina 等兼容服务
"""

import httpx


class Reranker:
    """
    重排序器——Cross-Encoder 精确排序。

    API Key 优先级：RERANK_API_KEY > EMBEDDING_API_KEY > LLM_API_KEY
    """

    def __init__(self, api_key: str, base_url: str, model: str = "BAAI/bge-reranker-v2-m3"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def rerank(self, query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
        if not documents:
            return []

        resp = httpx.post(
            f"{self.base_url}/rerank",
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n or len(documents),
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
