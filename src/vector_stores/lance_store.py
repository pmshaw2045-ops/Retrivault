"""LanceDB 向量存储

实现 VectorStore 接口。
LanceDB 嵌入式列式数据库——零外部服务依赖。
"""
import json
from datetime import date, datetime
from pathlib import Path

import lancedb
import pyarrow as pa

from src.interfaces import VectorStore


def _json_safe(obj):
    """将包含 date/datetime 的对象转为 JSON 安全格式"""
    return json.dumps(obj, ensure_ascii=False, default=_default_serializer)


def _default_serializer(o):
    """date/datetime → ISO 字符串"""
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")


class LanceVectorStore(VectorStore):
    """
    LanceDB 向量存储。

    表结构：
      - id: chunk_id (主键)
      - vector: 1024维 float32 向量
      - content: chunk 文本（用于 FTS 索引）
      - source_file, heading_path, chunk_index, chunk_hash, tags, wikilinks, frontmatter
    """

    TABLE_NAME = "chunks"
    DEFAULT_DIM = 1024  # BGE-M3 默认维度

    def __init__(self, db_path: str = "data/lancedb", dim: int = DEFAULT_DIM):
        self.db_path = db_path
        self.dim = dim
        self._db = None
        self._table = None

    @property
    def db(self):
        if self._db is None:
            Path(self.db_path).mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(self.db_path)
        return self._db

    @property
    def table(self):
        if self._table is None:
            self._ensure_table()
        return self._table

    def _ensure_table(self):
        """确保表存在，不存在则创建"""
        if self.TABLE_NAME in self.db.table_names():
            self._table = self.db.open_table(self.TABLE_NAME)
        else:
            schema = pa.schema([
                ("id", pa.string()),
                ("vector", pa.list_(pa.float32(), self.dim)),
                ("content", pa.string()),
                ("source_file", pa.string()),
                ("heading_path", pa.string()),
                ("chunk_index", pa.int32()),
                ("chunk_hash", pa.string()),
                ("tags", pa.string()),
                ("wikilinks", pa.string()),
                ("frontmatter", pa.string()),
                ("char_count", pa.int32()),
            ])
            self._table = self.db.create_table(self.TABLE_NAME, schema=schema)
            # FTS 索引可以立即建（不需要训练数据）
            self._table.create_fts_index("content")
            # 向量索引延迟到首次写入后创建（LanceDB 0.25+ 禁止空表建索引）

    def add_chunks(self, chunks: list[dict]) -> None:
        """
        批量写入 chunks。

        每个 chunk dict 必须包含：
          id, vector, content, source_file, heading_path,
          chunk_index, chunk_hash, tags, wikilinks, frontmatter, char_count

        LanceDB 写入是原子的——不会出现"部分写入"的中间态。
        首次写入后自动创建向量索引（LanceDB 0.25+ 需要训练数据）。
        """
        if not chunks:
            return

        self._ensure_table()
        was_empty = self._table.count_rows() == 0

        # 转换为 PyArrow 格式
        rows = []
        for c in chunks:
            import json
            rows.append({
                "id": c["id"],
                "vector": c["vector"],
                "content": c["content"],
                "source_file": c.get("source_file", ""),
                "heading_path": c.get("heading_path", ""),
                "chunk_index": c.get("chunk_index", 0),
                "chunk_hash": c.get("chunk_hash", ""),
                "tags": json.dumps(c.get("tags", []), ensure_ascii=False),
                "wikilinks": json.dumps(c.get("wikilinks", []), ensure_ascii=False),
                "frontmatter": _json_safe(c.get("frontmatter", {})),
                "char_count": c.get("char_count", 0),
            })

        self._table.add(rows)

        # 首次写入后尝试创建向量索引
        # PQ 索引需要至少 256 行训练数据；小数据集直接用 flat 搜索
        if was_empty:
            row_count = self._table.count_rows()
            if row_count >= 256:
                try:
                    self._table.create_index(num_sub_vectors=96)
                except Exception:
                    # 索引创建失败不影响功能——退化到 flat 搜索
                    pass

    def search(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[dict]:
        """
        向量搜索。

        返回 top_k 个最相似的 chunk，包含 content + metadata + _distance。
        """
        self._ensure_table()
        results = self._table.search(query_vector).limit(top_k).to_list()
        return self._format_results(results)

    def search_hybrid(
        self, query_vector: list[float], query_text: str, top_k: int = 5
    ) -> list[dict]:
        """混合搜索：向量 + FTS 文本匹配"""
        self._ensure_table()
        results = (
            self._table
            .search(query_vector, fts_columns=["content"])
            .limit(top_k * 3)
            .to_list()
        )
        query_terms = set(query_text.lower().split())
        for r in results:
            content_lower = r.get("content", "").lower()
            hits = sum(1 for t in query_terms if t in content_lower)
            if hits > 0:
                r["_distance"] = max(0.01, r.get("_distance", 1.0) - hits * 0.05)
        results.sort(key=lambda r: r.get("_distance", 1.0))
        return self._format_results(results[:top_k])

    def clear(self) -> None:
        """清空向量库（重建空表）"""
        if self._db is None:
            self._db = lancedb.connect(self.db_path)
        if self.TABLE_NAME in self._db.table_names():
            self._db.drop_table(self.TABLE_NAME)
        self._table = None

    def delete_by_source(self, source_file: str) -> int:
        """删除指定源文件的所有 chunk。返回删除数量。"""
        self._ensure_table()
        count_before = self.count()
        self._table.delete(f"source_file = '{source_file}'")
        count_after = self.count()
        return count_before - count_after

    def count(self) -> int:
        """返回表中 chunk 总数"""
        self._ensure_table()
        return self._table.count_rows()

    @staticmethod
    def _format_results(results: list[dict]) -> list[dict]:
        """格式化搜索结果，反序列化 JSON 字段"""
        import json
        for r in results:
            for field in ("tags", "wikilinks"):
                if field in r and isinstance(r[field], str):
                    try:
                        r[field] = json.loads(r[field])
                    except json.JSONDecodeError:
                        r[field] = []
            if "frontmatter" in r and isinstance(r["frontmatter"], str):
                try:
                    r["frontmatter"] = json.loads(r["frontmatter"])
                except json.JSONDecodeError:
                    r["frontmatter"] = {}
        return results
