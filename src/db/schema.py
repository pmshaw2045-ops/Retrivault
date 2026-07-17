"""SQLite Schema — 建表 + 迁移

三张核心表：
  - index_state     索引状态（idle|indexing|ready|error）
  - chunk_progress  Chunk 级别进度（支撑断点恢复 + 模型版本检测）
  - doc_manifest    文档清单（支撑增量更新判断）
"""

import sqlite3

SCHEMA_VERSION = 1


CREATE_TABLES_SQL = """
-- 索引状态表
CREATE TABLE IF NOT EXISTS index_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vault_path      TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'idle',  -- idle|indexing|ready|error
    doc_count       INTEGER DEFAULT 0,
    chunk_count     INTEGER DEFAULT 0,
    started_at      TEXT,
    finished_at     TEXT,
    error_msg       TEXT
);

-- Chunk 级别进度表
CREATE TABLE IF NOT EXISTS chunk_progress (
    chunk_id        TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content_hash    TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|embedded|skipped
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunk_progress_status ON chunk_progress(status);
CREATE INDEX IF NOT EXISTS idx_chunk_progress_source ON chunk_progress(source_file);

-- 文档清单表
CREATE TABLE IF NOT EXISTS doc_manifest (
    source_file     TEXT PRIMARY KEY,
    file_hash       TEXT NOT NULL,
    file_mtime      REAL NOT NULL,
    chunk_count     INTEGER DEFAULT 0,
    indexed_at      TEXT DEFAULT (datetime('now'))
);

-- 搜索历史表
CREATE TABLE IF NOT EXISTS search_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query           TEXT NOT NULL,
    answer          TEXT,
    source_count    INTEGER DEFAULT 0,
    config_json     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Schema 版本
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


def init_db(db_path: str = "data/rag.db") -> sqlite3.Connection:
    """初始化数据库：建表 + 确保 schema 版本"""
    from pathlib import Path

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(CREATE_TABLES_SQL)

    # 确保 schema_version 有记录
    existing = conn.execute("SELECT version FROM schema_version").fetchone()
    if not existing:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()

    return conn
