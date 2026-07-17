"""测试 Chunker — MD 结构感知分块引擎"""

from src.pipeline.chunker import Chunker


class TestBasicChunking:
    """基础分块"""

    def test_single_short_paragraph(self):
        """单个短段落 → 一个 chunk"""
        chunker = Chunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.chunk("# Title\n\nA short paragraph.")
        assert len(chunks) == 1
        assert "A short paragraph" in chunks[0].content

    def test_multiple_short_paragraphs_merge(self):
        """多个短段落合并为一个 chunk"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = "# Title\n\nPar1.\n\nPar2.\n\nPar3."
        chunks = chunker.chunk(content)
        # 三段都很短，应该合并为一个 chunk
        assert len(chunks) == 1
        assert "Par1" in chunks[0].content
        assert "Par3" in chunks[0].content

    def test_long_content_splits(self):
        """长内容分裂多个 chunk"""
        chunker = Chunker(chunk_size=100, chunk_overlap=0)
        # 生成一个 300+ 字符的段落
        content = "# Title\n\n" + "This is a long paragraph. " * 30
        chunks = chunker.chunk(content)
        assert len(chunks) >= 2  # 至少 2 个 chunk


class TestHeadingPreservation:
    """标题层级保持"""

    def test_heading_in_metadata(self):
        """chunk 的 metadata 包含 heading_path"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = """## 存储组件

LanceDB 是一个嵌入式向量数据库。它提供了高效的向量检索和存储能力。
支持多种索引类型，包括 IVF 和 HNSW，可以根据数据规模和查询需求灵活选择。

### 向量索引

使用 IVF 索引可以加速大规模数据的检索。
对于百万级向量，IVF 索引比暴力搜索快 10 倍以上。
但需要合理设置索引参数以平衡速度和精度。"""
        chunks = chunker.chunk(content, source_file="test.md")
        # 检查 heading_path 被正确记录
        heading_paths = [c.metadata.get("heading_path", "") for c in chunks]
        assert any("存储组件" in hp for hp in heading_paths), f"heading_paths: {heading_paths}"

    def test_h2_creates_boundary(self):
        """## 二级标题是逻辑分界点"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = """## 第一节
Section one content. This is a longer paragraph that ensures each section
has enough text to stand on its own as a separate chunk. The chunker's
merge logic only combines chunks smaller than the minimum threshold.
Both sections need at least 200 characters to avoid being merged.
This extra text here guarantees the first section passes the threshold.

## 第二节
Section two content is also padded sufficiently to avoid being merged
into the first section. The paragraph has enough text to exceed the
minimum chunk size threshold. Now the chunker should keep them separate
since both are above the minimum size limit for independent chunks.
Both sections now comfortably exceed the 200 character minimum."""
        chunks = chunker.chunk(content, source_file="test.md")
        # 两个 ## 应该产生至少 2 个 chunk
        assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}"

    def test_heading_hierarchy(self):
        """标题层级 ## > ### 保留在 heading_path 中"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = """## 架构设计

顶层介绍部分，这里描述了整体架构的核心理念和设计原则。
架构设计需要考虑可扩展性、可维护性和性能等多个维度。
这些都是在实际项目中反复验证的经验总结，值得深入思考。

### 存储层

LanceDB 提供向量存储能力，支持高效的相似度搜索。
它与 SQLite 配合使用，分别管理向量数据和结构化元数据。
存储层的设计直接决定了系统的可扩展性和数据可靠性。

### 通信层

Redis 作为缓存层，提供快速的数据访问。
同时支持事件驱动的消息队列，实现组件间的异步通信。
这种架构设计能够有效降低系统各组件之间的耦合度。"""
        chunks = chunker.chunk(content, source_file="test.md")
        # 验证 heading_path 正确记录了父级标题
        heading_paths = [c.metadata.get("heading_path", "") for c in chunks]
        assert any("架构设计" in hp for hp in heading_paths), f"heading_paths: {heading_paths}"
        # 子标题内容应包含在 chunk 中（虽然是 merge 后，但内容仍在）
        combined = " ".join(c.content for c in chunks)
        assert "存储层" in combined or "LanceDB" in combined, "存储层相关内容应存在于某个 chunk 中"


class TestOverlap:
    """相邻 chunk 重叠"""

    def test_overlap_enabled(self):
        """重叠开启时相邻 chunk 共享内容"""
        chunker = Chunker(chunk_size=200, chunk_overlap=50)
        content = "# Title\n\n" + "abcdefghij " * 30  # 长段落
        chunks = chunker.chunk(content)
        assert len(chunks) >= 2

        # 前一个 chunk 的结尾应在后一个 chunk 的开头出现
        last_50 = chunks[0].content[-50:]
        assert last_50 in chunks[1].content

    def test_no_overlap(self):
        """chunk_overlap=0 时不重叠"""
        chunker = Chunker(chunk_size=200, chunk_overlap=0)
        content = "# Title\n\n" + "abcdefghij " * 30
        chunks = chunker.chunk(content)
        assert len(chunks) >= 2
        # 确保不重叠（第一个 chunk 的尾字符不等于第二个的开头)
        # 这是一个近似验证
        if len(chunks) > 1:
            assert chunks[0].content[-20:] != chunks[1].content[:20]


class TestCodeBlockProtection:
    """代码块不被拦腰截断"""

    def test_code_block_stays_intact(self):
        """围栏代码块不会被拆分到两个 chunk"""
        chunker = Chunker(chunk_size=300, chunk_overlap=0)
        content = """## 代码示例

