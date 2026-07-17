"""索引生命周期管理

职责：
  1. 启动时判断索引决策（FIRST_INDEX / INCREMENTAL / RESUME / REINDEX / SKIP）
  2. 记录索引进度（chunk-level 幂等）
  3. 检测文件变更 + embedding 模型版本变更
"""
import hashlib
import sqlite3
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


class IndexDecision(Enum):
    """索引决策"""
    FIRST_INDEX = auto()    # 首次启动，全量索引
    INCREMENTAL = auto()    # 有文件变更，增量索引
    RESUME = auto()          # 上次中断，从断点继续
    REINDEX = auto()         # embedding 模型变更，全量重建
    SKIP = auto()            # 无变更，跳过


@dataclass
class IndexState:
    """索引状态快照"""
    vault_path: str
    status: str          # idle|indexing|ready|error
    doc_count: int
    chunk_count: int
    started_at: str | None
    finished_at: str | None
    error_msg: str | None


class IndexManager:
    """
    索引生命周期管理器。

    核心方法 on_startup() 返回 IndexDecision，
    调用方根据决策执行对应的索引操作。
    """

    def __init__(self, db: sqlite3.Connection, embedder_model_name: str):
        self.db = db
        self.embedder_model_name = embedder_model_name

    # ============================================================
    # 启动决策
    # ============================================================

    def on_startup(self, vault_path: str) -> IndexDecision:
        """
        启动时判断索引决策。

        决策逻辑：
          1. 无历史记录 → FIRST_INDEX
          2. 上次状态 indexing → RESUME
          3. embedding 模型变更 → REINDEX
          4. 有文件变更 → INCREMENTAL
          5. 其他 → SKIP
        """
        state = self.get_state(vault_path)

        # 首次启动
        if state is None:
            return IndexDecision.FIRST_INDEX

        # 上次索引被中断
        if state.status == "indexing":
            return IndexDecision.RESUME

        # 检测 embedding 模型是否变更
        if self._is_embedding_model_changed():
            return IndexDecision.REINDEX

        # 检测文件变更
        changed = self.detect_changes(vault_path)
        if changed:
            return IndexDecision.INCREMENTAL

        return IndexDecision.SKIP

    # ============================================================
    # 状态管理
    # ============================================================

    def get_state(self, vault_path: str) -> IndexState | None:
        """获取索引状态"""
        row = self.db.execute(
            "SELECT * FROM index_state WHERE vault_path = ?",
            (vault_path,)
        ).fetchone()
        if row is None:
            return None
        return IndexState(
            vault_path=row["vault_path"],
            status=row["status"],
            doc_count=row["doc_count"],
            chunk_count=row["chunk_count"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_msg=row["error_msg"],
        )

    def mark_indexing_start(self, vault_path: str) -> None:
        """标记索引起始"""
        self.db.execute(
            """INSERT INTO index_state (vault_path, status, started_at)
               VALUES (?, 'indexing', datetime('now'))
               ON CONFLICT(vault_path) DO UPDATE SET
               status='indexing', started_at=datetime('now'), error_msg=NULL""",
            (vault_path,)
        )
        self.db.commit()

    def mark_indexing_done(self, vault_path: str, doc_count: int, chunk_count: int) -> None:
        """标记索引完成"""
        self.db.execute(
            """UPDATE index_state SET
               status='ready', doc_count=?, chunk_count=?,
               finished_at=datetime('now')
               WHERE vault_path=?""",
            (doc_count, chunk_count, vault_path)
        )
        self.db.commit()

    def mark_indexing_error(self, vault_path: str, error: str) -> None:
        """标记索引错误"""
        self.db.execute(
            "UPDATE index_state SET status='error', error_msg=? WHERE vault_path=?",
            (error, vault_path)
        )
        self.db.commit()

    # ============================================================
    # Chunk 进度（幂等）
    # ============================================================

    def is_chunk_embedded(self, chunk_id: str) -> bool:
        """检查 chunk 是否已入库（幂等判断）"""
        row = self.db.execute(
            "SELECT status FROM chunk_progress WHERE chunk_id=?",
            (chunk_id,)
        ).fetchone()
        return row is not None and row["status"] == "embedded"

    def mark_chunk_pending(self, chunk_id: str, source_file: str,
                           chunk_index: int, content_hash: str) -> None:
        """标记 chunk 待处理"""
        self.db.execute(
            """INSERT OR REPLACE INTO chunk_progress
               (chunk_id, source_file, chunk_index, content_hash,
                embedding_model, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))""",
            (chunk_id, source_file, chunk_index, content_hash, self.embedder_model_name)
        )
        self.db.commit()

    def mark_chunk_embedded(self, chunk_id: str) -> None:
        """标记 chunk 已入库"""
        self.db.execute(
            "UPDATE chunk_progress SET status='embedded' WHERE chunk_id=?",
            (chunk_id,)
        )
        self.db.commit()

    def get_pending_chunks(self) -> list[dict]:
        """获取所有待处理的 chunk（断点恢复用）"""
        rows = self.db.execute(
            "SELECT * FROM chunk_progress WHERE status='pending'"
        ).fetchall()
        return [dict(r) for r in rows]

    # ============================================================
    # 变更检测
    # ============================================================

    def detect_changes(self, vault_path: str) -> list[str]:
        """
        检测 vault 内文件变更。

        对比文件系统 mtime + file_hash 与 doc_manifest 记录。
        返回变更文件列表（新增 + 修改 + 删除）。
        """
        changed: list[str] = []
        vault = Path(vault_path).expanduser().resolve()

        # 获取已索引的文件清单
        indexed = {
            row["source_file"]: {"hash": row["file_hash"], "mtime": row["file_mtime"]}
            for row in self.db.execute("SELECT * FROM doc_manifest").fetchall()
        }

        # 扫描当前文件系统
        current_files: dict[str, dict] = {}
        for md_file in vault.rglob("*.md"):
            # 排除规则（与 scanner 一致）
            rel = str(md_file.relative_to(vault))
            if ".trash" in rel or ".obsidian" in rel or ".excalidraw.md" in rel:
                continue
            if any(p.startswith(".") for p in md_file.parts):
                continue

            mtime = md_file.stat().st_mtime
            file_hash = self._file_hash(str(md_file))
            current_files[rel] = {"hash": file_hash, "mtime": mtime}

        # 检测新增/修改
        for rel, info in current_files.items():
            if rel not in indexed:
                changed.append(rel)  # 新增
            elif info["hash"] != indexed[rel]["hash"]:
                changed.append(rel)  # 修改

        # 检测删除
        for rel in indexed:
            if rel not in current_files:
                changed.append(rel)  # 删除

        return changed

    def update_doc_manifest(self, source_file: str,
                            file_hash: str, file_mtime: float,
                            chunk_count: int) -> None:
        """更新文档清单"""
        self.db.execute(
            """INSERT OR REPLACE INTO doc_manifest
               (source_file, file_hash, file_mtime, chunk_count, indexed_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (source_file, file_hash, file_mtime, chunk_count)
        )
        self.db.commit()

    def remove_doc_manifest(self, source_file: str) -> None:
        """删除文档清单记录"""
        self.db.execute("DELETE FROM doc_manifest WHERE source_file=?", (source_file,))
        self.db.commit()

    # ============================================================
    # Embedding 模型版本检测
    # ============================================================

    def _is_embedding_model_changed(self) -> bool:
        """检测 embedding 模型是否变更"""
        row = self.db.execute(
            "SELECT DISTINCT embedding_model FROM chunk_progress LIMIT 1"
        ).fetchone()
        if row is None:
            return False
        return row["embedding_model"] != self.embedder_model_name

    def get_last_embedding_model(self) -> str | None:
        """获取上次使用的 embedding 模型名"""
        row = self.db.execute(
            "SELECT DISTINCT embedding_model FROM chunk_progress LIMIT 1"
        ).fetchone()
        return row["embedding_model"] if row else None

    # ============================================================
    # 清理
    # ============================================================

    def reset_all(self, vault_path: str) -> None:
        """全量重置索引状态"""
        self.db.execute("DELETE FROM index_state WHERE vault_path=?", (vault_path,))
        self.db.execute("DELETE FROM chunk_progress")
        self.db.execute("DELETE FROM doc_manifest")
        self.db.commit()

    # ============================================================
    # 工具
    # ============================================================

    @staticmethod
    def _file_hash(file_path: str) -> str:
        """计算文件 SHA256"""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()
