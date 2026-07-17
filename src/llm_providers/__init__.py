"""LLM Provider 注册工厂"""
from src.interfaces import LLMProvider

_llm_providers: dict[str, type[LLMProvider]] = {}

def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _llm_providers[name] = cls

def get_provider(name: str) -> type[LLMProvider]:
    if name not in _llm_providers:
        raise ValueError(f"Unknown LLM provider: {name}")
    return _llm_providers[name]
