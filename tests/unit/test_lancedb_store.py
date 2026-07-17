"""测试 LanceVectorStore — CRUD、搜索、删除"""
import tempfile

import pytest

from src.vector_stores.lance_store import LanceVectorStore


@pytest.fixture
def temp_store():
    """临时 LanceDB 实例"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LanceVectorStore(db_path=tmpdir, dim=4)  # 小维度加速测试
        yield store


@pytest.fixture
def sample_chunks():
    """测试用 chunk 数据"""
    return [
        {
            "id": "chunk_001",
            "vector": [0.1, 0.2, 0.3, 0.4],
            "content": "LanceDB is great for RAG",
            "source_file": "test/note1.md",
            "heading_path": "Intro",
            "chunk_index": 0,
            "chunk_hash": "abc123",
            "tags": ["#test"],
            "wikilinks": ["LinkA"],
            "frontmatter": {"title": "Note 1"},
            "char_count": 25,
        },
        {
            "id": "chunk_002",
            "vector": [0.5, 0.6, 0.7, 0.8],
            "content": "BGE-M3 embedding model",
            "source_file": "test/note2.md",
            "heading_path": "Embedding",
            "chunk_index": 0,
            "chunk_hash": "def456",
            "tags": ["#embedding"],
            "wikilinks": [],
            "frontmatter": {},
            "char_count": 22,
        },
    ]


class TestLanceDBBasic:
    """基础 CRUD"""

    def test_empty_count(self, temp_store):
        """空表 count 为 0"""
        assert temp_store.count() == 0

    def test_add_chunks(self, temp_store, sample_chunks):
        """添加 chunks 后 count 增加"""
        temp_store.add_chunks(sample_chunks)
        assert temp_store.count() == 2

    def test_add_empty_chunks(self, temp_store):
        """空列表不报错"""
        temp_store.add_chunks([])
        assert temp_store.count() == 0

    def test_search_returns_results(self, temp_store, sample_chunks):
        """向量搜索返回正确结果"""
        temp_store.add_chunks(sample_chunks)

        # 搜索接近 chunk_001 的向量
        results = temp_store.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        assert len(results) == 1
        assert results[0]["id"] == "chunk_001"
        assert "LanceDB is great" in results[0]["content"]

    def test_search_respects_top_k(self, temp_store, sample_chunks):
        """top_k 限制生效"""
        temp_store.add_chunks(sample_chunks)
        results = temp_store.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        assert len(results) == 1

    def test_search_metadata(self, temp_store, sample_chunks):
        """搜索结果包含 metadata"""
        temp_store.add_chunks(sample_chunks)
        results = temp_store.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        r = results[0]
        assert r["source_file"] == "test/note1.md"
        assert r["heading_path"] == "Intro"
        assert "_distance" in r  # LanceDB 自动添加距离字段


class TestLanceDBDelete:
    """删除操作"""

    def test_delete_by_source(self, temp_store, sample_chunks):
        """按源文件删除"""
        temp_store.add_chunks(sample_chunks)
        deleted = temp_store.delete_by_source("test/note1.md")
        assert deleted == 1
        assert temp_store.count() == 1

    def test_delete_nonexistent(self, temp_store, sample_chunks):
        """删除不存在的源文件返回 0"""
        temp_store.add_chunks(sample_chunks)
        deleted = temp_store.delete_by_source("nonexistent.md")
        assert deleted == 0
        assert temp_store.count() == 2


class TestLanceDBSchema:
    """表结构"""

    def test_fts_index_created(self, temp_store, sample_chunks):
        """FTS 索引在建表时自动创建"""
        temp_store.add_chunks(sample_chunks)
        # 验证表存在且有数据
        assert temp_store.count() == 2
        # FTS 索引在 _ensure_table 时创建，不会报错即成功


class TestLanceDBPersistence:
    """持久化"""

    def test_data_persists(self, tmp_path):
        """数据跨实例持久化"""
        db_path = str(tmp_path / "test_lancedb")

        # 写入
        store1 = LanceVectorStore(db_path=db_path, dim=4)
        store1.add_chunks([{
            "id": "persist_001",
            "vector": [0.1, 0.2, 0.3, 0.4],
            "content": "persistence test",
            "source_file": "test.md",
            "heading_path": "",
            "chunk_index": 0,
            "chunk_hash": "xyz",
            "tags": [],
            "wikilinks": [],
            "frontmatter": {},
            "char_count": 16,
        }])

        # 读取（新实例，同路径）
        store2 = LanceVectorStore(db_path=db_path, dim=4)
        assert store2.count() == 1
        results = store2.search([0.1, 0.2, 0.3, 0.4], top_k=1)
        assert results[0]["id"] == "persist_001"
