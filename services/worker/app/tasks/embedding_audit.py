"""
Embedding 审计模块

统一封装 embedding 调用，实现：
- 审计记录写入 embedding_usage
- Hash 去重 (dedup_hit)
- 限流重试 (rate_limited + backoff)
- 成本估算
- embedding_dim 一致性校验
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = structlog.get_logger(__name__)

# ============================================================
# 配置
# ============================================================

VECTOR_DIM = 1024  # bge-large-zh / text-embedding-3-small

# Embedding 定价表 (USD per 1K tokens)
EMBEDDING_PRICING = {
    "openai": {"text-embedding-3-small": 0.00002, "text-embedding-3-large": 0.00013},
    "baidu": {"bge-large-zh": 0.0001, "embedding-v1": 0.0001},
    "dedup": {"hash_check": 0.0},
    "none": {"none": 0.0},
}

# 数据库连接
DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"


# ============================================================
# 数据类
# ============================================================

@dataclass
class EmbeddingResult:
    """Embedding 调用结果"""
    embedding: Optional[List[float]] = None
    provider: str = ""
    model: str = ""
    embedding_dim: int = 0
    input_chars: int = 0
    estimated_tokens: int = 0
    latency_ms: int = 0
    status: str = "failed"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    backoff_seconds: Optional[int] = None
    content_hash: Optional[str] = None


# ============================================================
# 辅助函数
# ============================================================

def estimate_tokens(text: str) -> int:
    """估算 token 数量（粗略：1.5 字符/token）"""
    return max(1, len(text) // 2)


def compute_content_hash(text: str) -> str:
    """计算内容 hash"""
    return hashlib.sha256(text.encode()).hexdigest()


def calculate_cost(provider: str, model: str, tokens: int) -> float:
    """计算成本估算 (USD)"""
    provider_prices = EMBEDDING_PRICING.get(provider, {})
    price_per_1k = provider_prices.get(model, 0.0001)
    return (tokens / 1000) * price_per_1k


def get_db_session():
    """获取数据库会话"""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()


# ============================================================
# Qdrant 维度校验
# ============================================================

_qdrant_dim_validated = False


def validate_qdrant_dimension(qdrant_client, collection_name: str) -> None:
    """
    校验 embedding_dim 与 Qdrant collection vector size 一致性
    
    不一致则 raise RuntimeError
    """
    global _qdrant_dim_validated
    if _qdrant_dim_validated:
        return
    
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name not in collection_names:
            # Collection 不存在，将在创建时使用正确维度
            _qdrant_dim_validated = True
            return
        
        # 获取 collection 配置
        collection_info = qdrant_client.get_collection(collection_name)
        qdrant_dim = collection_info.config.params.vectors.size
        
        if qdrant_dim != VECTOR_DIM:
            error_msg = f"embedding_dim mismatch: expected {VECTOR_DIM}, Qdrant has {qdrant_dim}"
            logger.error("embedding_dim_mismatch", expected=VECTOR_DIM, actual=qdrant_dim)
            
            # 记录失败审计
            try:
                session = get_db_session()
                record_embedding_usage_sync(
                    session=session,
                    tenant_id="system",
                    site_id=None,
                    object_type="system",
                    object_id="dim_check",
                    provider="system",
                    model="dim_check",
                    embedding_dim=VECTOR_DIM,
                    input_chars=0,
                    estimated_tokens=0,
                    latency_ms=0,
                    status="failed",
                    error_type="dim_mismatch",
                    error_message=error_msg,
                )
                session.commit()
                session.close()
            except Exception as e:
                logger.warning("failed_to_record_dim_mismatch", error=str(e))
            
            raise RuntimeError(error_msg)
        
        _qdrant_dim_validated = True
        logger.info("qdrant_dimension_validated", dim=VECTOR_DIM)
        
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("qdrant_dimension_check_failed", error=str(e))
        # 非致命错误，继续执行


# ============================================================
# Embedding 调用（带审计）
# ============================================================

def get_embedding_with_audit(
    text: str,
    max_retries: int = 3,
) -> EmbeddingResult:
    """
    获取文本向量（带审计信息）
    
    支持：
    - OpenAI (text-embedding-3-small)
    - Baidu BCE (bge-large-zh)
    - Baidu OAuth (embedding-v1)
    
    包含限流重试逻辑
    """
    input_chars = len(text)
    estimated_tokens = estimate_tokens(text)
    content_hash = compute_content_hash(text)
    start_time = time.time()
    
    # 尝试 Baidu BCE API Key 格式
    baidu_bce_key = getattr(settings, 'BAIDU_BCE_KEY', '')
    if baidu_bce_key and baidu_bce_key.startswith("bce-v3/"):
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=30) as client:
                    embed_resp = client.post(
                        "https://qianfan.baidubce.com/v2/embeddings",
                        headers={
                            "Authorization": f"Bearer {baidu_bce_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "bge-large-zh",
                            "input": [text[:1000]],
                        },
                    )
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    if embed_resp.status_code == 200:
                        data = embed_resp.json()
                        if "data" in data and len(data["data"]) > 0:
                            embedding = data["data"][0]["embedding"]
                            return EmbeddingResult(
                                embedding=embedding,
                                provider="baidu",
                                model="bge-large-zh",
                                embedding_dim=len(embedding),
                                input_chars=input_chars,
                                estimated_tokens=estimated_tokens,
                                latency_ms=latency_ms,
                                status="success",
                                content_hash=content_hash,
                            )
                    elif embed_resp.status_code == 429:
                        backoff = 2 ** attempt * 10  # 10s, 20s, 40s
                        logger.warning("rate_limited", attempt=attempt, backoff=backoff)
                        if attempt < max_retries - 1:
                            time.sleep(backoff)
                            continue
                        return EmbeddingResult(
                            provider="baidu",
                            model="bge-large-zh",
                            embedding_dim=0,
                            input_chars=input_chars,
                            estimated_tokens=estimated_tokens,
                            latency_ms=latency_ms,
                            status="rate_limited",
                            error_type="rate_limit",
                            backoff_seconds=backoff,
                            content_hash=content_hash,
                        )
                    else:
                        return EmbeddingResult(
                            provider="baidu",
                            model="bge-large-zh",
                            embedding_dim=0,
                            input_chars=input_chars,
                            estimated_tokens=estimated_tokens,
                            latency_ms=latency_ms,
                            status="failed",
                            error_type="api_error",
                            error_message=embed_resp.text[:200],
                            content_hash=content_hash,
                        )
            except Exception as e:
                logger.error("baidu_bce_embedding_error", error=str(e), attempt=attempt)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
    
    # 尝试 OpenAI
    openai_key = getattr(settings, 'OPENAI_API_KEY', '')
    if openai_key:
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "text-embedding-3-small",
                        "input": text[:8000],
                    },
                )
                latency_ms = int((time.time() - start_time) * 1000)
                
                if resp.status_code == 200:
                    data = resp.json()
                    embedding = data["data"][0]["embedding"]
                    return EmbeddingResult(
                        embedding=embedding,
                        provider="openai",
                        model="text-embedding-3-small",
                        embedding_dim=len(embedding),
                        input_chars=input_chars,
                        estimated_tokens=estimated_tokens,
                        latency_ms=latency_ms,
                        status="success",
                        content_hash=content_hash,
                    )
                elif resp.status_code == 429:
                    return EmbeddingResult(
                        provider="openai",
                        model="text-embedding-3-small",
                        embedding_dim=0,
                        input_chars=input_chars,
                        estimated_tokens=estimated_tokens,
                        latency_ms=latency_ms,
                        status="rate_limited",
                        error_type="rate_limit",
                        backoff_seconds=60,
                        content_hash=content_hash,
                    )
        except Exception as e:
            logger.error("openai_embedding_error", error=str(e))
    
    # 无可用 provider
    latency_ms = int((time.time() - start_time) * 1000)
    return EmbeddingResult(
        provider="none",
        model="none",
        embedding_dim=0,
        input_chars=input_chars,
        estimated_tokens=estimated_tokens,
        latency_ms=latency_ms,
        status="failed",
        error_type="no_provider",
        content_hash=content_hash,
    )


# ============================================================
# 审计记录
# ============================================================

def record_embedding_usage_sync(
    session,
    tenant_id: str,
    site_id: Optional[str],
    object_type: str,
    object_id: str,
    provider: str,
    model: str,
    embedding_dim: int,
    input_chars: int,
    estimated_tokens: int,
    latency_ms: int,
    status: str,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    backoff_seconds: Optional[int] = None,
    content_hash: Optional[str] = None,
    job_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    """记录 embedding 使用审计（同步版本）"""
    cost_estimate = calculate_cost(provider, model, estimated_tokens)
    
    session.execute(
        text("""
            INSERT INTO embedding_usage (
                tenant_id, site_id, object_type, object_id,
                provider, model, embedding_dim,
                input_chars, estimated_tokens, cost_estimate,
                latency_ms, status, error_type, error_message,
                backoff_seconds, content_hash, job_id, trace_id
            ) VALUES (
                :tenant_id, :site_id, :object_type, :object_id,
                :provider, :model, :embedding_dim,
                :input_chars, :estimated_tokens, :cost_estimate,
                :latency_ms, :status, :error_type, :error_message,
                :backoff_seconds, :content_hash, :job_id, :trace_id
            )
        """),
        {
            "tenant_id": tenant_id,
            "site_id": site_id,
            "object_type": object_type,
            "object_id": object_id,
            "provider": provider,
            "model": model,
            "embedding_dim": embedding_dim,
            "input_chars": input_chars,
            "estimated_tokens": estimated_tokens,
            "cost_estimate": cost_estimate,
            "latency_ms": latency_ms,
            "status": status,
            "error_type": error_type,
            "error_message": error_message[:500] if error_message else None,
            "backoff_seconds": backoff_seconds,
            "content_hash": content_hash,
            "job_id": job_id,
            "trace_id": trace_id,
        },
    )


# ============================================================
# 统一封装：embed_with_audit
# ============================================================

def embed_with_audit(
    tenant_id: str,
    site_id: Optional[str],
    object_type: str,
    object_id: str,
    text: str,
    existing_hash: Optional[str] = None,
    job_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> EmbeddingResult:
    """
    统一的 embedding 调用封装
    
    实现：
    1. Hash 去重检查
    2. 调用 embedding API
    3. 记录审计日志
    
    Args:
        tenant_id: 租户 ID
        site_id: 站点 ID
        object_type: 对象类型 (evidence/content/content_chunk)
        object_id: 对象 ID
        text: 待向量化文本
        existing_hash: 已有的 content hash（用于去重判断）
        job_id: 任务 ID
        trace_id: 追踪 ID
        
    Returns:
        EmbeddingResult
    """
    session = get_db_session()
    
    try:
        # 1. 计算 content hash
        content_hash = compute_content_hash(text)
        
        # 2. 去重检查
        if existing_hash and existing_hash == content_hash:
            # 命中去重
            result = EmbeddingResult(
                provider="dedup",
                model="hash_check",
                embedding_dim=0,
                input_chars=len(text),
                estimated_tokens=estimate_tokens(text),
                latency_ms=0,
                status="dedup_hit",
                content_hash=content_hash,
            )
            
            record_embedding_usage_sync(
                session=session,
                tenant_id=tenant_id,
                site_id=site_id,
                object_type=object_type,
                object_id=object_id,
                provider=result.provider,
                model=result.model,
                embedding_dim=result.embedding_dim,
                input_chars=result.input_chars,
                estimated_tokens=result.estimated_tokens,
                latency_ms=result.latency_ms,
                status=result.status,
                content_hash=content_hash,
                job_id=job_id,
                trace_id=trace_id,
            )
            session.commit()
            
            logger.info("embedding_dedup_hit", object_type=object_type, object_id=object_id)
            return result
        
        # 3. 调用 embedding API
        result = get_embedding_with_audit(text)
        result.content_hash = content_hash
        
        # 4. 记录审计
        record_embedding_usage_sync(
            session=session,
            tenant_id=tenant_id,
            site_id=site_id,
            object_type=object_type,
            object_id=object_id,
            provider=result.provider,
            model=result.model,
            embedding_dim=result.embedding_dim,
            input_chars=result.input_chars,
            estimated_tokens=result.estimated_tokens,
            latency_ms=result.latency_ms,
            status=result.status,
            error_type=result.error_type,
            error_message=result.error_message,
            backoff_seconds=result.backoff_seconds,
            content_hash=content_hash,
            job_id=job_id,
            trace_id=trace_id,
        )
        session.commit()
        
        logger.info(
            "embedding_complete",
            object_type=object_type,
            object_id=object_id,
            status=result.status,
            latency_ms=result.latency_ms,
        )
        
        return result
        
    except Exception as e:
        session.rollback()
        logger.error("embed_with_audit_error", error=str(e))
        raise
    finally:
        session.close()
