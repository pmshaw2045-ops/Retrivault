"""Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field

# ============================================================
# Search
# ============================================================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索查询")
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="vector", pattern="^(vector|hybrid)$")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    tag_filter: list[str] | None = Field(default=None)


class SourceInfo(BaseModel):
    index: int
    source_file: str
    heading_path: str
    score: float
    preview: str


class SearchResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = []
    retrieval_stats: dict = {}
    trace: list[dict] = []  # 流水线每步追踪


# ============================================================
# Index
# ============================================================

class IndexRequest(BaseModel):
    action: str = Field(default="full", pattern="^(full|incremental|resume)$")


class IndexProgress(BaseModel):
    status: str           # idle|indexing|ready|error
    doc_count: int
    chunk_count: int
    phase: str = ""       # scanning|embedding
    current: int = 0
    total: int = 0


# ============================================================
# Status
# ============================================================

class StatusResponse(BaseModel):
    state: str            # needs_index|indexing|ready|error
    doc_count: int
    chunk_count: int
    vault_path: str = ""
    pending_changes: bool = False
    changed_files: list[str] = []


# ============================================================
# Config
# ============================================================

class ConfigUpdate(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    chunk_size: int | None = Field(default=None, ge=128, le=2048)
    chunk_overlap: int | None = Field(default=None, ge=0, le=512)
    search_mode: str | None = Field(default=None, pattern="^(vector|hybrid)$")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class ConfigResponse(BaseModel):
    top_k: int
    chunk_size: int
    chunk_overlap: int
    search_mode: str
    temperature: float
    similarity_threshold: float
    embedding_model: str
    llm_model: str


# ============================================================
# Evaluate
# ============================================================

class EvaluateRequest(BaseModel):
    query: str
    expected_chunks: list[str] = []  # 期望命中的 chunk_id 列表


class EvaluateResponse(BaseModel):
    hit_rate: float
    mrr: float = 0.0
    retrieved_count: int
    expected_count: int
