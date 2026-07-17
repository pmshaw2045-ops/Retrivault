"""测试 IndexManager — 启动决策、状态管理、变更检测、模型版本检测"""
import sqlite3
from pathlib import Path

import pytest

from src.pipeline.index_manager import IndexDecision, IndexManager


@pytest.fixture
def db():
    """内存数据库（带完整 schema）"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS index_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vault_path TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'idle',
            doc_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            error_msg TEXT
        );
        CREATE TABLE IF NOT EXISTS chunk_progress (
            chunk_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            embedding_model TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS doc_manifest (
            source_file TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            file_mtime REAL NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            indexed_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def manager(db):
    """IndexManager with BGE-M3"""
    return IndexManager(db, embedder_model_name="BAAI/bge-m3")


@pytest.fixture
def temp_vault(tmp_path):
    """临时 vault 目录"""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "doc1.md").write_text("# Doc 1\nContent A.")
    (vault / "doc2.md").write_text("# Doc 2\nContent B.")
    return vault


class TestStartupDecisions:
    """启动决策"""

    def test_first_index_when_no_state(self, manager, temp_vault):
        """无历史记录 → FIRST_INDEX"""
        decision = manager.on_startup(str(temp_vault))
        assert decision == IndexDecision.FIRST_INDEX

    def test_skip_when_ready_and_no_changes(self, manager, temp_vault):
        """索引已完成 + 无变更 → SKIP"""
        # 模拟已完成索引
        manager.db.execute(
            "INSERT INTO index_state (vault_path, status, doc_count) VALUES (?, 'ready', 2)",
            (str(temp_vault),)
        )
        manager.db.commit()

        # 先标记文件为已索引
        _mark_all_indexed(manager, temp_vault, "BAAI/bge-m3")

        decision = manager.on_startup(str(temp_vault))
        assert decision == IndexDecision.SKIP

    def test_resume_when_interrupted(self, manager, temp_vault):
        """上次状态 indexing → RESUME"""
        manager.db.execute(
            "INSERT INTO index_state (vault_path, status) VALUES (?, 'indexing')",
            (str(temp_vault),)
        )
        manager.db.commit()

        decision = manager.on_startup(str(temp_vault))
        assert decision == IndexDecision.RESUME

    def test_reindex_when_model_changed(self, manager, temp_vault):
        """embedding 模型变更 → REINDEX"""
        # 已完成索引，但使用了不同的 embedding 模型
        manager.db.execute(
            "INSERT INTO index_state (vault_path, status) VALUES (?, 'ready')",
            (str(temp_vault),)
        )
        manager.db.execute(
            "INSERT INTO chunk_progress (chunk_id, source_file, chunk_index, content_hash, embedding_model, status) "
            "VALUES ('c1', 'doc1.md', 0, 'hash1', 'BAAI/bge-small', 'embedded')"
        )
        manager.db.commit()

        decision = manager.on_startup(str(temp_vault))
        assert decision == IndexDecision.REINDEX

    def test_incremental_when_files_changed(self, manager, temp_vault):
        """文件变更 → INCREMENTAL"""
        manager.db.execute(
            "INSERT INTO index_state (vault_path, status) VALUES (?, 'ready')",
            (str(temp_vault),)
        )
        # 不标记文件为已索引 — 变更检测会发现差异
        manager.db.commit()

        decision = manager.on_startup(str(temp_vault))
        assert decision == IndexDecision.INCREMENTAL


class TestStateManagement:
    """状态管理"""

    def test_mark_indexing_start(self, manager, temp_vault):
        """标记索引起始"""
        vault = str(temp_vault)
        manager.mark_indexing_start(vault)
        state = manager.get_state(vault)
        assert state.status == "indexing"
        assert state.started_at is not None

    def test_mark_indexing_done(self, manager, temp_vault):
        """标记索引完成"""
        vault = str(temp_vault)
        manager.mark_indexing_start(vault)
        manager.mark_indexing_done(vault, doc_count=3, chunk_count=12)
        state = manager.get_state(vault)
        assert state.status == "ready"
        assert state.doc_count == 3
        assert state.chunk_count == 12

    def test_mark_indexing_error(self, manager, temp_vault):
        """标记索引错误"""
        vault = str(temp_vault)
        manager.mark_indexing_start(vault)
        manager.mark_indexing_error(vault, "OOM")
        state = manager.get_state(vault)
        assert state.status == "error"
        assert "OOM" in state.error_msg


class TestChunkProgress:
    """Chunk 进度（幂等）"""

    def test_chunk_lifecycle(self, manager):
        """chunk 生命周期：pending → embedded"""
        manager.mark_chunk_pending("c1", "doc.md", 0, "hash1")
        assert not manager.is_chunk_embedded("c1")

        manager.mark_chunk_embedded("c1")
        assert manager.is_chunk_embedded("c1")

    def test_pending_chunks(self, manager):
        """get_pending_chunks 返回所有待处理的"""
        manager.mark_chunk_pending("c1", "doc1.md", 0, "h1")
        manager.mark_chunk_pending("c2", "doc2.md", 0, "h2")
        manager.mark_chunk_embedded("c1")

        pending = manager.get_pending_chunks()
        assert len(pending) == 1
        assert pending[0]["chunk_id"] == "c2"

    def test_embedding_model_recorded(self, manager):
        """chunk_progress 记录 embedding_model"""
        manager.mark_chunk_pending("c1", "doc.md", 0, "h1")
        row = manager.db.execute("SELECT embedding_model FROM chunk_progress WHERE chunk_id='c1'").fetchone()
        assert row["embedding_model"] == "BAAI/bge-m3"


class TestModelVersionDetection:
    """模型版本检测"""

    def test_no_model_recorded(self, manager):
        """无 chunk_progress 记录 → 不认为变更"""
        assert not manager._is_embedding_model_changed()

    def test_same_model(self, manager):
        """相同模型 → 不认为变更"""
        manager.mark_chunk_pending("c1", "doc.md", 0, "h1")
        assert not manager._is_embedding_model_changed()

    def test_different_model(self, db):
        """不同模型 → 检测到变更"""
        # 用旧模型记录
        mgr_old = IndexManager(db, embedder_model_name="BAAI/bge-small")
        mgr_old.mark_chunk_pending("c1", "doc.md", 0, "h1")

        # 用新模型检测
        mgr_new = IndexManager(db, embedder_model_name="BAAI/bge-m3")
        assert mgr_new._is_embedding_model_changed()

    def test_get_last_embedding_model(self, manager):
        """获取上次使用的模型名"""
        assert manager.get_last_embedding_model() is None
        manager.mark_chunk_pending("c1", "doc.md", 0, "h1")
        assert manager.get_last_embedding_model() == "BAAI/bge-m3"


class TestChangeDetection:
    """文件变更检测"""

    def test_detect_new_file(self, manager, temp_vault):
        """检测新增文件"""
        changed = manager.detect_changes(str(temp_vault))
        # 两个文件都未被索引 → 都算变更
        assert len(changed) == 2

    def test_detect_no_change_when_indexed(self, manager, temp_vault):
        """已索引文件无变更返回空"""
        _mark_all_indexed(manager, temp_vault, "BAAI/bge-m3")
        changed = manager.detect_changes(str(temp_vault))
        assert len(changed) == 0

    def test_detect_modified(self, manager, temp_vault):
        """检测文件修改"""
        _mark_all_indexed(manager, temp_vault, "BAAI/bge-m3")

        # 修改文件
        (temp_vault / "doc1.md").write_text("# Doc 1\nModified content.")

        changed = manager.detect_changes(str(temp_vault))
        assert len(changed) >= 1
        assert any("doc1.md" in c for c in changed)

    def test_detect_deleted(self, manager, temp_vault):
        """检测文件删除"""
        _mark_all_indexed(manager, temp_vault, "BAAI/bge-m3")

        # 删除文件
        (temp_vault / "doc1.md").unlink()

        changed = manager.detect_changes(str(temp_vault))
        assert any("doc1.md" in c for c in changed)


class TestReset:
    """重置"""

    def test_reset_all(self, manager, temp_vault):
        """全量重置"""
        vault = str(temp_vault)
        manager.mark_indexing_start(vault)
        manager.mark_chunk_pending("c1", "doc1.md", 0, "h1")
        manager.reset_all(vault)

        assert manager.get_state(vault) is None
        assert manager.get_pending_chunks() == []


# ============================================================
# Helpers
# ============================================================

def _mark_all_indexed(manager: IndexManager, vault: Path, model: str):
    """辅助：标记 vault 中所有文件为已索引"""
    for md_file in vault.rglob("*.md"):
        rel = str(md_file.relative_to(vault))
        file_hash = manager._file_hash(str(md_file))
        manager.update_doc_manifest(rel, file_hash, md_file.stat().st_mtime, 1)
