"""测试 ObsidianParser — wikilink/frontmatter/tag/callout/embed 解析"""
from src.pipeline.obsidian_parser import ObsidianParser


class TestWikilinks:
    """[[wikilink]] 解析"""

    def test_basic_wikilink(self):
        """基本 wikilink"""
        parser = ObsidianParser()
        doc = parser.parse("[[Agent 架构选型]]", "test.md")
        assert "Agent 架构选型" in doc.wikilinks

    def test_wikilink_with_alias(self):
        """带别名的 wikilink [[目标|显示文本]]"""
        parser = ObsidianParser()
        doc = parser.parse("参考 [[Agent Runtime 组件表|组件表]]", "test.md")
        assert "Agent Runtime 组件表" in doc.wikilinks  # 提取目标，非显示文本
        assert len(doc.wikilinks) == 1

    def test_wikilink_with_heading(self):
        """带章节锚点的 wikilink [[文档#章节]]"""
        parser = ObsidianParser()
        doc = parser.parse("见 [[Agent 落地12条#存储选型]]", "test.md")
        assert "Agent 落地12条" in doc.wikilinks  # 提取文件名部分
        assert len(doc.wikilinks) == 1

    def test_wikilink_with_heading_and_alias(self):
        """[[文档#章节|别名]]"""
        parser = ObsidianParser()
        doc = parser.parse("[[Agent框架#L5|长期记忆]]", "test.md")
        assert "Agent框架" in doc.wikilinks

    def test_multiple_wikilinks(self):
        """多个 wikilink"""
        parser = ObsidianParser()
        doc = parser.parse("参考 [[A]] 和 [[B]] 还有 [[C]]", "test.md")
        assert doc.wikilinks == ["A", "B", "C"]

    def test_no_wikilinks(self):
        """无 wikilink 返回空列表"""
        parser = ObsidianParser()
        doc = parser.parse("普通文本，没有链接", "test.md")
        assert doc.wikilinks == []

    def test_wikilink_dedup(self):
        """重复 wikilink 去重"""
        parser = ObsidianParser()
        doc = parser.parse("[[A]] 和 [[A]] 和 [[A]]", "test.md")
        assert doc.wikilinks == ["A"]


class TestTags:
    """#tag 解析"""

    def test_basic_tags(self):
        parser = ObsidianParser()
        doc = parser.parse("一些内容 #agent #architecture", "test.md")
        assert "#agent" in doc.tags
        assert "#architecture" in doc.tags

    def test_nested_tags(self):
        """嵌套标签 #agent/runtime"""
        parser = ObsidianParser()
        doc = parser.parse("标签 #agent/runtime/core", "test.md")
        assert "#agent/runtime/core" in doc.tags

    def test_chinese_tags(self):
        """中文标签"""
        parser = ObsidianParser()
        doc = parser.parse("标签 #架构/微服务", "test.md")
        assert "#架构/微服务" in doc.tags

    def test_tag_not_in_code_block(self):
        """代码块内的 # 不应被识别为 tag"""
        parser = ObsidianParser()
        doc = parser.parse("```python\n# this is a comment\nx = 1\n```\n真正的 #tag", "test.md")
        assert "#tag" in doc.tags
        assert "# this" not in doc.tags  # 代码块内注释

    def test_tag_not_in_url(self):
        """URL 中的 # 不应被识别"""
        parser = ObsidianParser()
        doc = parser.parse("链接 https://example.com#section 和 #realtag", "test.md")
        assert "#realtag" in doc.tags
        assert "#section" not in doc.tags

    def test_no_tags(self):
        parser = ObsidianParser()
        doc = parser.parse("普通文本没有标签", "test.md")
        assert doc.tags == []

    def test_tags_dedup(self):
        parser = ObsidianParser()
        doc = parser.parse("#tag #tag", "test.md")
        assert doc.tags == ["#tag"]


class TestCallouts:
    """> [!type] callout 解析"""

    def test_note_callout(self):
        parser = ObsidianParser()
        doc = parser.parse("> [!note] 核心原则\n> 这是内容", "test.md")
        assert len(doc.callouts) == 1
        assert doc.callouts[0]["type"] == "note"
        assert "核心原则" in doc.callouts[0]["title"]
        assert "这是内容" in doc.callouts[0]["content"]

    def test_warning_callout(self):
        parser = ObsidianParser()
        doc = parser.parse("> [!warning] 注意\n> 危险操作", "test.md")
        assert doc.callouts[0]["type"] == "warning"

    def test_foldable_callout(self):
        """可折叠 callout [!note]+"""
        parser = ObsidianParser()
        doc = parser.parse("> [!note]+ 展开查看\n> 隐藏内容", "test.md")
        assert doc.callouts[0]["foldable"] is True

    def test_multiple_callouts(self):
        parser = ObsidianParser()
        content = """> [!note] 第一点
> 内容A

> [!warning] 第二点
> 内容B"""
        doc = parser.parse(content, "test.md")
        assert len(doc.callouts) == 2
        assert doc.callouts[0]["type"] == "note"
        assert doc.callouts[1]["type"] == "warning"

    def test_no_callout(self):
        parser = ObsidianParser()
        doc = parser.parse("普通引用 > 不是 callout", "test.md")
        assert doc.callouts == []


class TestEmbeds:
    """![[embed]] 解析"""

    def test_basic_embed(self):
        parser = ObsidianParser()
        doc = parser.parse("![[image.png]]", "test.md")
        assert len(doc.embeds) == 1
        assert doc.embeds[0]["target"] == "image.png"

    def test_embed_with_heading(self):
        parser = ObsidianParser()
        doc = parser.parse("![[Runtime框架#组件表]]", "test.md")
        emb = doc.embeds[0]
        assert emb["target"] == "Runtime框架"
        assert emb["heading"] == "组件表"

    def test_no_embed(self):
        parser = ObsidianParser()
        doc = parser.parse("普通文本", "test.md")
        assert doc.embeds == []


class TestFrontmatterParsing:
    """Frontmatter 解析（obsidian_parser 也可提取）"""

    def test_frontmatter_with_tags(self):
        content = """---
title: 测试文档
tags: [agent, architecture]
created: 2026-01-01
---
# 正文"""
        parser = ObsidianParser()
        doc = parser.parse(content, "test.md")
        assert doc.frontmatter is not None
        assert doc.frontmatter["title"] == "测试文档"
        assert "agent" in doc.frontmatter["tags"]

    def test_no_frontmatter(self):
        parser = ObsidianParser()
        doc = parser.parse("# 纯正文\n无 frontmatter", "test.md")
        assert doc.frontmatter is None


class TestRealWorldContent:
    """用 sample_vault 中的真实内容验证"""

    def test_agent_architecture(self, sample_vault):
        """agent-architecture.md 含多种 Obsidian 语法"""
        content = (sample_vault / "agent-architecture.md").read_text(encoding="utf-8")
        parser = ObsidianParser()
        doc = parser.parse(content, "agent-architecture.md")

        assert "Agent Runtime 组件表" in doc.wikilinks
        assert "Agent 落地12条" in doc.wikilinks
        assert "#agent/runtime" in doc.tags
        assert "#architecture" in doc.tags

    def test_rag_basics(self, sample_vault):
        """rag-basics.md 含 callout"""
        content = (sample_vault / "rag-basics.md").read_text(encoding="utf-8")
        parser = ObsidianParser()
        doc = parser.parse(content, "rag-basics.md")

        assert len(doc.callouts) >= 1
        assert doc.callouts[0]["type"] == "note"
        assert "#rag/basics" in doc.tags
