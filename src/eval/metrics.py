"""检索评测指标

Hit Rate@k, MRR, NDCG@k, Recall@k, Precision@k

所有指标基于文档级匹配（relevant_docs）。
如果金标数据集有 chunk 标注，可切换为 chunk 级匹配。
"""

import math


def hit_rate(retrieved_docs: list[str], relevant_docs: list[str], k: int | None = None) -> float:
    """是否至少命中一个相关文档（只看前 k 个结果）"""
    if not relevant_docs:
        return 0.0
    docs = retrieved_docs[:k] if k is not None else retrieved_docs
    return 1.0 if any(d in relevant_docs for d in docs) else 0.0


def mrr(retrieved_docs: list[str], relevant_docs: list[str], k: int | None = None) -> float:
    """Mean Reciprocal Rank — 第一个相关文档的排名倒数（只看前 k 个结果）"""
    if not relevant_docs:
        return 0.0
    docs = retrieved_docs[:k] if k is not None else retrieved_docs
    for i, doc in enumerate(docs):
        if doc in relevant_docs:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int = 5) -> float:
    """Recall@k — 前 k 个结果中覆盖了多少相关文档（文件级去重）"""
    if not relevant_docs:
        return 0.0
    top_k = retrieved_docs[:k]
    # 同文件多 chunk 只算一次命中
    hits = len({d for d in top_k if d in relevant_docs})
    return hits / len(relevant_docs)


def precision_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int = 5) -> float:
    """Precision@k — 前 k 个结果中相关文档的比例（文件级去重）"""
    if not relevant_docs:
        return 0.0
    top_k = retrieved_docs[:k]
    hits = len({d for d in top_k if d in relevant_docs})
    return hits / k if k > 0 else 0.0


def ndcg_at_k(retrieved_docs: list[str], relevant_docs: list[str], k: int = 5) -> float:
    """NDCG@k — 归一化折损累积增益（文件级去重）"""
    if not relevant_docs:
        return 0.0

    top_k = retrieved_docs[:k]

    # DCG: 同文件多 chunk 只算第一次命中的位置
    dcg = 0.0
    seen = set()
    pos = 2  # log2(2) = 1
    for doc in top_k:
        if doc in relevant_docs and doc not in seen:
            dcg += 1.0 / math.log2(pos)
            seen.add(doc)
        pos += 1

    # IDCG: 理想排序（所有相关文档排在最前面）
    idcg = 0.0
    for i in range(min(len(relevant_docs), k)):
        idcg += 1.0 / math.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0
