"""Query 改写器 — 生成 3 路改写 + 查询扩展

使用 DeepSeek Flash（或任意 OpenAI 兼容 API）生成 3 个不同表述的改写，
将原始查询与改写拼接为扩展查询，提升检索覆盖率和召回精度。

如果改写结果明显异常（不含原始 Query 关键词），自动回退到原始查询。
"""

import json
import logging
import re

from openai import OpenAI

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个搜索查询改写专家。你的任务是将用户的问题改写为更精准的搜索查询。

## 规则
1. 输出 JSON 数组，包含 3 个不同表述的改写
2. 保持语义一致，用不同措辞表达
3. 用更接近技术文档的措辞
4. **绝对保留专有名词原文**（如 Obsidian、LanceDB、DeepSeek）
5. 去掉口语化语气词（"帮我"、"请问"等）

## 示例
输入：BGE-M3和text-embedding对比
输出：["BGE-M3 vs text-embedding 对比", "BGE-M3和OpenAI Embedding模型比较", "BGE-M3 text-embedding 对比 评测"]

只输出 JSON 数组，不要其他文字。"""


class QueryRewriter:
    """查询改写器：输入用户问题 → 输出 3 个改写 + 扩展查询"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-v4-flash",
    ):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def rewrite(self, query: str) -> dict:
        """返回 {rewrites: [3个改写], expanded: 扩展查询, model: str, system_prompt: str}"""
        result = {
            "rewrites": [],
            "expanded": query,
            "model": self.model,
            "system_prompt": REWRITE_SYSTEM_PROMPT,
            "user_prompt": query,
        }

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content or ""
            rewrites = self._parse_rewrites(raw)

            if rewrites and len(rewrites) >= 1:
                # 验证改写结果：至少保留原始 Query 中的关键词
                valid = self._validate_rewrites(query, rewrites)
                if valid:
                    result["rewrites"] = rewrites[:3]
                    # 扩展查询 = 原始 + 前 2 个改写（避免太长稀释语义）
                    expanded_parts = [query]
                    for r in rewrites[:2]:
                        if r.lower() != query.lower():
                            expanded_parts.append(r)
                    result["expanded"] = " ".join(expanded_parts)
                else:
                    logger.warning(f"Rewrite output failed validation, falling back: {rewrites}")
            else:
                logger.warning(f"Rewrite returned empty result for: {query}")

        except Exception:
            logger.exception("Query rewrite failed")

        return result

    # ── 内部方法 ──

    @staticmethod
    def _parse_rewrites(raw: str) -> list[str]:
        """从 LLM 输出中解析 JSON 数组"""
        # 尝试直接解析 JSON
        raw = raw.strip()
        # 去掉可能的 ```json 围栏
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

        # 如果 JSON 解析失败，尝试按行提取
        lines = [
            line.strip().strip('"').strip("'")
            for line in raw.split("\n")
            if line.strip() and not line.strip().startswith("[") and not line.strip().endswith("]")
        ]
        # 去重
        seen = set()
        result = []
        for line in lines:
            line = line.strip('",').strip()
            if line and line not in seen:
                # 去掉行首的序号如 1. 2. 3.
                line = re.sub(r"^\d+\.\s*", "", line)
                seen.add(line)
                result.append(line)

        return result

    @staticmethod
    def _validate_rewrites(original: str, rewrites: list[str]) -> bool:
        """验证改写结果是否合理

        只检查英文专有名词/术语是否保留（中文词 LLM 可能灵活措辞，不强制匹配）。
        """
        if not rewrites:
            return False

        # 提取原始查询中的英文/数字词（专有名词、术语、缩写等）
        en_tokens = re.findall(r"[a-zA-Z0-9]{2,}", original)
        if not en_tokens:
            return True  # 没有专有名词，不做验证

        en_lower = [t.lower() for t in en_tokens]

        # 至少一半的改写保留原始专有名词（允许灵活措辞）
        passed = 0
        for rw in rewrites:
            rw_lower = rw.lower()
            if any(t in rw_lower for t in en_lower):
                passed += 1
        return passed >= max(1, len(rewrites) // 2)
