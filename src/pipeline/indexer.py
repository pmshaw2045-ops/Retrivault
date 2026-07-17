"""索引编排器

编排全量/增量/恢复索引流程：
  scanner.scan() → parser.parse() → chunker.chunk() → embedder.embed() → vector_store.add()
"""
import hashlib
from collections import defaultdict
from pathlib import Path

from src.interfaces import EmbeddingProvider, VectorStore
from src.pipeline.chunker import Chunker
from src.pipeline.index_manager import IndexDecision, IndexManager
from src.pipeline.obsidian_parser import ObsidianParser
from src.pipeline.scanner import ObsidianScanner, ScannedDocument


class Indexer:
    """
    索引编排器。

    协调 scanner、parser、chunker、embedder、vector_store 协同工作。
    通过 IndexManager 管理状态和进度。
    """

    def __init__(
        self,
        scanner: ObsidianScanner,
        parser: ObsidianParser,
        chunker: Chunker,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        index_manager: IndexManager,
    ):
        self.scanner = scanner
        self.parser = parser
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.index_manager = index_manager

    def run(self, vault_path: str,
            progress_callback=None) -> dict:
        """
        根据启动决策执行对应的索引操作。

        Args:
            vault_path: Obsidian vault 路径
            progress_callback: 可选进度回调 fn(phase, current, total)

        Returns:
            {"status": "ok"|"skipped", "doc_count": N, "chunk_count": N}
        """
        decision = self.index_manager.on_startup(vault_path)

        if decision == IndexDecision.SKIP:
            state = self.index_manager.get_state(vault_path)
            return {"status": "skipped", "doc_count": state.doc_count,
                    "chunk_count": state.chunk_count}

        elif decision == IndexDecision.FIRST_INDEX:
            return self._full_index(vault_path, progress_callback)

        elif decision == IndexDecision.RESUME:
            return self._resume_index(vault_path, progress_callback)

        elif decision == IndexDecision.REINDEX:
            self.index_manager.reset_all(vault_path)
            # 清空向量库
            self._clear_vector_store()
            return self._full_index(vault_path, progress_callback)

        elif decision == IndexDecision.INCREMENTAL:
            changed = self.index_manager.detect_changes(vault_path)
            return self._incremental_index(vault_path, changed, progress_callback)

    def _full_index(self, vault_path: str, progress_callback=None) -> dict:
        """全量索引"""
        self.index_manager.mark_indexing_start(vault_path)

        docs = self.scanner.scan(vault_path)
        total_docs = len(docs)

        all_chunks: list[dict] = []
        for i, doc in enumerate(docs):
            if progress_callback:
                progress_callback("scanning", i + 1, total_docs)

            parsed = self.parser.parse(doc.content, doc.file_path)

            chunks = self.chunker.chunk(
                parsed.content,
                source_file=parsed.file_path,
                tags=parsed.tags,
                wikilinks=parsed.wikilinks,
                frontmatter=parsed.frontmatter,
            )

            # 记录进度
            file_hash = _sha256_file(doc.file_path)
            self.index_manager.update_doc_manifest(
                parsed.file_path, file_hash, doc.file_mtime, len(chunks)
            )

            for chunk in chunks:
                chunk_id = chunk.metadata["chunk_id"]
                self.index_manager.mark_chunk_pending(
                    chunk_id, parsed.file_path,
                    chunk.metadata["chunk_index"], chunk.metadata["chunk_hash"]
                )
                all_chunks.append(chunk)

        # 批量 Embedding + 入库
        self._embed_and_store(all_chunks, progress_callback)

        self.index_manager.mark_indexing_done(
            vault_path, doc_count=total_docs, chunk_count=len(all_chunks)
        )
        return {"status": "ok", "doc_count": total_docs, "chunk_count": len(all_chunks)}

    def _resume_index(self, vault_path: str, progress_callback=None) -> dict:
        """从断点恢复索引（只重新处理有 pending chunk 的文件）"""
        pending = self.index_manager.get_pending_chunks()
        if not pending:
            self.index_manager.mark_indexing_done(vault_path, 0, 0)
            return {"status": "ok", "doc_count": 0, "chunk_count": 0}

        # 只读取有 pending chunk 的源文件，避免全量扫描
        pending_by_file: dict[str, set] = defaultdict(set)
        for p in pending:
            pending_by_file[p["source_file"]].add(p["chunk_id"])

        import yaml
        docs = []
        for abs_path in pending_by_file:
            p = Path(abs_path)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                fm = yaml.safe_load(content.split("---", 2)[1]) if content.startswith("---") and "---" in content[3:] else None
                docs.append(ScannedDocument(
                    file_path=str(p),
                    file_name=p.name,
                    content=content,
                    frontmatter=fm if isinstance(fm, dict) else None,
                    file_mtime=p.stat().st_mtime,
                ))

        doc_map = {d.file_path: d for d in docs}

        all_chunks: list = []
        for source_file, pending_ids in pending_by_file.items():
            if source_file not in doc_map:
                continue
            doc = doc_map[source_file]
            parsed = self.parser.parse(doc.content, doc.file_path)

            # 每文件只分块一次
            file_chunks = self.chunker.chunk(
                parsed.content, source_file=source_file,
                tags=parsed.tags, wikilinks=parsed.wikilinks,
                frontmatter=parsed.frontmatter,
            )
            for fc in file_chunks:
                if fc.metadata["chunk_id"] in pending_ids:
                    all_chunks.append(fc)

        self._embed_and_store(all_chunks, progress_callback)

        total_docs = len(docs)
        state = self.index_manager.get_state(vault_path)
        self.index_manager.mark_indexing_done(
            vault_path, doc_count=total_docs,
            chunk_count=state.chunk_count if state else len(all_chunks)
        )
        return {"status": "ok", "doc_count": total_docs, "chunk_count": len(all_chunks)}

    def _incremental_index(self, vault_path: str,
                           changed_files: list[str],
                           progress_callback=None) -> dict:
        """增量索引"""
        docs = self.scanner.scan(vault_path)
        doc_map = {d.file_path: d for d in docs}

        all_chunks: list = []
        for rel_path in changed_files:
            abs_path = str(Path(vault_path) / rel_path)
            if abs_path not in doc_map:
                # 文件被删除
                self.vector_store.delete_by_source(abs_path)
                self.index_manager.remove_doc_manifest(abs_path)
                continue

            doc = doc_map[abs_path]
            parsed = self.parser.parse(doc.content, doc.file_path)
            chunks = self.chunker.chunk(
                parsed.content, source_file=parsed.file_path,
                tags=parsed.tags, wikilinks=parsed.wikilinks,
                frontmatter=parsed.frontmatter,
            )

            # 删除旧数据
            self.vector_store.delete_by_source(abs_path)

            # 标记新 chunk
            file_hash = _sha256_file(doc.file_path)
            self.index_manager.update_doc_manifest(
                parsed.file_path, file_hash, doc.file_mtime, len(chunks)
            )

            for chunk in chunks:
                chunk_id = chunk.metadata["chunk_id"]
                self.index_manager.mark_chunk_pending(
                    chunk_id, parsed.file_path,
                    chunk.metadata["chunk_index"], chunk.metadata["chunk_hash"]
                )
                all_chunks.append(chunk)

        self._embed_and_store(all_chunks, progress_callback)

        total_docs = len(docs)
        return {"status": "ok", "doc_count": total_docs, "chunk_count": len(all_chunks)}

    def _embed_and_store(self, chunks: list, progress_callback=None):
        """批量 Embedding + 写入 LanceDB"""
        if not chunks:
            return

        texts = [c.content for c in chunks]
        embeddings = self.embedder.embed_documents(texts)

        store_chunks = []
        for i, chunk in enumerate(chunks):
            store_chunks.append({
                "id": chunk.metadata["chunk_id"],
                "vector": embeddings[i],
                "content": chunk.content,
                "source_file": chunk.metadata["source_file"],
                "heading_path": chunk.metadata.get("heading_path", ""),
                "chunk_index": chunk.metadata["chunk_index"],
                "chunk_hash": chunk.metadata["chunk_hash"],
                "tags": chunk.metadata.get("tags", []),
                "wikilinks": chunk.metadata.get("wikilinks", []),
                "frontmatter": chunk.metadata.get("frontmatter", {}),
                "char_count": chunk.metadata.get("char_count", 0),
            })

            if progress_callback:
                progress_callback("embedding", i + 1, len(chunks))

        # 批量写入
        self.vector_store.add_chunks(store_chunks)

        # 标记所有 chunk 为 embedded
        for chunk in chunks:
            self.index_manager.mark_chunk_embedded(chunk.metadata["chunk_id"])

    def _clear_vector_store(self):
        """清空向量库（重建表）"""
        import lancedb
        db = lancedb.connect(self.vector_store.db_path)
        if self.vector_store.TABLE_NAME in db.table_names():
            db.drop_table(self.vector_store.TABLE_NAME)


def _sha256_file(file_path: str) -> str:
    """计算文件 SHA256"""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()
