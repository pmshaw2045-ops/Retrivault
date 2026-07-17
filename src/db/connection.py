"""SQLite 数据库连接管理"""

import sqlite3
from pathlib import Path


class Database:
    """
    SQLite 连接管理器。

    单连接模式（个人量级不需要连接池）。
    """

    def __init__(self, db_path: str = "data/rag.db"):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            # 确保父目录存在
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")  # 更好的并发
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# 模块级单例
_db: Database | None = None


def get_db(db_path: str = "data/rag.db") -> Database:
    """获取数据库实例"""
    global _db
    if _db is None:
        _db = Database(db_path)
    return _db


def close_db():
    """关闭数据库连接"""
    global _db
    if _db:
        _db.close()
        _db = None
