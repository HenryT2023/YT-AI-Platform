"""
语义检索 API

提供基于向量的语义检索接口
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from app.services.vector_store import VectorStore, get_vector_store, SearchResult
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    """检索请求"""
    query: str = Field(..., min_length=1, max_length=500, description="查询文本")
    collection: str = Field(default="knowledge", description="Collection 名称")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")
    score_threshold: float = Field(default=0.5, ge=0, le=1, description="分数阈值")
    filters: Optional[dict[str, Any]] = Field(default=None, description="过滤条件")


class SearchResultItem(BaseModel):
    """检索结果项"""
    id: str
    score: float
    content: str
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    """检索响应"""
    query: str
    collection: str
    results: list[SearchResultItem]
    total: int


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SearchRequest,
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    语义检索

    基于向量相似度检索相关内容
    """
    logger.info(
        "semantic_search_request",
        query_length=len(request.query),
        collection=request.collection,
        top_k=request.top_k,
    )

    results = await vector_store.search(
        collection_name=request.collection,
        query=request.query,
        top_k=request.top_k,
        filters=request.filters,
        score_threshold=request.score_threshold,
    )

    return SearchResponse(
        query=request.query,
        collection=request.collection,
        results=[
            SearchResultItem(
                id=r.id,
                score=r.score,
                content=r.content,
                metadata=r.metadata,
            )
            for r in results
        ],
        total=len(results),
    )


@router.get("/semantic", response_model=SearchResponse)
async def semantic_search_get(
    query: str = Query(..., min_length=1, max_length=500, description="查询文本"),
    collection: str = Query(default="knowledge", description="Collection 名称"),
    top_k: int = Query(default=5, ge=1, le=20, description="返回数量"),
    score_threshold: float = Query(default=0.5, ge=0, le=1, description="分数阈值"),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    语义检索 (GET)

    基于向量相似度检索相关内容
    """
    results = await vector_store.search(
        collection_name=collection,
        query=query,
        top_k=top_k,
        score_threshold=score_threshold,
    )

    return SearchResponse(
        query=query,
        collection=collection,
        results=[
            SearchResultItem(
                id=r.id,
                score=r.score,
                content=r.content,
                metadata=r.metadata,
            )
            for r in results
        ],
        total=len(results),
    )


@router.get("/collections")
async def list_collections(
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    列出所有 Collections
    """
    collections = ["knowledge", "npc_persona", "quest_content"]
    result = []

    for name in collections:
        info = await vector_store.get_collection_info(name)
        if info:
            result.append(info)

    return {"collections": result}


@router.get("/collections/{collection_name}")
async def get_collection_info(
    collection_name: str,
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    获取 Collection 信息
    """
    info = await vector_store.get_collection_info(collection_name)
    if not info:
        raise HTTPException(status_code=404, detail="Collection not found")
    return info


@router.get("/health")
async def vector_health(
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    向量服务健康检查
    """
    healthy = await vector_store.health_check()
    return {
        "status": "healthy" if healthy else "unhealthy",
        "service": "qdrant",
    }
