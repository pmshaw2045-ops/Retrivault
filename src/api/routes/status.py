"""GET /api/status — 索引状态 + 文档统计"""
from fastapi import APIRouter

from src.api.dependencies import get_components
from src.api.models import StatusResponse
from src.pipeline.index_manager import IndexDecision

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def status():
    """获取索引状态 + 文档统计"""
    comps = get_components()

    if not comps.vault_path:
        return StatusResponse(
            state="needs_config",
            doc_count=0,
            chunk_count=0,
            vault_path="未配置",
        )

    decision = comps.index_manager.on_startup(comps.vault_path)

    if decision == IndexDecision.FIRST_INDEX:
        state = "needs_index"
    elif decision == IndexDecision.RESUME:
        state = "indexing"
    elif decision == IndexDecision.INCREMENTAL:
        state = "ready"
        changed = comps.index_manager.detect_changes(comps.vault_path)
        idx_state = comps.index_manager.get_state(comps.vault_path)
        return StatusResponse(
            state=state,
            doc_count=idx_state.doc_count if idx_state else 0,
            chunk_count=idx_state.chunk_count if idx_state else 0,
            vault_path=comps.vault_path,
            pending_changes=True,
            changed_files=changed,
        )
    elif decision == IndexDecision.REINDEX:
        state = "needs_index"
    else:
        state = "ready"

    idx_state = comps.index_manager.get_state(comps.vault_path)

    return StatusResponse(
        state=state,
        doc_count=idx_state.doc_count if idx_state else 0,
        chunk_count=idx_state.chunk_count if idx_state else 0,
        vault_path=comps.vault_path,
    )
