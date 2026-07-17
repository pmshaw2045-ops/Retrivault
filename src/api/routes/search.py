"""POST /api/search — 检索 + LLM 生成"""
import logging
import os
import time

from fastapi import APIRouter, HTTPException

from src.api.dependencies import get_components
from src.api.models import SearchRequest, SearchResponse, SourceInfo
from src.pipeline.query_rewriter import QueryRewriter

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_rewriter(config) -> QueryRewriter:
    api_key = os.getenv("LLM_API_KEY", "") or os.getenv("EMBEDDING_API_KEY", "")
    return QueryRewriter(
        api_key=api_key,
        base_url=config.rewrite.base_url or "https://api.deepseek.com/v1",
        model=config.rewrite.model or "deepseek-v4-flash",
    )


def _trace(step: str, **kwargs) -> dict:
    return {"step": step, **kwargs}


def _should_rewrite(query: str) -> bool:
    """判断查询是否需要 LLM 改写"""
    q = query.strip()
    if len(q) <= 3:
        return False
    conversational = {"帮我", "请问", "有没有", "怎么", "如何",
                      "什么", "哪个", "哪些", "为什么", "给", "一下",
                      "能不能", "是不是", "可否"}
    if any(w in q for w in conversational):
        return True
    if len(q) > 15:
        return True
    return False


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    comps = get_components()
    traces: list[dict] = []
    t0 = time.time()

    # 0. Query 改写（3 路改写 + 查询扩展）
    search_query = req.query
    t_qr = time.time()
    if comps.config.rewrite.enabled and _should_rewrite(req.query):
        try:
            rw = _get_rewriter(comps.config).rewrite(req.query)
            expanded = rw.get("expanded", req.query)
            if expanded and expanded != req.query:
                search_query = expanded
            rw["duration_ms"] = (time.time() - t_qr) * 1000
        except Exception:
            rw = {"rewrites": [], "expanded": req.query, "model": "",
                  "system_prompt": "", "user_prompt": ""}
            pass
    else:
        rw = {"rewrites": [], "expanded": req.query, "model": "",
              "system_prompt": "", "user_prompt": ""}
    traces.append(_trace("rewrite", input=req.query, output=search_query,
                         rewrites=rw.get("rewrites", []),
                         duration_ms=(time.time() - t_qr) * 1000,
                         skipped=search_query == req.query,
                         model=rw.get("model", ""),
                         system_prompt=rw.get("system_prompt", ""),
                         user_prompt=rw.get("user_prompt", "")))

    # 1. Embedding
    t_emb = time.time()
    try:
        query_vector = comps.embedder.embed_query(search_query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}") from e
    traces.append(_trace("embed", dims=len(query_vector),
                         duration_ms=(time.time() - t_emb) * 1000))

    # 2. 检索
    t_ret = time.time()
    results = await comps.retriever.search_async(
        query_vector, query_text=req.query,
        top_k=req.top_k, similarity_threshold=req.similarity_threshold,
        tag_filter=req.tag_filter, mode=req.mode,
    )
    # 细粒度：记录每个 chunk 的内容片段和分数
    ret_details = [{"preview": r.content[:80].replace("\n", " "),
                    "score": round(r.score, 3)}
                   for r in results]
    traces.append(_trace("retrieve", mode=req.mode,
                         chunks_found=len(results),
                         duration_ms=(time.time() - t_ret) * 1000,
                         results=ret_details))

    if not results:
        traces.append(_trace("total", duration_ms=(time.time() - t0) * 1000))
        return SearchResponse(
            answer="我的知识库中没有相关信息。", sources=[],
            retrieval_stats={"chunks_found": 0, "chunks_used": 0, "tokens_used": 0},
            trace=traces,
        )

    # 2.5 Rerank
    t_rr = time.time()
    reranked = False
    reranked_data = None
    before_rerank = [(r.source_file.split("/")[-1], round(r.score, 3)) for r in results]
    if comps.reranker:
        try:
            docs = [r.content for r in results]
            reranked_data = comps.reranker.rerank(search_query, docs, top_n=len(docs))
            if reranked_data:
                # ★ 保存原始检索分（reranker 的 relevance_score 对用户不友好）
                original_scores = {i: r.score for i, r in enumerate(results)}
                reordered = [results[item["index"]] for item in reranked_data]
                for i, item in enumerate(reranked_data):
                    orig_idx = item["index"]
                    reordered[i].score = original_scores.get(orig_idx, reordered[i].score)
                results = reordered
                reranked = True
        except Exception:
            pass
    after_rerank = [(r.source_file.split("/")[-1], round(r.score, 3)) for r in results]
    # 记录 rerank 输入（每条文档的前100字符片段）
    if reranked_data:
        rerank_inputs = [r.content[:100].replace("\n", " ") for r in
                         [results[item["index"]] for item in reranked_data]]
    else:
        rerank_inputs = [r.content[:100].replace("\n", " ") for r in results]
    traces.append(_trace("rerank", applied=reranked,
                         duration_ms=(time.time() - t_rr) * 1000,
                         model=comps.config.rerank.model,
                         query=search_query,
                         input_count=len(rerank_inputs),
                         input_docs=rerank_inputs[:5],
                         before=before_rerank, after=after_rerank))

    # 3. LLM 生成
    t_llm = time.time()
    if comps.generator:
        try:
            resp = comps.generator.generate(
                query=req.query, results=results, temperature=req.temperature,
            )
            traces.append(_trace("generate",
                                 model=comps.config.llm.model,
                                 tokens_used=resp.retrieval_stats.get("tokens_used", 0),
                                 system_prompt=resp.prompt_text[:500] if hasattr(resp, 'prompt_text') else "",
                                 user_prompt_chunks=f"{len(results)} chunks → {len(list(resp.sources))} used",
                                 duration_ms=(time.time() - t_llm) * 1000))
            traces.append(_trace("total", duration_ms=(time.time() - t0) * 1000))
            return SearchResponse(
                answer=resp.answer,
                sources=[SourceInfo(**s) for s in resp.sources],
                retrieval_stats=resp.retrieval_stats,
                trace=traces,
            )
        except Exception:
            logger.exception("LLM generation failed")

    traces.append(_trace("generate", skipped=True, reason="LLM unavailable"))
    traces.append(_trace("total", duration_ms=(time.time() - t0) * 1000))
    return _build_retrieval_only_response(results, traces)


def _build_retrieval_only_response(results, traces=None):
    sources = []
    for i, r in enumerate(results):
        sources.append(SourceInfo(
            index=i + 1, source_file=r.source_file, heading_path=r.heading_path,
            score=round(r.score, 3), preview=r.content[:200],
        ))
    answer = "（LLM 未配置）\n\n" + "\n\n---\n\n".join(
        f"[{i+1}] {s.preview}" for i, s in enumerate(sources)
    )
    return SearchResponse(
        answer=answer, sources=sources,
        retrieval_stats={"chunks_found": len(results), "chunks_used": len(results)},
        trace=traces or [],
    )


def _needs_rewrite(query: str) -> bool:
    if len(query) < 8:
        return False
    fuzzy = {"怎么", "什么", "如何", "那个", "这个", "一下", "帮我", "给我", "有没有"}
    return any(w in query for w in fuzzy)


def _build_prompt_preview(query: str, results) -> str:
    """构建提交给 LLM 的 prompt 摘要"""
    chunks_summary = "\n".join(
        f"[{i+1}] {r.source_file.split('/')[-1]} ({r.char_count}字)"
        for i, r in enumerate(results)
    )
    return f"Query: {query}\nChunks ({len(results)}):\n{chunks_summary}"
