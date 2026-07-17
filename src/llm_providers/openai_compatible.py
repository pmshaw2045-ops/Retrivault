"""OpenAI 协议兼容 Provider

支持 DeepSeek / OpenAI / Ollama 等所有 OpenAI 兼容 API。
"""

from openai import OpenAI

from src.interfaces import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI 协议兼容 LLM Provider。

    支持：
      - DeepSeek: base_url="https://api.deepseek.com/v1"
      - OpenAI:   base_url="https://api.openai.com/v1"
      - Ollama:   base_url="http://localhost:11434/v1"
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def count_tokens(self, text: str) -> int:
        # 粗略估算：中文约 1.5 char/token, 英文约 4 char/token
        # DeepSeek/OpenAI 的 tokenizer 在此不做精确计算
        return max(1, len(text) // 2)
