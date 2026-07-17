"""向量存储 Provider 注册工厂"""

from src.interfaces import VectorStore

# Provider 注册表
_vector_stores: dict[str, type[VectorStore]] = {}


def register_provider(name: str, cls: type[VectorStore]) -> None:
    """注册向量存储 Provider"""
    _vector_stores[name] = cls


def get_provider(name: str) -> type[VectorStore]:
    """获取向量存储 Provider 类"""
    if name not in _vector_stores:
        raise ValueError(
            f"Unknown vector store provider: {name}. Available: {list(_vector_stores.keys())}"
        )
    return _vector_stores[name]


# Step 3 实现 LanceVectorStore 后注册：
# from src.vector_stores.lance_store import LanceVectorStore
# register_provider("lance", LanceVectorStore)
