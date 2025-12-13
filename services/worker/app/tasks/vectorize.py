"""
文档向量化任务

将知识库文档转换为向量并存入 Qdrant
"""

from typing import Any, List
from uuid import UUID

from celery import shared_task
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


def get_embedding(text: str) -> List[float]:
    """获取文本嵌入向量"""
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


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
    """确保 collection 存在"""
    collections = qdrant.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.QDRANT_COLLECTION not in collection_names:
        qdrant.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=1536,  # text-embedding-3-small 维度
                distance=Distance.COSINE,
            ),
        )
        logger.info("collection_created", name=settings.QDRANT_COLLECTION)


@shared_task
def batch_vectorize_documents(document_ids: List[str]) -> dict[str, Any]:
    """批量向量化文档"""
    results = []
    for doc_id in document_ids:
        # TODO: 从数据库获取文档内容
        # 这里需要实现从数据库读取文档的逻辑
        pass
    return {"status": "success", "processed": len(results)}
