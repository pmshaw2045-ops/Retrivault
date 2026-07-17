"""POST /api/eval — 评测端点"""
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_components
from src.eval import GoldenDataset
from src.eval.runner import EvalRunner

router = APIRouter()


@router.get("/eval/last")
async def get_last_eval():
    """返回最近一次评测结果"""
    last = EvalRunner.get_last()
    if last is None:
        return {"has_data": False, "run_at": None, "metrics": None, "details": []}
    return {"has_data": True, **last}


class EvalRequest(BaseModel):
    mode: str = Field(default="vector", pattern="^(vector|hybrid)$")
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    golden_path: str = Field(default="tests/fixtures/golden_dataset.yaml")
    config_name: str = Field(default="")


@router.post("/eval")
async def run_eval(req: EvalRequest):
    """
    运行评测。

    从 golden_path 加载金标数据集，对每条 query 执行检索并计算指标。
    """
    comps = get_components()

    golden_file = Path(req.golden_path)
    if not golden_file.exists():
        raise HTTPException(status_code=404, detail=f"金标数据集不存在: {req.golden_path}")

    try:
        dataset = GoldenDataset.from_yaml(golden_file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"金标数据集格式错误: {e}") from e

    try:
        runner = EvalRunner(comps, dataset)
        report = await runner.run(
            mode=req.mode,
            top_k=req.top_k,
            similarity_threshold=req.similarity_threshold,
            config_name=req.config_name,
        )
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="评测执行失败") from None

    return {
        "config": report.config_name,
        "total_queries": report.total_queries,
        "metrics": {
            "hit_rate": round(report.avg_hit_rate, 4),
            "mrr": round(report.avg_mrr, 4),
            "recall@5": round(report.avg_recall, 4),
            "precision@5": round(report.avg_precision, 4),
            "ndcg@5": round(report.avg_ndcg, 4),
            "avg_latency_ms": round(report.avg_latency_ms, 1),
        },
        "details": [
            {
                "query": r.query,
                "hit": r.hit,
                "mrr": round(r.mrr, 4),
                "recall@5": round(r.recall, 4),
                "precision@5": round(r.precision, 4),
                "ndcg@5": round(r.ndcg, 4),
                "latency_ms": round(r.latency_ms, 1),
                "retrieved": r.retrieved_docs[:5],
            }
            for r in report.results
        ],
    }


class CompareRequest(BaseModel):
    configs: list[dict] = Field(default_factory=list, min_length=1, max_length=4)
    golden_path: str = Field(default="tests/fixtures/golden_dataset.yaml")


@router.post("/eval/compare")
async def compare_eval(req: CompareRequest):
    """多配置对比评测"""
    golden_file = Path(req.golden_path)
    if not golden_file.exists():
        raise HTTPException(status_code=404, detail=f"金标数据集不存在: {req.golden_path}")

    dataset = GoldenDataset.from_yaml(golden_file)
    runner = EvalRunner(get_components(), dataset)

    compare = await runner.compare(req.configs)

    return {
        "comparisons": [
            {
                "config": r.config_name,
                "metrics": {
                    "hit_rate": round(r.avg_hit_rate, 4),
                    "mrr": round(r.avg_mrr, 4),
                    "recall@5": round(r.avg_recall, 4),
                    "precision@5": round(r.avg_precision, 4),
                    "ndcg@5": round(r.avg_ndcg, 4),
                    "avg_latency_ms": round(r.avg_latency_ms, 1),
                },
            }
            for r in compare.reports
        ]
    }
