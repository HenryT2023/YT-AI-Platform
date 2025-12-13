"""
文档向量化任务

将知识库文档转换为向量并存入 Qdrant

v3 改进：
- 支持 evidence/content 变更触发 upsert
- 支持多种 embedding 提供者（OpenAI/Baidu）
- 支持删除向量
- 集成 embedding_usage 审计
- Hash 去重 (dedup_hit)
- 限流重试 (rate_limited + backoff)
- embedding_dim 一致性校验
"""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from celery import shared_task
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, PointIdsList
import structlog
import httpx
import hashlib

from app.config import settings
from app.tasks.embedding_audit import (
    embed_with_audit,
    validate_qdrant_dimension,
    compute_content_hash,
    VECTOR_DIM,
)

logger = structlog.get_logger(__name__)


def get_embedding(text: str) -> Optional[List[float]]:
    """
    获取文本嵌入向量

    支持 OpenAI 和 Baidu embedding API
    """
    # 优先使用 OpenAI
    if settings.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=getattr(settings, 'OPENAI_API_BASE', None),
            )
            response = client.embeddings.create(
                model=getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-3-small'),
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("openai_embedding_error", error=str(e))

    # 回退：使用 Baidu embedding
    if settings.BAIDU_API_KEY and settings.BAIDU_SECRET_KEY:
        try:
            return _get_baidu_embedding(text)
        except Exception as e:
            logger.error("baidu_embedding_error", error=str(e))

    logger.warning("no_embedding_provider_available")
    return None


def _get_baidu_embedding(text: str) -> Optional[List[float]]:
    """使用 Baidu embedding API"""
    import requests

    # 获取 access_token
    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    token_resp = requests.post(token_url, params={
        "grant_type": "client_credentials",
        "client_id": settings.BAIDU_API_KEY,
        "client_secret": settings.BAIDU_SECRET_KEY,
    })
    if token_resp.status_code != 200:
        return None
    access_token = token_resp.json().get("access_token")

    # 调用 embedding API
    embed_url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/embeddings/embedding-v1?access_token={access_token}"
    embed_resp = requests.post(embed_url, json={"input": [text[:1000]]})
    if embed_resp.status_code == 200:
        data = embed_resp.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["embedding"]
    return None


def get_qdrant_client() -> QdrantClient:
    """获取 Qdrant 客户端"""
    return QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY,
    )


@shared_task(bind=True, max_retries=3)
def vectorize_document(
    self,
    document_id: str,
    title: str,
    content: str,
    domain: str,
    source: str = "",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """
    向量化单个文档

    Args:
        document_id: 文档 ID
        title: 文档标题
        content: 文档内容
        domain: 知识领域
        source: 来源
        chunk_size: 分块大小
        chunk_overlap: 分块重叠

    Returns:
        处理结果
    """
    logger.info("vectorize_document_start", document_id=document_id, title=title)

    try:
        # 1. 分块
        chunks = chunk_text(content, chunk_size, chunk_overlap)
        logger.info("document_chunked", document_id=document_id, chunk_count=len(chunks))

        # 2. 获取 Qdrant 客户端
        qdrant = get_qdrant_client()

        # 3. 确保 collection 存在
        ensure_collection(qdrant)

        # 4. 向量化并存储
        points = []
        for i, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            point_id = f"{document_id}_{i}"

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "document_id": document_id,
                        "title": title,
                        "content": chunk,
                        "domain": domain,
                        "source": source,
                        "chunk_index": i,
                    },
                )
            )

        # 5. 批量插入
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
        )

        logger.info(
            "vectorize_document_complete",
            document_id=document_id,
            points_count=len(points),
        )

        return {
            "status": "success",
            "document_id": document_id,
            "chunk_count": len(chunks),
            "points_count": len(points),
        }

    except Exception as e:
        logger.error("vectorize_document_error", document_id=document_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """将文本分块"""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]

        # 尝试在句子边界处分割
        if end < text_length:
            last_period = chunk.rfind("。")
            if last_period > chunk_size // 2:
                end = start + last_period + 1
                chunk = text[start:end]

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if c]


