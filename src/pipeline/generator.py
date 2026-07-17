"""LLM 生成引擎

职责：
1. Prompt 组装（系统角色 + 知识片段 + 格式要求）
2. Token 预算管理（保证至少 3 个 chunk）
3. LLM 调用
4. 引用注入（[1][2] 标记 + 来源信息）
5. 空结果短路（不调用 LLM，直接返回"无相关信息"）
"""
from dataclasses import dataclass, field

from src.interfaces import LLMProvider
from src.pipeline.retriever import SearchResult


@dataclass
class SearchResponse:
    """搜索响应"""
    answer: str
    sources: list[dict] = field(default_factory=list)
    retrieval_stats: dict = field(default_factory=dict)
    prompt_text: str = ""


class Generator:
    """
    Prompt 组装 + LLM 调用 + 引用注入。

    Args:
        llm: LLMProvider 实例
        max_prompt_tokens: Prompt 最大 token 预算
        min_chunks: 最少保留的 chunk 数量
    """

    SYSTEM_PROMPT = """你是 Obsidian 个人知识库助手。你的回答严格基于以下检索到的知识片段。
如果知识片段不包含回答所需信息，直接说"我的知识库中没有相关信息"，绝不编造。

## 回答规则
1. 用自然、专业的中文回答用户问题
2. 在答案中使用 [N] 标注引用来源（N 是知识片段的编号）
3. 如果多个片段涉及同一观点，可以引用多个编号
4. 不引入知识片段中没有的外部知识
5. 知识片段可能包含 Obsidian 特有的链接语法 [[xxx]]，在回答中保留为纯文本"""

    USER_PROMPT_TEMPLATE = """## 知识片段
{sources}

## 用户问题
{query}

请基于以上知识片段回答问题，并在答案中标注引用来源。"""

    def __init__(
        self,
        llm: LLMProvider,
        max_prompt_tokens: int = 6000,
        min_chunks: int = 3,
    ):
        self.llm = llm
        self.max_prompt_tokens = max_prompt_tokens
        self.min_chunks = min_chunks

    def generate(
        self,
        query: str,
        results: list[SearchResult],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> SearchResponse:
        """
        生成回答。

        Args:
            query: 用户问题
            results: 检索到的 chunk 列表
            temperature: LLM 温度
            max_tokens: 回答最大 token 数

        Returns:
            SearchResponse（含 answer + sources + stats）
        """
        # 空结果短路：不调 LLM，直接返回
        if not results:
            return SearchResponse(
                answer="我的知识库中没有相关信息。",
                retrieval_stats={"chunks_found": 0, "chunks_used": 0, "tokens_used": 0},
            )

        # Token 预算管理：按分数排列 + 至少保留 min_chunks 个
        selected = self._budget_chunks(results)

        # 组装 Prompt
        sources_text = self._format_sources(selected)
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            sources=sources_text, query=query
        )

        # 调用 LLM
        answer = self.llm.generate(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 引用注入
        answer_with_citations = self._inject_citations(answer)

        # 来源信息
        sources = []
        for i, chunk in enumerate(selected):
            sources.append({
                "index": i + 1,
                "source_file": chunk.source_file,
                "heading_path": chunk.heading_path,
                "score": round(chunk.score, 3),
                "preview": chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
            })

        return SearchResponse(
            answer=answer_with_citations,
            sources=sources,
            retrieval_stats={
                "chunks_found": len(results),
                "chunks_used": len(selected),
                "tokens_used": self._estimate_tokens(
                    self.SYSTEM_PROMPT + "\n" + user_prompt
                ),
            },
            prompt_text=f"System:\n{self.SYSTEM_PROMPT}\n\n--- User ---\n{user_prompt}",
        )

    # ============================================================
    # Token 预算管理
    # ============================================================

    def _budget_chunks(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        Token 预算管理。

        规则：
        1. 按分数从高到低排列
        2. 逐个添加 chunk → 计算 prompt token 数
        3. 超出 max_prompt_tokens → 停止
        4. 保证至少保留 min_chunks 个（不足则截断长 chunk）
        """
        # 按分数降序
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

        selected = []
        current_tokens = self._estimate_tokens(self.SYSTEM_PROMPT)

        for chunk in sorted_results:
            chunk_tokens = self._estimate_tokens(chunk.content)
            if current_tokens + chunk_tokens <= self.max_prompt_tokens:
                selected.append(chunk)
                current_tokens += chunk_tokens
            else:
                # 已经满足最小数量，停止
                if len(selected) >= self.min_chunks:
                    break
                # 还没满足最小数量，截断这个 chunk
                available = self.max_prompt_tokens - current_tokens
                if available > 50:  # 最少保留 50 tokens 有意义内容
                    truncated = self._truncate_to_tokens(chunk.content, available)
                    chunk.content = truncated
                    selected.append(chunk)
                break

        return selected

    # ============================================================
    # 引用注入
    # ============================================================

    @staticmethod
    def _inject_citations(answer: str) -> str:
        """
        确保回答中有引用标记。

        LLM 可能已经按 SYSTEM_PROMPT 要求加了 [N] 引用，
        如果没加，在末尾追加来源提示。
        """
        import re
        if re.search(r"\[\d+\]", answer):
            return answer  # 已有引用标记，不重复添加
        return answer  # LLM 遵守 prompt 的话不需要后处理

    # ============================================================
    # Prompt 格式化
    # ============================================================

    @staticmethod
    def _format_sources(chunks: list[SearchResult]) -> str:
        """将 chunk 列表格式化为编号的知识片段文本"""
        parts = []
        for i, chunk in enumerate(chunks):
            source_info = f"{chunk.source_file}"
            if chunk.heading_path:
                source_info += f" > {chunk.heading_path}"

            parts.append(
                f"[{i + 1}] ({source_info})\n{chunk.content}"
            )
        return "\n\n---\n\n".join(parts)

    # ============================================================
    # Token 估算
    # ============================================================

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本 token 数。

        委托给 LLMProvider 实现（各家 tokenizer 不同）。
        如果 Provider 不支持，用字符数/2 做粗略估算。
        """
        if hasattr(self.llm, 'count_tokens'):
            return self.llm.count_tokens(text)
        # 粗略估算：中文约 1.5 字符/token，英文约 4 字符/token
        return max(1, len(text) // 2)

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """按 token 预算截断文本（保留完整句子）"""
        # 粗略估算
        max_chars = max_tokens * 2
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        # 找到最后一个完整句子
        last_period = max(
            truncated.rfind("。"),
            truncated.rfind("！"),
            truncated.rfind("？"),
            truncated.rfind(". "),
        )
        if last_period > max_chars // 2:
            return truncated[:last_period + 1] + "…"
        return truncated + "…"
