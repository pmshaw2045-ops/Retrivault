"""测试 Retriever — 向量搜索、tag_filter、similarity_threshold、async"""
import tempfile

import pytest

from src.pipeline.retriever import Retriever, SearchResult
from src.vector_stores.lance_store import LanceVectorStore


@pytest.fixture
def store():
    """临时 LanceDB store"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LanceVectorStore(db_path=tmpdir, dim=4)
        yield store


@pytest.fixture
def populated_store(store):
    """已填充测试数据的 store"""
    chunks = [
        {
            "id": "c1", "vector": [0.1, 0.2, 0.3, 0.4],
            "content": "Agent 架构选型需要考虑存储组件",
            "source_file": "notes/agent.md",
            "heading_path": "架构选型 > 存储",
            "chunk_index": 0, "chunk_hash": "h1",
            "tags": ["#agent", "#architecture"],
            "wikilinks": ["存储组件"],
            "frontmatter": {"title": "Agent 架构"},
            "char_count": 15,
        },
        {
            "id": "c2", "vector": [0.5, 0.6, 0.7, 0.8],
            "content": "RAG 基础知识介绍",
            "source_file": "notes/rag.md",
            "heading_path": "RAG 基础",
            "chunk_index": 0, "chunk_hash": "h2",
            "tags": ["#rag"],
            "wikilinks": [],
            "frontmatter": {},
            "char_count": 8,
        },
        {
            "id": "c3", "vector": [0.9, 0.1, 0.2, 0.3],
            "content": "Python 异步编程指南",
            "source_file": "notes/python.md",
            "heading_path": "异步",
            "chunk_index": 0, "chunk_hash": "h3",
            "tags": ["#python", "#async"],
            "wikilinks": [],
            "frontmatter": {},
            "char_count": 10,
        },
    ]
    store.add_chunks(chunks)
    return store


class TestRetrieverBasic:
    """基础检索功能"""

    def test_search_returns_results(self, populated_store):
        """搜索返回结果"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search([0.1, 0.2, 0.3, 0.4], top_k=2)
        assert len(results) >= 1
        assert isinstance(results[0], SearchResult)

    def test_top_k_respected(self, populated_store):
        """top_k 限制生效"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search([0.0, 0.0, 0.0, 0.0], top_k=2)
        assert len(results) <= 2

    def test_results_sorted_by_score(self, populated_store):
        """结果按分数降序排列"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search([0.1, 0.2, 0.3, 0.4], top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_result_contains_metadata(self, populated_store):
        """搜索结果包含 metadata"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        r = results[0]
        assert r.source_file == "notes/agent.md"
        assert "存储" in r.heading_path
        assert r.score >= 0.0
        assert "#agent" in r.tags


class TestSimilarityThreshold:
    """相似度阈值过滤"""

    def test_threshold_filters_low_scores(self, populated_store):
        """低相似度结果被阈值过滤"""
        # 用极低向量（全 0）搜，应该得到较低分数
        retriever = Retriever(populated_store, similarity_threshold=0.5)
        results = retriever.search([0.0, 0.0, 0.0, 0.0], top_k=10)
        # 全零向量搜出来的分数可能较低，但至少有结果
        # 核心验证：retriever 不会崩溃，且没有 score < 0.5 的结果
        for r in results:
            assert r.score >= 0.5, f"Score {r.score} below threshold 0.5"

    def test_runtime_threshold_override(self, populated_store):
        """运行时覆盖默认阈值"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        # 精确匹配向量应该得到高分
        results = retriever.search(
            [0.1, 0.2, 0.3, 0.4], similarity_threshold=0.5
        )
        # 精确匹配得分接近 1.0，通过 0.5 阈值
        assert len(results) >= 1
        for r in results:
            assert r.score >= 0.5


class TestTagFilter:
    """标签过滤"""

    def test_tag_filter_matches(self, populated_store):
        """tag_filter 正确过滤"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search(
            [0.0, 0.0, 0.0, 0.0], top_k=5,
            tag_filter=["#agent"]
        )
        assert len(results) == 1
        assert "Agent" in results[0].content

    def test_tag_filter_no_match(self, populated_store):
        """无匹配 tag 返回空"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search(
            [0.0, 0.0, 0.0, 0.0], top_k=5,
            tag_filter=["#nonexistent"]
        )
        assert len(results) == 0

    def test_multiple_tags_filter(self, populated_store):
        """多标签 OR 过滤"""
        retriever = Retriever(populated_store, similarity_threshold=0.0)
        results = retriever.search(
            [0.0, 0.0, 0.0, 0.0], top_k=5,
            tag_filter=["#rag", "#python"]
        )
        assert len(results) >= 1  # 至少匹配 rag 或 python


class TestEmptyStore:
    """空 store 行为"""

    def test_empty_store_returns_empty(self, store):
        """空 store 返回空列表"""
        retriever = Retriever(store, similarity_threshold=0.0)
        results = retriever.search([0.1, 0.2, 0.3, 0.4])
        assert results == []