def ensure_collection(qdrant: QdrantClient) -> None:
    """确保 collection 存在并校验维度"""
    # 先校验维度一致性
    validate_qdrant_dimension(qdrant, settings.QDRANT_COLLECTION)
    
    collections = qdrant.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.QDRANT_COLLECTION not in collection_names:
        qdrant.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_DIM,  # 使用统一的向量维度
                distance=Distance.COSINE,
            ),
        )
        logger.info("collection_created", name=settings.QDRANT_COLLECTION, dim=VECTOR_DIM)


@shared_task
def batch_vectorize_documents(document_ids: List[str]) -> dict[str, Any]:
    """批量向量化文档"""
    results = []
    for doc_id in document_ids:
        # TODO: 从数据库获取文档内容
        # 这里需要实现从数据库读取文档的逻辑
        pass
    return {"status": "success", "processed": len(results)}


# ============================================================
# Evidence/Content 变更触发任务
# ============================================================

def _generate_point_id(evidence_id: str) -> str:
    """生成 Qdrant point ID（UUID 格式）"""
    hash_bytes = hashlib.md5(evidence_id.encode()).hexdigest()
    return f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}"


@shared_task(bind=True, max_retries=3)
def vectorize_evidence(
    self,
    evidence_id: str,
    tenant_id: str,
    site_id: str,
    source_type: str,
    source_ref: Optional[str],
    title: Optional[str],
    excerpt: str,
    confidence: float = 1.0,
    verified: bool = False,
    tags: Optional[List[str]] = None,
    domains: Optional[List[str]] = None,
    existing_hash: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    向量化单条证据

    当 evidence 创建或更新时触发
    
    v3: 集成 embedding_usage 审计和 hash 去重
    """
    log = logger.bind(evidence_id=evidence_id)
    log.info("vectorize_evidence_start")
    
    # 生成 job_id（如果未提供）
    if not job_id:
        job_id = str(uuid4())

    try:
        # 1. 构建待向量化文本
        text_parts = []
        if title:
            text_parts.append(title)
        text_parts.append(excerpt)
        text = "\n".join(text_parts)

        # 2. 获取向量（带审计和去重）
        embed_result = embed_with_audit(
            tenant_id=tenant_id,
            site_id=site_id,
            object_type="evidence",
            object_id=evidence_id,
            text=text,
            existing_hash=existing_hash,
            job_id=job_id,
        )
        
        # 去重命中，跳过
        if embed_result.status == "dedup_hit":
            log.info("vectorize_evidence_dedup_hit")
            return {
                "status": "dedup_hit",
                "evidence_id": evidence_id,
                "content_hash": embed_result.content_hash,
            }
        
        # 获取向量失败
        if not embed_result.embedding:
            log.warning("vectorize_evidence_no_embedding", status=embed_result.status)
            return {
                "status": "error",
                "error": embed_result.status,
                "error_type": embed_result.error_type,
            }

        # 3. 构建 point
        point_id = _generate_point_id(evidence_id)
        point = PointStruct(
            id=point_id,
            vector=embed_result.embedding,
            payload={
                "evidence_id": evidence_id,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "source_type": source_type,
                "source_ref": source_ref,
                "title": title,
                "excerpt": excerpt[:500],
                "confidence": confidence,
                "verified": verified,
                "tags": tags or [],
                "domains": domains or [],
                "content_hash": embed_result.content_hash,
            },
        )

        # 4. Upsert 到 Qdrant
        qdrant = get_qdrant_client()
        ensure_collection(qdrant)
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[point],
        )

        log.info(
            "vectorize_evidence_complete",
            point_id=point_id,
            latency_ms=embed_result.latency_ms,
        )
        return {
            "status": "success",
            "evidence_id": evidence_id,
            "point_id": point_id,
            "content_hash": embed_result.content_hash,
            "latency_ms": embed_result.latency_ms,
        }

    except Exception as e:
        log.error("vectorize_evidence_error", error=str(e))
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def delete_evidence_vector(
    self,
    evidence_id: str,
) -> Dict[str, Any]:
    """
    删除证据向量

    当 evidence 删除时触发
    """
    log = logger.bind(evidence_id=evidence_id)
    log.info("delete_evidence_vector_start")

    try:
        point_id = _generate_point_id(evidence_id)
        qdrant = get_qdrant_client()
        qdrant.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=PointIdsList(points=[point_id]),
        )

        log.info("delete_evidence_vector_complete", point_id=point_id)
        return {
            "status": "success",
            "evidence_id": evidence_id,
            "point_id": point_id,
        }

    except Exception as e:
        log.error("delete_evidence_vector_error", error=str(e))
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def vectorize_content(
    self,
    content_id: str,
    tenant_id: str,
    site_id: str,
    content_type: str,
    title: str,
    body: str,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    domains: Optional[List[str]] = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    向量化内容（分块）

    当 content 创建或更新时触发
    
    v3: 集成 embedding_usage 审计
    """
    log = logger.bind(content_id=content_id)
    log.info("vectorize_content_start")
    
    # 生成 job_id（如果未提供）
    if not job_id:
        job_id = str(uuid4())

    try:
        # 1. 分块
        text = f"{title}\n{summary or ''}\n{body}"
        chunks = chunk_text(text, chunk_size, chunk_overlap)
        log.info("content_chunked", chunk_count=len(chunks))

        # 2. 获取 Qdrant 客户端
        qdrant = get_qdrant_client()
        ensure_collection(qdrant)

        # 3. 向量化并存储（带审计）
        points = []
        success_count = 0
        dedup_count = 0
        failed_count = 0
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{content_id}_{i}"
            
            # 使用 embed_with_audit
            embed_result = embed_with_audit(
                tenant_id=tenant_id,
                site_id=site_id,
                object_type="content_chunk",
                object_id=chunk_id,
                text=chunk,
                job_id=job_id,
            )
            
            if embed_result.status == "dedup_hit":
                dedup_count += 1
                continue
            
            if not embed_result.embedding:
                failed_count += 1
                continue
            
            success_count += 1
            point_id = _generate_point_id(chunk_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embed_result.embedding,
                    payload={
                        "content_id": content_id,
                        "tenant_id": tenant_id,
                        "site_id": site_id,
                        "content_type": content_type,
                        "title": title,
                        "excerpt": chunk[:500],
                        "chunk_index": i,
                        "tags": tags or [],
                        "domains": domains or [],
                        "content_hash": embed_result.content_hash,
                    },
                )
            )

        # 4. 批量插入
        if points:
            qdrant.upsert(
                collection_name=settings.QDRANT_COLLECTION,
                points=points,
            )

        log.info(
            "vectorize_content_complete",
            points_count=len(points),
            success=success_count,
            dedup=dedup_count,
            failed=failed_count,
        )
        return {
            "status": "success",
            "content_id": content_id,
            "chunk_count": len(chunks),
            "points_count": len(points),
            "success_count": success_count,
            "dedup_count": dedup_count,
            "failed_count": failed_count,
        }

    except Exception as e:
        log.error("vectorize_content_error", error=str(e))
        raise self.retry(exc=e, countdown=60)


@shared_task
def sync_all_evidences(
    tenant_id: str,
    site_id: str,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    同步所有证据到 Qdrant

    用于初始化或重建索引
    """
    log = logger.bind(tenant_id=tenant_id, site_id=site_id)
    log.info("sync_all_evidences_start")

    # TODO: 从数据库分批读取 evidence 并调用 vectorize_evidence
    # 这里需要数据库连接，暂时返回占位结果
    return {
        "status": "pending",
        "message": "需要实现数据库连接",
    }
