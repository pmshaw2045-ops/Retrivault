"""SSE 流式搜索端点 — 逐步推送 pipeline 进度与完整详情

每个步骤作为 Server-Sent Event 推送，前端 EventSource 实时消费。
事件类型：rewrite / embed / retrieve / rerank / generate / result / error
"""

import json
import logging
import os
import time

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_components
from src.pipeline.query_rewriter import QueryRewriter

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_rewriter(config) -> QueryRewriter:
    api_key = os.getenv("LLM_API_KEY", "") or os.getenv("EMBEDDING_API_KEY", "")
    return QueryRewriter(
        api_key=api_key,
        base_url=config.rewrite.base_url or "https://api.deepseek.com/v1",
        model=config.rewrite.model or "deepseek-v4-flash",
    )


def _should_rewrite(query: str) -> bool:
    """判断查询是否需要 LLM 改写

    不需要改写的场景：
    - 短查询（<=3 个字）→ 没必要
    - 纯关键词（无口语化词、无疑问词）→ 已是检索友好格式
    需要改写的场景：
    - 含口语化词（帮我、请问、有没有、怎么、如何…）
    - 含疑问句结构（是什么、怎么办、有什么区别…）
    - 完整自然语句（含主谓结构，长度 > 15 字）
    """
    q = query.strip()
    if len(q) <= 3:
        return False

    # 口语化触发词 — 命中任意一个就改写
    conversational = {
        "帮我",
        "请问",
        "有没有",
        "怎么",
        "如何",
        "什么",
        "哪个",
        "哪些",
        "为什么",
        "给",
        "一下",
        "能不能",
        "是不是",
        "可否",
    }
    for w in conversational:
        if w in q:
            return True

    # 长自然语句（>15字不含口语词也改写，大概率是自然语言而非关键词）
    if len(q) > 15:
        return True

    return False


