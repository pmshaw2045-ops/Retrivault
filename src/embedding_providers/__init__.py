"""Embedding Provider 注册工厂"""

from src.interfaces import EmbeddingProvider

_embedding_providers: dict[str, type[EmbeddingProvider]] = {}


def register_provider(name: str, cls: type[EmbeddingProvider]) -> None:
    _embedding_providers[name] = cls


def get_provider(name: str) -> type[EmbeddingProvider]:
    if name not in _embedding_providers:
        raise ValueError(f"Unknown embedding provider: {name}")
    return _embedding_providers[name]
