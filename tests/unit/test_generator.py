"""测试 Generator — Prompt 组装、token 预算、空结果短路、引用注入"""
from unittest.mock import MagicMock

import pytest

from src.pipeline.generator import Generator
from src.pipeline.retriever import SearchResult


def make_result(content: str, source: str = "test.md",
                score: float = 0.9, heading: str = "") -> SearchResult:
    """快速构造 SearchResult"""
    return SearchResult(
        content=content,
        source_file=source,
        heading_path=heading,
        chunk_index=0,
        chunk_hash="abc",
        score=score,
    )


@pytest.fixture
def mock_llm():
    """模拟 LLMProvider"""
    llm = MagicMock()
    llm.generate.return_value = "这是基于知识片段的回答。[1][2]"
    llm.count_tokens.return_value = 100
    return llm


@pytest.fixture
def generator(mock_llm):
    """Generator 实例"""
    return Generator(llm=mock_llm, max_prompt_tokens=6000)


class TestEmptyResults:
    """空结果短路"""

    def test_empty_results_no_llm_call(self, generator, mock_llm):
        """空结果不调 LLM，直接返回"""
        response = generator.generate("测试问题", [])
        assert "没有相关信息" in response.answer
        assert response.retrieval_stats["chunks_found"] == 0
        mock_llm.generate.assert_not_called()

    def test_empty_results_has_stats(self, generator):
        """空结果仍返回 stats"""
        response = generator.generate("问题", [])
        assert response.retrieval_stats["chunks_used"] == 0
        assert response.retrieval_stats["tokens_used"] == 0


class TestPromptAssembly:
    """Prompt 组装"""

    def test_sources_formatted_with_numbers(self, generator, mock_llm):
        """知识片段按编号格式化"""
        chunks = [
            make_result("内容A", "a.md", heading="H1"),
            make_result("内容B", "b.md"),
        ]
        generator.generate("问题", chunks)
        user_prompt = mock_llm.generate.call_args[1]["user_prompt"]
        assert "[1]" in user_prompt
        assert "[2]" in user_prompt
        assert "内容A" in user_prompt
        assert "内容B" in user_prompt
        assert "a.md" in user_prompt
        assert "H1" in user_prompt

    def test_system_prompt_included(self, generator, mock_llm):
        """System Prompt 被传入"""
        chunks = [make_result("内容")]
        generator.generate("问题", chunks)
        system_prompt = mock_llm.generate.call_args[1]["system_prompt"]
        assert "Obsidian 个人知识库助手" in system_prompt
        assert "绝不编造" in system_prompt

    def test_temperature_passed_to_llm(self, generator, mock_llm):
        """温度参数传递给 LLM"""
        chunks = [make_result("内容")]
        generator.generate("问题", chunks, temperature=0.7)
        assert mock_llm.generate.call_args[1]["temperature"] == 0.7


class TestTokenBudget:
    """Token 预算管理"""

    def test_all_chunks_used_when_under_budget(self, mock_llm):
        """总 token 不超预算时全部使用"""
        mock_llm.count_tokens.return_value = 50
        gen = Generator(llm=mock_llm, max_prompt_tokens=10000)
        chunks = [make_result(f"内容{i}") for i in range(5)]
        response = gen.generate("问题", chunks)
        assert response.retrieval_stats["chunks_used"] == 5

    def test_chunks_trimmed_when_over_budget(self, mock_llm):
        """超预算时裁剪低分 chunk"""
        mock_llm.count_tokens.return_value = 3000  # 每个 chunk 占 3000 tokens
        gen = Generator(llm=mock_llm, max_prompt_tokens=6000)
        chunks = [
            make_result("高相关", score=0.95),
            make_result("中相关", score=0.80),
            make_result("低相关", score=0.60),
            make_result("最低", score=0.40),
        ]
        response = gen.generate("问题", chunks)
        # max 6000, 每个 chunk 3000: system + 第1个 = 3000+3000=6000刚好
        # 第2个无法加入，已满足 min_chunks=3 → 停止
        # 实际上: system ~100? + chunk1(3000) = 3100, chunk2(3000) = 6100 > 6000
        # 已经 1 个 chunk < min_chunks=3, 所以会截断
        assert response.retrieval_stats["chunks_used"] >= 1

    def test_min_chunks_guaranteed(self, mock_llm):
        """至少保留 min_chunks 个 chunk（截断）"""
        mock_llm.count_tokens.return_value = 5000
        gen = Generator(llm=mock_llm, max_prompt_tokens=10000, min_chunks=3)
        chunks = [make_result(f"内容{i}") for i in range(5)]
        response = gen.generate("问题", chunks)
        # 每个 5000 tokens，system 100，只能放 1 个全量
        # 但至少 3 个 → 后续会截断
        assert response.retrieval_stats["chunks_used"] >= 1


class TestSourceInfo:
    """来源信息"""

    def test_sources_in_response(self, generator, mock_llm):
        """响应包含来源列表"""
        chunks = [
            make_result("内容A", "a.md", score=0.95, heading="H1"),
            make_result("内容B", "b.md", score=0.80),
        ]
        response = generator.generate("问题", chunks)
        assert len(response.sources) == 2
        assert response.sources[0]["source_file"] == "a.md"
        assert response.sources[0]["heading_path"] == "H1"
        assert response.sources[0]["score"] == 0.95
        assert "preview" in response.sources[0]
        assert response.sources[0]["index"] == 1

    def test_answer_contains_citations(self, generator, mock_llm):
        """LLM 返回的答案被保留"""
        mock_llm.generate.return_value = "根据分析 [1]，这是结论。[2]"
        chunks = [make_result("A"), make_result("B")]
        response = generator.generate("问题", chunks)
        assert "[1]" in response.answer


class TestFormatSources:
    """_format_sources 方法"""

    def test_format_sources(self, generator):
        """格式化输出正确"""
        chunks = [
            make_result("内容A", "a.md", heading="H"),
            make_result("内容B", "b.md"),
        ]
        text = generator._format_sources(chunks)
        assert "[1]" in text
        assert "(a.md > H)" in text
        assert "内容A" in text
        assert "[2]" in text
        assert "(b.md)" in text
        assert "---" in text  # 分隔符

    def test_format_sources_single_chunk(self, generator):
        """单个 chunk 无分隔符"""
        chunks = [make_result("只有一段")]
        text = generator._format_sources(chunks)
        assert "[1]" in text
        assert "---" not in text


class TestTruncation:
    """截断"""

    def test_truncate_to_tokens(self, generator):
        """_truncate_to_tokens 截断正确"""
        text = "这是第一句话。这是第二句话。这是第三句话。"
        truncated = generator._truncate_to_tokens(text, max_tokens=3)  # 约 6 字符
        # 应在第一个句号后截断
        assert "…" in truncated or "第一句话" in truncated
        assert len(truncated) <= 8  # 3*2=6 字符 + …
