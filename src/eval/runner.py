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
    recall: float
    precision: float
    ndcg: float
    top_k: int
    latency_ms: float
    chunks_found: int
    retrieved_docs: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """完整评测报告"""
    config_name: str
    total_queries: int
    top_k: int
    results: list[EvalResult]
    avg_hit_rate: float = 0.0
    avg_mrr: float = 0.0
    avg_recall: float = 0.0
    avg_precision: float = 0.0
    avg_ndcg: float = 0.0
    avg_latency_ms: float = 0.0


@dataclass
class EvalCompareReport:
    """多配置对比报告"""
    reports: list[EvalReport] = field(default_factory=list)


class EvalRunner:
    """评测编排器"""

    # 最近一次评测结果（进程级缓存）
    _last_report: EvalReport | None = None
    _prev_report: EvalReport | None = None
    _last_run_at: str | None = None
    _last_config: dict | None = None

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
            top_k=top_k,
            results=results,
            avg_hit_rate=sum(r.hit for r in results) / n if n else 0,
            avg_mrr=sum(r.mrr for r in results) / n if n else 0,
            avg_recall=sum(r.recall for r in results) / n if n else 0,
            avg_precision=sum(r.precision for r in results) / n if n else 0,
            avg_ndcg=sum(r.ndcg for r in results) / n if n else 0,
            avg_latency_ms=sum(r.latency_ms for r in results) / n if n else 0,
        )
        EvalRunner._save_last(report, config={"mode": mode, "top_k": top_k, "threshold": similarity_threshold})
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
                query=gq.query, hit=0, mrr=0, recall=0,
                precision=0, ndcg=0, top_k=kwargs.get("top_k", 5),
                latency_ms=0, chunks_found=0,
            )

        internal_k = kwargs.get("top_k", 5) * 2
        user_k = kwargs.get("top_k", 5)
        results = await self.comps.retriever.search_async(
            query_vector,
            query_text=gq.query,
            top_k=internal_k,
            similarity_threshold=kwargs.get("similarity_threshold", 0.0),
            mode=kwargs.get("mode", "vector"),
        )

        # 提取文档名
        retrieved_docs = [r.source_file.split("/")[-1] for r in results]

        latency = (time.time() - t0) * 1000

        return EvalResult(
            query=gq.query,
            hit=hit_rate(retrieved_docs, list(relevant_docs), k=user_k),
            mrr=mrr(retrieved_docs, list(relevant_docs), k=user_k),
            recall=recall_at_k(retrieved_docs, list(relevant_docs), k=user_k),
            precision=precision_at_k(retrieved_docs, list(relevant_docs), k=user_k),
            ndcg=ndcg_at_k(retrieved_docs, list(relevant_docs), k=user_k),
            top_k=user_k,
            latency_ms=latency,
            chunks_found=len(retrieved_docs),
            retrieved_docs=retrieved_docs,
        )

    # ── 最近一次评测结果缓存 ──

    @classmethod
    def _save_last(cls, report: EvalReport, config: dict | None = None) -> None:
        from datetime import datetime
        if cls._last_report is not None:
            cls._prev_report = cls._last_report
        cls._last_report = report
        cls._last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cls._last_config = config

    @classmethod
    def get_last(cls) -> dict | None:
        """返回上次评测摘要，无数据时返回 None"""
        if cls._last_report is None:
            return None
        r = cls._last_report
        prev = cls._prev_report

        def _delta(curr, attr):
            if prev is None:
                return None
            pv = getattr(prev, attr, 0)
            return round(curr - pv, 4)

        return {
            "run_at": cls._last_run_at,
            "config": cls._last_config,
            "total_queries": r.total_queries,
            "top_k": r.top_k,
            "metrics": {
                "hit_rate": round(r.avg_hit_rate, 4),
                "mrr": round(r.avg_mrr, 4),
                "precision": round(r.avg_precision, 4),
                "recall": round(r.avg_recall, 4),
                "ndcg": round(r.avg_ndcg, 4),
                "avg_latency_ms": round(r.avg_latency_ms, 1),
            },
            "deltas": {
                "hit_rate": _delta(r.avg_hit_rate, "avg_hit_rate"),
                "mrr": _delta(r.avg_mrr, "avg_mrr"),
                "precision": _delta(r.avg_precision, "avg_precision"),
                "recall": _delta(r.avg_recall, "avg_recall"),
                "ndcg": _delta(r.avg_ndcg, "avg_ndcg"),
            },
            "details": [
                {
                    "query": er.query,
                    "hit": er.hit,
                    "mrr": round(er.mrr, 4),
                    "recall": round(er.recall, 4),
                    "precision": round(er.precision, 4),
                    "ndcg": round(er.ndcg, 4),
                    "top_k": er.top_k,
                    "latency_ms": round(er.latency_ms, 1),
                    "retrieved": er.retrieved_docs[:er.top_k],
                }
                for er in r.results
            ],
        }