```python
def hello():
    print("Hello, world!")
    return True
```

后续文本。"""
        chunks = chunker.chunk(content)
        # 验证：```python 出现的位置，其 chunk 中必须有完整的代码块
        for chunk in chunks:
            if "```python" in chunk.content:
                assert "```" in chunk.content[chunk.content.index("```python") + 10 :]
                # 应该有闭合 ```
                after_open = chunk.content[chunk.content.index("```python") :]
                assert after_open.count("```") >= 2  # 开头和结尾

    def test_inline_code_not_broken(self):
        """行内代码不被拆断"""
        chunker = Chunker(chunk_size=200, chunk_overlap=0)
        content = "# Title\n\n参考 `ChromaDB.query()` 方法。"
        chunks = chunker.chunk(content)
        for chunk in chunks:
            # 所有 ` 成对出现
            backtick_count = chunk.content.count("`")
            assert backtick_count % 2 == 0, f"Unbalanced backticks in chunk: {chunk.content[:50]}"


class TestSentenceSplitting:
    """段落 > chunk_size 时按句子拆分"""

    def test_long_paragraph_splits_by_sentence(self):
        """超长段落按句子（。！？\n）拆分"""
        chunker = Chunker(chunk_size=50, chunk_overlap=0)
        # 长段落，多句话
        sentences = [
            "这是第一句话，介绍基本概念。",
            "这是第二句话，展开详细说明！",
            "这是第三句话？提供一个疑问。",
            "这是第四句话，总结前面的内容。",
        ]
        content = "# Title\n\n" + "".join(sentences)
        chunks = chunker.chunk(content)
        assert len(chunks) >= 2

    def test_sentence_boundary_respected(self):
        """不会在句子中间截断"""
        chunker = Chunker(chunk_size=80, chunk_overlap=0)
        content = "# T\n\n" + "第一句话。第二句话。第三句话。第四句话。第五句话。"
        chunks = chunker.chunk(content)
        # 每个 chunk 应该以句号结尾或以句号开头（除了首尾）
        for i, chunk in enumerate(chunks):
            stripped = chunk.content.strip()
            # 至少不以残缺方式结尾——结尾是标点符号
            assert (
                stripped[-1] in "。！？.\n,，;；:：" or i == len(chunks) - 1
            ), f"Chunk {i} ends with '{stripped[-5:]}'"


class TestMetadata:
    """chunk metadata 完整性"""

    def test_chunk_index_increments(self):
        """chunk_index 从 0 开始递增"""
        chunker = Chunker(chunk_size=200, chunk_overlap=0)
        content = "# Title\n\n" + "long text " * 100
        chunks = chunker.chunk(content, source_file="test.md")
        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i

    def test_source_file_in_metadata(self):
        """source_file 被记录"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = "# Title\n\nContent."
        chunks = chunker.chunk(content, source_file="my/note.md")
        assert chunks[0].metadata["source_file"] == "my/note.md"

    def test_chunk_hash_is_unique(self):
        """每个 chunk 有唯一的 content_hash"""
        chunker = Chunker(chunk_size=200, chunk_overlap=0)
        content = "# Title\n\n" + "unique " * 50
        chunks = chunker.chunk(content)
        hashes = [c.metadata["chunk_hash"] for c in chunks]
        assert len(set(hashes)) == len(hashes)  # 全部唯一

    def test_chunk_id_unique(self):
        """每个 chunk 有唯一的 chunk_id"""
        chunker = Chunker(chunk_size=200, chunk_overlap=0)
        content = "# Title\n\n" + "id " * 50
        chunks = chunker.chunk(content, source_file="test.md")
        ids = [c.metadata["chunk_id"] for c in chunks]
        assert len(set(ids)) == len(ids)

    def test_tags_wikilinks_in_metadata(self):
        """tags 和 wikilinks 被传入 metadata"""
        chunker = Chunker(chunk_size=500, chunk_overlap=0)
        content = "# Title\n\nContent with info."
        chunks = chunker.chunk(
            content,
            source_file="test.md",
            tags=["#test", "#example"],
            wikilinks=["LinkA", "LinkB"],
        )
        assert "#test" in chunks[0].metadata["tags"]
        assert "LinkA" in chunks[0].metadata["wikilinks"]


class TestEdgeCases:
    """边界情况"""

    def test_empty_content(self):
        """空内容返回空列表"""
        chunker = Chunker()
        chunks = chunker.chunk("")
        assert chunks == []

    def test_only_title(self):
        """只有标题无正文"""
        chunker = Chunker()
        chunks = chunker.chunk("# Just a title")
        assert len(chunks) == 1
        assert "Just a title" in chunks[0].content

    def test_very_large_chunk_size(self):
        """chunk_size 远大于内容 → 单 chunk"""
        chunker = Chunker(chunk_size=10000, chunk_overlap=0)
        content = "# Title\n\nShort content."
        chunks = chunker.chunk(content)
        assert len(chunks) == 1

    def test_very_small_chunk_size(self):
        """极小的 chunk_size 仍然产生合法 chunk"""
        chunker = Chunker(chunk_size=20, chunk_overlap=5)
        content = "# T\n\nA sentence. Another one."
        chunks = chunker.chunk(content)
        # 即使 chunk_size 极小，也不应该出错
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk.content) > 0
