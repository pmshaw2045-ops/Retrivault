"""Pydantic v2 配置模型 + 校验逻辑"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RAGConfig(BaseModel):
    chunk_size: int = Field(default=512, ge=128, le=2048)
    chunk_overlap: int = Field(default=64, ge=0, le=512)
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class LLMConfig(BaseModel):
    model: str = Field(default="deepseek-v4-pro", min_length=1)
    temperature: float = Field(default=0.3)
    max_tokens: int = Field(default=2048, ge=256, le=16384)

    @field_validator("temperature")
    @classmethod
    def clamp_temperature(cls, v: float) -> float:
        """Clamp temperature to [0.0, 2.0] — 超出范围自动修正而非拒绝"""
        return max(0.0, min(2.0, v))


class EmbeddingConfig(BaseModel):
    provider: Literal["local", "api"] = "local"
    model: str = Field(default="BAAI/bge-m3", min_length=1)
    base_url: str = Field(default="")
    batch_size: int = Field(default=32, ge=1, le=128)
    device: Literal["cpu", "cuda", "mps"] = "cpu"


class RerankConfig(BaseModel):
    enabled: bool = False
    provider: Literal["api"] = "api"
    model: str = Field(default="BAAI/bge-reranker-v2-m3")
    base_url: str = Field(default="")


class RewriteConfig(BaseModel):
    enabled: bool = True
    model: str = Field(default="Qwen/Qwen2.5-7B-Instruct")
    base_url: str = Field(default="https://api.siliconflow.cn/v1")


class SearchConfig(BaseModel):
    mode: Literal["vector", "hybrid"] = "vector"
    rerank_enabled: bool = False


class PathsConfig(BaseModel):
    lancedb_dir: str = Field(default="data/lancedb", min_length=1)
    sqlite_db: str = Field(default="data/rag.db", min_length=1)


class AppConfig(BaseModel):
    """应用全量配置"""
    rag: RAGConfig = Field(default_factory=RAGConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    rewrite: RewriteConfig = Field(default_factory=RewriteConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
