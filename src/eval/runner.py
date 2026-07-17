"""评测编排器

对金标数据集中的每个 query 执行检索，计算全部指标。
支持多配置对比（different modes, thresholds, etc.）。
"""
import time
from dataclasses import dataclass, field

from src.api.dependencies import AppComponents
from src.eval import GoldenDataset, GoldenQuery
from src.eval.metrics import (
    hit_rate,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


@dataclass
class EvalResult:
    """单条 query 的评测结果"""
    query: str
    hit: float
    mrr: float
    recall_5: float
    precision_5: float
    ndcg_5: float
    latency_ms: float
    chunks_found: int
    retrieved_docs: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """完整评测报告"""
    config_name: str
    total_queries: int
    results: list[EvalResult]
    avg_hit_rate: float = 0.0
    avg_mrr: float = 0.0
    avg_recall_5: float = 0.0
    avg_precision_5: float = 0.0
    avg_ndcg_5: float = 0.0
    avg_latency_ms: float = 0.0


@dataclass
class EvalCompareReport:
    """多配置对比报告"""
    reports: list[EvalReport] = field(default_factory=list)


class EvalRunner:
    """评测编排器"""

    # 最近一次评测结果（进程级缓存）
    _last_report: EvalReport | None = None
    _last_run_at: str | None = None

    def __init__(self, comps: AppComponents, dataset: GoldenDataset):
        self.comps = comps
        self.dataset = dataset

    async def run(self, mode: str = "vector", top_k: int = 5,
            similarity_threshold: float = 0.0,
            config_name: str = "") -> EvalReport:
        results: list[EvalResult] = []

        for gq in self.dataset.queries:
            er = await self._eval_one(gq, mode=mode, top_k=top_k,
                                      similarity_threshold=similarity_threshold)
            results.append(er)

        n = len(results)
        report = EvalReport(
            config_name=config_name or f"{mode}-k{top_k}-t{similarity_threshold}",
            total_queries=n,
            results=results,
            avg_hit_rate=sum(r.hit for r in results) / n if n else 0,
            avg_mrr=sum(r.mrr for r in results) / n if n else 0,
            avg_recall_5=sum(r.recall_5 for r in results) / n if n else 0,
            avg_precision_5=sum(r.precision_5 for r in results) / n if n else 0,
            avg_ndcg_5=sum(r.ndcg_5 for r in results) / n if n else 0,
            avg_latency_ms=sum(r.latency_ms for r in results) / n if n else 0,
        )
        EvalRunner._save_last(report)
        return report

    async def compare(self, configs: list[dict]) -> EvalCompareReport:
        """多配置对比评测"""
        reports = []
        for cfg in configs:
            report = await self.run(**cfg)
            reports.append(report)
        return EvalCompareReport(reports=reports)

    async def _eval_one(self, gq: GoldenQuery, **kwargs) -> EvalResult:
        """评测单条 query"""
        t0 = time.time()

        relevant_docs = set(gq.relevant_docs)

        try:
            query_vector = self.comps.embedder.embed_query(gq.query)
        except Exception:
            return EvalResult(
                query=gq.query, hit=0, mrr=0, recall_5=0,
                precision_5=0, ndcg_5=0, latency_ms=0, chunks_found=0,
            )

        top_k = kwargs.get("top_k", 5) * 2
        results = await self.comps.retriever.search_async(
            query_vector,
            query_text=gq.query,
            top_k=top_k,
            similarity_threshold=kwargs.get("similarity_threshold", 0.0),
            mode=kwargs.get("mode", "vector"),
        )

        # 提取文档名
        retrieved_docs = [r.source_file.split("/")[-1] for r in results]

        latency = (time.time() - t0) * 1000

        return EvalResult(
            query=gq.query,
            hit=hit_rate(retrieved_docs, list(relevant_docs)),
            mrr=mrr(retrieved_docs, list(relevant_docs)),
            recall_5=recall_at_k(retrieved_docs, list(relevant_docs), k=5),
            precision_5=precision_at_k(retrieved_docs, list(relevant_docs), k=5),
            ndcg_5=ndcg_at_k(retrieved_docs, list(relevant_docs), k=5),
            latency_ms=latency,
            chunks_found=len(retrieved_docs),
            retrieved_docs=retrieved_docs,
        )

    # ── 最近一次评测结果缓存 ──

    @classmethod
    def _save_last(cls, report: EvalReport) -> None:
        from datetime import datetime
        cls._last_report = report
        cls._last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def get_last(cls) -> dict | None:
        """返回上次评测摘要，无数据时返回 None"""
        if cls._last_report is None:
            return None
        r = cls._last_report
        return {
            "run_at": cls._last_run_at,
            "total_queries": r.total_queries,
            "metrics": {
                "hit_rate": round(r.avg_hit_rate, 4),
                "mrr": round(r.avg_mrr, 4),
                "recall@5": round(r.avg_recall_5, 4),
                "precision@5": round(r.avg_precision_5, 4),
                "ndcg@5": round(r.avg_ndcg_5, 4),
                "avg_latency_ms": round(r.avg_latency_ms, 1),
            },
            "details": [
                {
                    "query": er.query,
                    "hit": er.hit,
                    "mrr": round(er.mrr, 4),
                    "recall@5": round(er.recall_5, 4),
                    "latency_ms": round(er.latency_ms, 1),
                    "retrieved": er.retrieved_docs[:5],
                }
                for er in r.results
            ],
        }
