"""MD 结构感知分块引擎

分块规则（优先级从高到低）：
1. 以 ## 二级标题为逻辑分界点（保留 heading_path 作为 chunk metadata）
2. 每个 ## section 内按 \n\n（段落）拆分
3. 段落 < chunk_size → 合并相邻段落直到接近 chunk_size
4. 段落 > chunk_size → 按 sentence（。！？\n）拆分
5. 句子 > chunk_size（代码块等极端情况） → 按字符截断
6. overlap：相邻 chunk 间以完整 sentence 为单位重叠（overlap_sentences = 2）
7. 代码块（```...```）作为原子单元，不拦腰截断
"""
import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """分块结果"""
    content: str                              # chunk 文本
    metadata: dict = field(default_factory=dict)  # 元数据


class Chunker:
    """
    MD 结构感知分块器。

    Args:
        chunk_size: 目标 chunk 大小（字符数，非 token 数）
        chunk_overlap: 相邻 chunk 重叠大小（字符数）
    """

    # 句子边界（避免在代码块内误匹配，用先行断言排除代码块）
    SENTENCE_BOUNDARY_RE = re.compile(r"[。！？]\s*")

    # 段落分隔符
    PARAGRAPH_SEP = "\n\n"

    # 围栏代码块
    FENCE_RE = re.compile(r"```")

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = max(200, chunk_size // 4)  # 最小 chunk 尺寸

    def chunk(
        self,
        content: str,
        source_file: str = "unknown.md",
        heading_path: str = "",
        tags: list[str] | None = None,
        wikilinks: list[str] | None = None,
        frontmatter: dict | None = None,
    ) -> list[Chunk]:
        """
        将文档内容拆分为 chunk 列表。

        Args:
            content: Markdown 全文
            source_file: 源文件路径
            heading_path: 当前标题路径（递归使用）
            tags: 文档级标签
            wikilinks: 文档级 wikilink 列表
            frontmatter: 文档级 frontmatter

        Returns:
            Chunk 列表
        """
        if not content.strip():
            return []

        # ★ 剥离 frontmatter：正文里不应包含 YAML 头，它只在 metadata 里
        content = self._strip_frontmatter(content)

        # Step 1: 按 ## 标题拆分为 section
        sections = self._split_by_headings(content)

        # Step 2: 对每个 section 分块
        all_chunks: list[Chunk] = []
        for section_heading, section_body in sections:
            current_path = self._join_path(heading_path, section_heading)
            section_chunks = self._chunk_section(section_body, current_path)
            all_chunks.extend(section_chunks)

        # Step 3: 填充 chunk 的 metadata
        for i, chunk in enumerate(all_chunks):
            chunk.metadata.update({
                "source_file": source_file,
                "chunk_index": i,
                "chunk_id": self._make_chunk_id(source_file, i),
                "chunk_hash": self._hash_content(chunk.content),
                "tags": tags or [],
                "wikilinks": wikilinks or [],
                "frontmatter": frontmatter or {},
                "char_count": len(chunk.content),
            })

        # Step 4: 跨 section 合并过小的 chunk
        all_chunks = self._merge_tiny_chunks(all_chunks, "root")

        # 重新分配 chunk_index
        for i, chunk in enumerate(all_chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["chunk_id"] = self._make_chunk_id(source_file, i)
            chunk.metadata["char_count"] = len(chunk.content)

        return all_chunks

    # ============================================================
    # Step 1: 按 ## 标题拆分
    # ============================================================

    @staticmethod
    def _split_by_headings(content: str) -> list[tuple[str, str]]:
        """按 ## 标题拆分为 (heading, body) 列表。空 ## 不设边界。"""
        heading_re = re.compile(r"^##\s*(.*)$", re.MULTILINE)

        matches = list(heading_re.finditer(content))

        if not matches:
            return [("", content.strip())]

        sections: list[tuple[str, str]] = []

        # 第一个 ## 之前的内容
        first_pos = matches[0].start()
        if first_pos > 0:
            before = content[:first_pos].strip()
            if before:
                sections.append(("", before))

        for i, match in enumerate(matches):
            heading = match.group(1).strip()
            # 空 ## 不设边界，跳过
            if not heading:
                continue
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            if body:
                sections.append((heading, body))

        return sections

    # ============================================================
    # Step 2: Section 内分块
    # ============================================================

    def _chunk_section(self, body: str, heading_path: str) -> list[Chunk]:
        """对单个 section 的正文分块，同时追踪 ### 子标题更新 heading_path"""
        # 先按 ### 拆分为子区域（不做 chunk 边界，但更新 heading_path）
        sub_regions = self._split_by_subheading(body, heading_path)

        all_chunks: list[Chunk] = []
        for region_path, region_body in sub_regions:
            sub_chunks = self._chunk_plain_section(region_body, region_path)
            all_chunks.extend(sub_chunks)

        # 应用 overlap（跨子区域）
        if self.chunk_overlap > 0 and len(all_chunks) >= 2:
            all_chunks = self._apply_overlap(all_chunks)

        return all_chunks

    @staticmethod
    def _split_by_subheading(body: str, parent_path: str) -> list[tuple[str, str]]:
        """
        按 ### 子标题拆分（不强制 chunk 边界，仅更新 heading_path）。

        返回 [(heading_path, body), ...]
        """
        sub_re = re.compile(r"^###\s+(.+)$", re.MULTILINE)
        matches = list(sub_re.finditer(body))

        if not matches:
            return [(parent_path, body.strip())]

        regions: list[tuple[str, str]] = []

        first_pos = matches[0].start()
        if first_pos > 0:
            before = body[:first_pos].strip()
            if before:
                regions.append((parent_path, before))

        for i, match in enumerate(matches):
            sub_heading = match.group(1).strip()
            sub_path = f"{parent_path} > {sub_heading}" if parent_path else sub_heading
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            region_body = body[start:end].strip()
            if region_body:
                regions.append((sub_path, region_body))

        return regions

    def _chunk_plain_section(self, body: str, heading_path: str) -> list[Chunk]:
        # 提取代码块作为原子单元
        atoms = self._split_atoms(body)

        chunks: list[Chunk] = []
        current_text = ""
        current_len = 0

        for atom in atoms:
            atom_len = len(atom)

            if current_len + atom_len <= self.chunk_size:
                # 可以放入当前 chunk
                if current_text:
                    current_text += "\n\n" + atom
                else:
                    current_text = atom
                current_len = len(current_text)
            else:
                # 当前 chunk 已满
                if current_text:
                    chunks.append(Chunk(
                        content=current_text,
                        metadata={"heading_path": heading_path},
                    ))

                # 如果这个 atom 本身也超长，需要 sentence-level 拆分
                if atom_len > self.chunk_size:
                    sub_chunks = self._split_long_atom(atom, heading_path)
                    chunks.extend(sub_chunks)
                    current_text = ""
                    current_len = 0
                else:
                    current_text = atom
                    current_len = atom_len

        # 最后一个 chunk
        if current_text:
            chunks.append(Chunk(
                content=current_text,
                metadata={"heading_path": heading_path},
            ))

        return chunks

    def _merge_tiny_chunks(self, chunks: list[Chunk], heading_path: str) -> list[Chunk]:
        """合并过小的 chunk 到相邻 chunk（优先往前合并，不行则往后合并）"""
        if len(chunks) < 2:
            return chunks

        merged = []
        for chunk in chunks:
            if len(chunk.content) < self.min_chunk_size and merged:
                prev = merged[-1]
                new_len = len(prev.content) + 2 + len(chunk.content)
                if new_len <= self.chunk_size * 1.2:
                    prev.content = prev.content + "\n\n" + chunk.content
                    # 保留前一个 chunk 的 heading_path（优先用 parent heading）
                    continue
            merged.append(chunk)

        # 前向合并已经处理了大部份，但还有少量开头 chunk 太小（前面没东西可合并）
        # 尝试把开头小 chunk 往后合并（保留第一个 chunk 的 heading_path）
        if len(merged) >= 2 and len(merged[0].content) < self.min_chunk_size:
            first = merged[0]
            second = merged[1]
            new_len = len(first.content) + 2 + len(second.content)
            if new_len <= self.chunk_size * 1.2:
                second.content = first.content + "\n\n" + second.content
                # 保留后一个 chunk 的 heading_path（第一个 chunk 可能没有具体 heading）
                merged.pop(0)

        return merged or chunks

    # ============================================================
    # 原子拆分（保护代码块）
    # ============================================================

    def _split_atoms(self, body: str) -> list[str]:
        """
        将正文拆分为原子单元。

        原子 = 代码块（不可拆分） + 普通段落（可继续拆分）。
        返回的每个 atom 自身不会再被截断。
        """
        atoms: list[str] = []
        pos = 0

        for match in self.FENCE_RE.finditer(body):
            start = match.start()

            # 前面是普通内容
            if start > pos:
                before = body[pos:start].strip()
                # 按段落拆分普通内容
                if before:
                    atoms.extend(
                        p.strip() for p in before.split(self.PARAGRAPH_SEP) if p.strip()
                    )

            # 找到配对 ```
            end = self.FENCE_RE.search(body, match.end())
            if end:
                code_block = body[start:end.end()]
                atoms.append(code_block)
                pos = end.end()
            else:
                # 无闭合，后面全算当前块
                atoms.append(body[start:])
                pos = len(body)
                break

        # 最后一个代码块后的内容
        if pos < len(body):
            remaining = body[pos:].strip()
            if remaining:
                atoms.extend(
                    p.strip() for p in remaining.split(self.PARAGRAPH_SEP) if p.strip()
                )

        return atoms

    # ============================================================
    # 超长 atom 的句子级拆分
    # ============================================================

    def _split_long_atom(self, atom: str, heading_path: str) -> list[Chunk]:
        """超长 atom（> chunk_size）按句子拆分"""
        # 代码块不拆——如果单个代码块超过 chunk_size，直接作为一个 chunk
        if atom.startswith("```"):
            return [Chunk(content=atom, metadata={"heading_path": heading_path})]

        # 按句子拆分
        sentences = self.SENTENCE_BOUNDARY_RE.split(atom)

        # 一些标点可能产生空字符串
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[Chunk] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 <= self.chunk_size:
                current = (current + "。" + sent) if current else sent
            else:
                if current:
                    chunks.append(Chunk(content=current, metadata={"heading_path": heading_path}))
                # 如果单个句子超长（极端情况），按字符截断
                if len(sent) > self.chunk_size:
                    sub = self._split_by_chars(sent, heading_path)
                    chunks.extend(sub)
                    current = ""
                else:
                    current = sent

        if current:
            chunks.append(Chunk(content=current, metadata={"heading_path": heading_path}))

        return chunks

    def _split_by_chars(self, text: str, heading_path: str) -> list[Chunk]:
        """极端情况：按字符截断"""
        chunks: list[Chunk] = []
        for i in range(0, len(text), self.chunk_size):
            chunk_text = text[i:i + self.chunk_size]
            chunks.append(Chunk(content=chunk_text, metadata={"heading_path": heading_path}))
        return chunks

    # ============================================================
    # Overlap
    # ============================================================

    def _apply_overlap(self, chunks: list[Chunk]) -> list[Chunk]:
        """
        在相邻 chunk 间添加重叠。

        前一个 chunk 的结尾部分附加到后一个 chunk 的开头。
        以完整 sentence 为单位进行重叠。
        """
        if not chunks or len(chunks) < 2:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = result[-1]
            curr = chunks[i]

            # 从 prev 的结尾取 overlap_chars 个字符
            overlap_chars = min(self.chunk_overlap, len(prev.content))
            if overlap_chars > 0:
                overlap_text = prev.content[-overlap_chars:]
                # 调整到最近的句子边界
                overlap_text = self._trim_to_sentence_start(overlap_text)
                if overlap_text:
                    curr.content = overlap_text + "\n\n" + curr.content

            result.append(curr)

        return result

    @staticmethod
    def _trim_to_sentence_start(text: str) -> str:
        """裁剪重叠文本到最近的句子开头"""
        # 找第一个句号/问号/感叹号之后的位置
        for i, ch in enumerate(text):
            if ch in "。！？":
                # 从下一个句子开头取
                after = text[i + 1:].lstrip()
                if after:
                    return after
                return text[i + 1:]  # 至少跳过标点
        return text

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """剥离 YAML frontmatter（---...---），返回正文"""
        if not content.startswith("---"):
            return content
        # 找第二个 ---
        rest = content[3:]
        idx = rest.find("\n---")
        if idx == -1:
            return content
        return rest[idx + 4:].lstrip()

    @staticmethod
    def _join_path(parent: str, child: str) -> str:
        """合并标题路径"""
        if not parent:
            return child
        if not child:
            return parent
        return f"{parent} > {child}"

    @staticmethod
    def _make_chunk_id(source_file: str, chunk_index: int) -> str:
        """生成 chunk_id：hash(source_file + chunk_index)"""
        raw = f"{source_file}#{chunk_index}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _hash_content(content: str) -> str:
        """生成 content_hash：sha256(content)"""
        return hashlib.sha256(content.encode()).hexdigest()
