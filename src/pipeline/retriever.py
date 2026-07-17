"""检索引擎

Phase 1: LanceDB 向量搜索
Phase 2: LanceDB 混合搜索（向量 + FTS）+ 结果去重
"""
import asyncio
import math
from dataclasses import dataclass, field

from src.interfaces import VectorStore


def rescale_score(cosine_similarity: float) -> float:
    """sigmoid 映射：raw cos_sim → [0,1] 用户友好分数"""
    k = 30.0
    midpoint = 0.1
    return 1.0 / (1.0 + math.exp(-k * (cosine_similarity - midpoint)))


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

        results = self._build_results(raw, threshold, tag_filter)

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
                       tag_filter: list[str] | None) -> list[SearchResult]:
        results = []
        for r in raw:
            distance = r.get("_distance", 1.0)
            raw_sim = max(0.0, 1.0 - distance)
            score = rescale_score(raw_sim)
            if score < threshold:
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
        """同一 source_file 只保留最高分 chunk，避免重复文档占满 Top-K"""
        seen: dict[str, SearchResult] = {}
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            if r.source_file not in seen:
                seen[r.source_file] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)
