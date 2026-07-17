"""检索引擎

Phase 1: LanceDB 向量搜索
Phase 2: LanceDB 混合搜索（向量 + FTS）+ 结果去重

关键词加分（_keyword_boost）：
  - 使用 jieba 中文分词，支持英/中/混合查询
  - 在 raw_sim 层加分（before rescale_score），不入侵 LanceDB 存储层
  - 每个有意义的查询词命中 +0.10 raw_sim，上限 +0.20
"""
import asyncio
import math
from dataclasses import dataclass, field

from src.interfaces import VectorStore

# ── jieba 分词器（惰性加载，首次使用时初始化） ──
_JIEBA_REF = None  # 模块级引用，避免局部作用域问题


def _tokenize(text: str) -> list[str]:
    """对查询文本做中文分词，返回有意义的关键词列表。

    对纯英文/数字/符号查询 fallback 到 str.split()。
    过滤单字、停用词后的词才用于关键词加分。
    """
    global _JIEBA_REF
    if not text.strip():
        return []

    # 检测是否有中文：有中文用 jieba，否则 .split()
    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in text)
    if has_chinese:
        if _JIEBA_REF is None:
            import jieba
            _JIEBA_REF = jieba
        tokens = _JIEBA_REF.lcut(text)
    else:
        tokens = text.lower().split()

    return [t.lower() for t in tokens if len(t) >= 2]


def _keyword_boost(content: str, tokens: list[str]) -> float:
    """计算关键词加分：每个 token 在 content 中出现一次 +0.10，上限 +0.20。"""
    if not tokens:
        return 0.0
    content_lower = content.lower()
    hits = sum(1 for t in tokens if t in content_lower)
    return min(0.20, hits * 0.10)


def rescale_score(cosine_similarity: float) -> float:
    """sigmoid 映射：raw cos_sim → [0,1] 内部排序分数

    使用温和的 k=5 使中低分段仍有区分度，确保 reranker 能拿到有意义的分布。
    此分数用于阈值过滤和排序，不等于用户看到的展示分数。
    """
    k = 5.0
    midpoint = 0.3
    return 1.0 / (1.0 + math.exp(-k * (cosine_similarity - midpoint)))


def display_score(internal_score: float) -> float:
    """将内部排序分数映射为用户友好的展示分数

    内部分数范围约 [0.5, 1.0]（余弦距离修复后）。
    直接透传 internal_score，不再做非线性映射。
    """
    return round(internal_score, 3)


@dataclass
class SearchResult:
    content: str
    source_file: str
    heading_path: str
    chunk_index: int
    chunk_hash: str
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    wikilinks: list[str] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)
    char_count: int = 0


class Retriever:

    def __init__(self, vector_store: VectorStore, default_top_k: int = 5,
                 similarity_threshold: float = 0.3):
        self.store = vector_store
        self.default_top_k = default_top_k
        self.similarity_threshold = similarity_threshold

    def search(self, query_vector: list[float], query_text: str = "",
               top_k: int | None = None,
               similarity_threshold: float | None = None,
               tag_filter: list[str] | None = None,
               mode: str = "vector") -> list[SearchResult]:
        k = top_k or self.default_top_k
        threshold = similarity_threshold if similarity_threshold is not None else self.similarity_threshold
        fetch_k = k * 3 if mode == "hybrid" else k

        if mode == "hybrid" and query_text:
            raw = self.store.search_hybrid(query_vector, query_text, top_k=fetch_k)
        else:
            raw = self.store.search(query_vector, top_k=fetch_k)

        results = self._build_results(raw, threshold, tag_filter, query_text=query_text)

        # 去重：同一 source_file 只保留最高分的 chunk
        results = self._dedup_by_source(results)

        return results[:k]

    async def search_async(self, query_vector: list[float],
                            query_text: str = "",
                            top_k: int | None = None,
                            similarity_threshold: float | None = None,
                            tag_filter: list[str] | None = None,
                            mode: str = "vector") -> list[SearchResult]:
        return await asyncio.to_thread(self.search, query_vector,
                                       query_text=query_text,
                                       top_k=top_k, similarity_threshold=similarity_threshold,
                                       tag_filter=tag_filter, mode=mode)

    # ── 内部方法 ──

    def _build_results(self, raw: list[dict], threshold: float,
                       tag_filter: list[str] | None,
                       query_text: str = "") -> list[SearchResult]:
        query_tokens = _tokenize(query_text) if query_text else []
        results = []
        for r in raw:
            distance = r.get("_distance", 1.0)
            raw_sim = max(0.0, 1.0 - distance)

            # 关键词加分（raw_sim 层，before rescale）
            if query_tokens:
                content = r.get("content", "")
                raw_sim = min(1.0, raw_sim + _keyword_boost(content, query_tokens))

            score = rescale_score(raw_sim)
            if display_score(score) < threshold:
                continue

            chunk_tags = r.get("tags", [])
            if isinstance(chunk_tags, str):
                import json
                try:
                    chunk_tags = json.loads(chunk_tags)
                except json.JSONDecodeError:
                    chunk_tags = []

            if tag_filter and not any(t in chunk_tags for t in tag_filter):
                continue

            results.append(SearchResult(
                content=r.get("content", ""),
                source_file=r.get("source_file", ""),
                heading_path=r.get("heading_path", ""),
                chunk_index=r.get("chunk_index", 0),
                chunk_hash=r.get("chunk_hash", ""),
                score=score,
                tags=chunk_tags,
                wikilinks=r.get("wikilinks", []) if not isinstance(r.get("wikilinks"), str) else [],
                frontmatter=r.get("frontmatter", {}) if not isinstance(r.get("frontmatter"), str) else {},
                char_count=r.get("char_count", 0),
            ))
        return results

    @staticmethod
    def _dedup_by_source(results: list[SearchResult]) -> list[SearchResult]:
        """同一 source_file + heading_path 只保留最高分 chunk

        不同 section（不同 heading_path）的 chunk 各自保留，
        避免一篇文档中两个不相关的相关小节互相覆盖。
        """
        seen: dict[tuple[str, str], SearchResult] = {}
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            key = (r.source_file, r.heading_path)
            if key not in seen:
                seen[key] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)
