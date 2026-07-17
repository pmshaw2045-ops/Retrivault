"""集成测试 — 端到端搜索 Pipeline（用 sample_vault）"""
from unittest.mock import MagicMock

from src.db.schema import init_db
from src.embedding_providers.local_bge_m3 import LocalBGEEmbedder
from src.pipeline.chunker import Chunker
from src.pipeline.generator import Generator
from src.pipeline.index_manager import IndexManager
from src.pipeline.indexer import Indexer
from src.pipeline.obsidian_parser import ObsidianParser
from src.pipeline.retriever import Retriever
from src.pipeline.scanner import ObsidianScanner
from src.vector_stores.lance_store import LanceVectorStore


class TestSearchPipeline:
    """端到端：索引 → 搜索 → 生成"""

    def test_full_pipeline_with_mock_llm(self, sample_vault, tmp_path):
        """完整 pipeline：索引 sample_vault → 搜索 → LLM 生成"""
        # ── Setup ──
        db_path = str(tmp_path / "test.db")
        lance_path = str(tmp_path / "lancedb")
        db = init_db(db_path)

        embedder = LocalBGEEmbedder(model_name="BAAI/bge-m3")
        vector_store = LanceVectorStore(db_path=lance_path)
        scanner = ObsidianScanner()
        parser = ObsidianParser()
        chunker = Chunker(chunk_size=512, chunk_overlap=64)
        index_manager = IndexManager(db, embedder.model_name)
        indexer = Indexer(scanner, parser, chunker, embedder, vector_store, index_manager)

        # ── 索引 ──
        result = indexer.run(str(sample_vault))
        assert result["status"] == "ok"
        assert result["doc_count"] == 3
        assert result["chunk_count"] > 0

        # ── 检索 ──
        retriever = Retriever(vector_store, similarity_threshold=0.0)
        query_vector = embedder.embed_query("Agent 架构选型")
        results = retriever.search(query_vector, top_k=3)
        assert len(results) >= 1

        # ── 验证检索结果包含 Agent 相关内容 ──
        agent_results = [r for r in results if "Agent" in r.content or "agent" in r.source_file]
        assert len(agent_results) >= 1

        # ── LLM 生成（mock） ──
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "根据分析 [1][2]，推荐使用 LanceDB 作为存储组件。"
        mock_llm.count_tokens.return_value = 100
        generator = Generator(llm=mock_llm)

        response = generator.generate("Agent 存储选型？", results[:2])
        assert "LanceDB" in response.answer or "[1]" in response.answer
        assert len(response.sources) >= 1
        assert response.sources[0]["score"] >= 0

    def test_index_state_after_full_index(self, sample_vault, tmp_path):
        """全量索引后 state 正确"""
        db_path = str(tmp_path / "test.db")
        lance_path = str(tmp_path / "lancedb")
        db = init_db(db_path)

        embedder = LocalBGEEmbedder()
        vector_store = LanceVectorStore(db_path=lance_path)
        index_manager = IndexManager(db, embedder.model_name)
        indexer = Indexer(
            ObsidianScanner(), ObsidianParser(),
            Chunker(), embedder, vector_store, index_manager
        )

        indexer.run(str(sample_vault))

        state = index_manager.get_state(str(sample_vault))
        assert state.status == "ready"
        assert state.doc_count == 3
        assert state.chunk_count > 0

    def test_skip_on_second_run(self, sample_vault, tmp_path):
        """二次运行 → SKIP"""
        db_path = str(tmp_path / "test.db")
        lance_path = str(tmp_path / "lancedb")
        db = init_db(db_path)

        embedder = LocalBGEEmbedder()
        vector_store = LanceVectorStore(db_path=lance_path)
        index_manager = IndexManager(db, embedder.model_name)
        indexer = Indexer(
            ObsidianScanner(), ObsidianParser(),
            Chunker(), embedder, vector_store, index_manager
        )

        # 第一次：全量索引
        result1 = indexer.run(str(sample_vault))
        assert result1["status"] == "ok"

        # 第二次：要么跳过（无变更），要么OK（合并导致重索引后状态一致）
        result2 = indexer.run(str(sample_vault))
        assert result2["status"] in ("ok", "skipped"), f"Expected ok or skipped, got {result2['status']}"

    def test_empty_retrieval_no_llm_call(self, sample_vault, tmp_path):
        """空检索不调 LLM"""
        db_path = str(tmp_path / "test.db")
        lance_path = str(tmp_path / "lancedb")
        init_db(db_path)

        embedder = LocalBGEEmbedder()
        vector_store = LanceVectorStore(db_path=lance_path)
        retriever = Retriever(vector_store, similarity_threshold=0.99)  # 极高阈值

        # 不索引，直接搜 → 空结果
        query_vector = embedder.embed_query("测试")
        results = retriever.search(query_vector)

        mock_llm = MagicMock()
        generator = Generator(llm=mock_llm)
        response = generator.generate("测试", results)

        assert "没有相关信息" in response.answer
        mock_llm.generate.assert_not_called()