async def _search_events(
    q: str,
    top_k: int,
    mode: str,
    threshold: float,
    temp: float,
    rerank: bool = True,
    rewrite: bool = True,
):
    """生成搜索 pipeline 事件序列，每步携带完整详情"""
    comps = get_components()
    t0 = time.time()

    # ── Step 1: Rewrite ──
    search_query = q
    rw_data = {
        "input": q,
        "output": q,
        "rewrites": [],
        "skipped": True,
        "duration_ms": 0,
        "model": "",
        "system_prompt": "",
        "user_prompt": "",
    }
    t1 = time.time()
    if rewrite and _should_rewrite(q):
        yield _sse("rewrite", {"status": "running", "input": q})
        try:
            rewriter = _get_rewriter(comps.config)
            result = rewriter.rewrite(q)
            expanded = result.get("expanded", q)
            rewrites = result.get("rewrites", [])
            if expanded and expanded != q:
                search_query = expanded
                rw_data = {
                    "input": q,
                    "output": search_query,
                    "rewrites": rewrites,
                    "skipped": False,
                    "model": result.get("model", ""),
                    "system_prompt": result.get("system_prompt", ""),
                    "user_prompt": result.get("user_prompt", q),
                    "duration_ms": (time.time() - t1) * 1000,
                }
        except Exception:
            pass
        yield _sse("rewrite", {"status": "done", **rw_data})
    else:
        yield _sse(
            "rewrite",
            {"status": "skipped", "reason": "rewrite disabled" if not rewrite else "keyword query"},
        )

    # ── Step 2: Embed ──
    yield _sse("embed", {"status": "running", "query": search_query})
    t2 = time.time()
    try:
        query_vector = comps.embedder.embed_query(search_query)
        yield _sse(
            "embed",
            {
                "status": "done",
                "dims": len(query_vector),
                "model": comps.embedder.model_name,
                "query": search_query,
                "duration_ms": (time.time() - t2) * 1000,
            },
        )
    except Exception as e:
        yield _sse("embed", {"status": "error", "error": str(e)})
        yield _sse("error", {"message": f"Embedding failed: {e}"})
        return

    # ── Step 3: Retrieve ──
    yield _sse(
        "retrieve", {"status": "running", "mode": mode, "top_k": top_k, "threshold": threshold}
    )
    t3 = time.time()
    results = await comps.retriever.search_async(
        query_vector,
        query_text=q,
        top_k=top_k,
        similarity_threshold=threshold,
        tag_filter=None,
        mode=mode,
    )
    ret_details = [
        {
            "source_file": r.source_file,
            "heading_path": r.heading_path,
            "score": round(r.score, 3),
            "preview": r.content[:160].replace("\n", " "),
            "char_count": r.char_count,
        }
        for r in results
    ]
    yield _sse(
        "retrieve",
        {
            "status": "done",
            "chunks_found": len(results),
            "results": ret_details,
            "mode": mode,
            "top_k": top_k,
            "threshold": threshold,
            "duration_ms": (time.time() - t3) * 1000,
        },
    )

    if not results:
        yield _sse(
            "result",
            {
                "answer": "我的知识库中没有相关信息。",
                "sources": [],
                "stats": {"chunks_found": 0},
                "total_ms": (time.time() - t0) * 1000,
            },
        )
        return

    # ── Step 4: Rerank ──
    t4 = time.time()
    reranked = False
    if comps.reranker and rerank:
        yield _sse("rerank", {"status": "running", "model": comps.config.rerank.model})
        before_rerank = [(r.source_file.split("/")[-1], round(r.score, 3)) for r in results]
        try:
            docs = [r.content for r in results]
            reranked_data = comps.reranker.rerank(search_query, docs, top_n=len(docs))
            # ★ 保存原始检索分（reranker 的 relevance_score 对用户不友好）
            original_scores = {i: r.score for i, r in enumerate(results)}
            reordered = [results[item["index"]] for item in reranked_data]
            # 只保留检索分用于展示，reranker 仅用于排序
            for i, item in enumerate(reranked_data):
                orig_idx = item["index"]
                reordered[i].score = original_scores.get(orig_idx, reordered[i].score)
            results = reordered
            reranked = True
        except Exception:
            pass
        after_rerank = [(r.source_file.split("/")[-1], round(r.score, 3)) for r in results]
        yield _sse(
            "rerank",
            {
                "status": "done",
                "applied": reranked,
                "model": comps.config.rerank.model,
                "before": before_rerank,
                "after": after_rerank,
                "duration_ms": (time.time() - t4) * 1000,
            },
        )
    else:
        yield _sse("rerank", {"status": "skipped", "applied": False, "reason": "rerank disabled"})

    # ── Step 5: Generate ──
    model_name = comps.config.llm.model
    yield _sse("generate", {"status": "running", "model": model_name, "temperature": temp})
    t5 = time.time()
    if comps.generator:
        try:
            resp = comps.generator.generate(
                query=q,
                results=results,
                temperature=temp,
            )
            sources = [
                {
                    "index": i + 1,
                    "source_file": s["source_file"],
                    "heading_path": s["heading_path"],
                    "score": s["score"],
                    "preview": s["preview"],
                }
                for i, s in enumerate(resp.sources)
            ]
            # 提取 system_prompt 和 user_prompt（从 prompt_text 拆分）
            prompt_text = resp.prompt_text or ""
            system_prompt = ""
            user_prompt = ""
            if prompt_text:
                parts = prompt_text.split("--- User ---\n", 1)
                if len(parts) == 2:
                    system_prompt = parts[0].replace("System:\n", "").strip()
                    user_prompt = parts[1].strip()
                else:
                    system_prompt = prompt_text

            yield _sse(
                "generate",
                {
                    "status": "done",
                    "model": model_name,
                    "temperature": temp,
                    "tokens_used": resp.retrieval_stats.get("tokens_used", 0),
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "duration_ms": (time.time() - t5) * 1000,
                },
            )
            yield _sse(
                "result",
                {
                    "answer": resp.answer,
                    "sources": sources,
                    "stats": resp.retrieval_stats,
                    "total_ms": (time.time() - t0) * 1000,
                },
            )
            return
        except Exception:
            yield _sse(
                "generate",
                {"status": "error", "error": "LLM generation failed", "model": model_name},
            )

    # No LLM — retrieval only
    yield _sse("generate", {"status": "skipped", "reason": "LLM unavailable", "model": ""})
    sources = [
        {
            "index": i + 1,
            "source_file": r.source_file,
            "heading_path": r.heading_path,
            "score": round(r.score, 3),
            "preview": r.content[:200],
        }
        for i, r in enumerate(results)
    ]
    yield _sse(
        "result",
        {
            "answer": "（LLM 未配置）\n\n"
            + "\n---\n".join(f"[{i+1}] {s['preview']}" for i, s in enumerate(sources)),
            "sources": sources,
            "stats": {"chunks_found": len(results)},
            "total_ms": (time.time() - t0) * 1000,
        },
    )


@router.get("/search/stream")
async def search_stream(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
    mode: str = Query("vector", pattern="^(vector|hybrid)$"),
    threshold: float = Query(0.0, ge=0.0, le=1.0),
    temp: float = Query(0.3, ge=0.0, le=2.0),
    rerank: str = Query("true", pattern="^(true|false)$", description="关闭后跳过重排序"),
    rewrite: str = Query("true", pattern="^(true|false)$", description="关闭后跳过 Query 改写"),
):
    # bool 型 query param 必须用 str 手动转：FastAPI 的 bool("false") == True
    rerank_enabled = rerank == "true"
    rewrite_enabled = rewrite == "true"
    return StreamingResponse(
        _search_events(q, top_k, mode, threshold, temp, rerank_enabled, rewrite_enabled),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
