"""POST /api/index + GET /api/index/progress"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src.api.dependencies import get_components
from src.api.models import IndexProgress, IndexRequest

logger = logging.getLogger(__name__)
router = APIRouter()

_index_progress = IndexProgress(status="idle", doc_count=0, chunk_count=0)
_last_decision: str = ""  # 缓存 status 决策，避免重复计算


def get_cached_decision() -> str:
    """获取缓存的索引决策（避免每次 poll 重新 hash）"""
    global _last_decision
    return _last_decision


def set_cached_decision(decision: str):
    global _last_decision
    _last_decision = decision


@router.post("/index")
async def trigger_index(req: IndexRequest):
    """触发索引。action=full 强制全量重建。"""
    comps = get_components()

    if not comps.vault_path:
        raise HTTPException(status_code=400, detail="未配置 vault 路径")

    global _index_progress
    _index_progress.status = "indexing"

    def _run():
        global _index_progress
        try:
            def progress_cb(phase, current, total):
                _index_progress.phase = phase
                _index_progress.current = current
                _index_progress.total = total

            # 尊重 action 参数：full → 先清空再全量，否则让 indexer 自动决策
            if req.action == "full":
                comps.vector_store.clear()
                comps.index_manager.reset_all(comps.vault_path)

            result = comps.indexer.run(comps.vault_path, progress_callback=progress_cb)
            _index_progress.status = "ready"
            _index_progress.doc_count = result.get("doc_count", 0)
            _index_progress.chunk_count = result.get("chunk_count", 0)
            set_cached_decision("ready")
        except Exception:
            _index_progress.status = "error"
            logger.exception("Indexing failed")

    asyncio.create_task(asyncio.to_thread(_run))
    return {"status": "started"}


@router.get("/index/progress", response_model=IndexProgress)
async def index_progress():
    return _index_progress
