#!/usr/bin/env python3
"""
向量索引全量同步脚本

用法:
    python scripts/sync_vectors.py --tenant-id yantian
    python scripts/sync_vectors.py --tenant-id yantian --site-id yantian-main
    python scripts/sync_vectors.py --tenant-id yantian --dry-run

功能:
    1. 从 PostgreSQL 读取所有 evidence
    2. 向量化并写入 Qdrant
    3. 更新 evidence.vector_updated_at
    4. 记录同步任务到 vector_sync_jobs
"""

import argparse
import asyncio
import hashlib
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

# 添加项目路径
sys.path.insert(0, "/Users/hal/YT-AI-Platform/services/core-backend")

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)


# ============================================================
# 配置
# ============================================================

import os
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
)
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "yantian_evidence"
BATCH_SIZE = 50
VECTOR_DIM = 1024


# ============================================================
# Embedding 获取
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


def estimate_tokens(text: str) -> int:
    """估算 token 数量（粗略：1.5 字符/token）"""
    return max(1, len(text) // 2)


async def get_embedding_with_audit(text: str, settings: Dict[str, str]) -> EmbeddingResult:
    """获取文本向量（带审计信息）"""
    import httpx

    input_chars = len(text)
    estimated_tokens = estimate_tokens(text)
    start_time = time.time()

    # 优先使用 OpenAI
    openai_key = settings.get("OPENAI_API_KEY", "")
    if openai_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
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
                    )
                else:
                    return EmbeddingResult(
                        provider="openai",
                        model="text-embedding-3-small",
                        embedding_dim=0,
                        input_chars=input_chars,
                        estimated_tokens=estimated_tokens,
                        latency_ms=latency_ms,
                        status="failed",
                        error_type="api_error",
                        error_message=resp.text[:200],
                    )
        except Exception as e:
            logger.error("openai_embedding_error", error=str(e))

    # 回退：Baidu BCE API Key 格式 (bce-v3/ALTAK-xxx/secret)
    baidu_bce_key = settings.get("BAIDU_BCE_KEY", "")
    if baidu_bce_key and baidu_bce_key.startswith("bce-v3/"):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                embed_resp = await client.post(
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
                        )
                elif embed_resp.status_code == 429:
                    return EmbeddingResult(
                        provider="baidu",
                        model="bge-large-zh",
                        embedding_dim=0,
                        input_chars=input_chars,
                        estimated_tokens=estimated_tokens,
                        latency_ms=latency_ms,
                        status="rate_limited",
                        error_type="rate_limit",
                        backoff_seconds=60,
                    )
                else:
                    logger.warning("baidu_bce_embedding_failed", status=embed_resp.status_code, body=embed_resp.text[:200])
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
                    )
        except Exception as e:
            logger.error("baidu_bce_embedding_error", error=str(e))

    # 回退：Baidu OAuth 格式
    baidu_key = settings.get("BAIDU_API_KEY", "")
    baidu_secret = settings.get("BAIDU_SECRET_KEY", "")
    if baidu_key and baidu_secret:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token_resp = await client.post(
                    "https://aip.baidubce.com/oauth/2.0/token",
                    params={
                        "grant_type": "client_credentials",
                        "client_id": baidu_key,
                        "client_secret": baidu_secret,
                    },
                )
                if token_resp.status_code != 200:
                    latency_ms = int((time.time() - start_time) * 1000)
                    return EmbeddingResult(
                        provider="baidu",
                        model="embedding-v1",
                        embedding_dim=0,
                        input_chars=input_chars,
                        estimated_tokens=estimated_tokens,
                        latency_ms=latency_ms,
                        status="failed",
                        error_type="auth_error",
                    )
                access_token = token_resp.json().get("access_token")

                embed_resp = await client.post(
                    f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/embeddings/embedding-v1?access_token={access_token}",
                    json={"input": [text[:1000]]},
                )
                latency_ms = int((time.time() - start_time) * 1000)
                if embed_resp.status_code == 200:
                    data = embed_resp.json()
                    if "data" in data and len(data["data"]) > 0:
                        embedding = data["data"][0]["embedding"]
                        return EmbeddingResult(
                            embedding=embedding,
                            provider="baidu",
                            model="embedding-v1",
                            embedding_dim=len(embedding),
                            input_chars=input_chars,
                            estimated_tokens=estimated_tokens,
                            latency_ms=latency_ms,
                            status="success",
                        )
        except Exception as e:
            logger.error("baidu_embedding_error", error=str(e))

    # 无可用 provider
    latency_ms = int((time.time() - start_time) * 1000) if 'start_time' in dir() else 0
    return EmbeddingResult(
        provider="none",
        model="none",
        embedding_dim=0,
        input_chars=input_chars,
        estimated_tokens=estimated_tokens,
        latency_ms=latency_ms,
        status="failed",
        error_type="no_provider",
    )


def compute_content_hash(title: Optional[str], excerpt: str) -> str:
    """计算内容 hash"""
    content = f"{title or ''}\n{excerpt}"
    return hashlib.sha256(content.encode()).hexdigest()


# Embedding 定价表 (USD per 1K tokens)
EMBEDDING_PRICING = {
    "openai": {"text-embedding-3-small": 0.00002, "text-embedding-3-large": 0.00013},
    "baidu": {"bge-large-zh": 0.0001, "embedding-v1": 0.0001},
    "dedup": {"hash_check": 0.0},
    "none": {"none": 0.0},
}


def calculate_cost(provider: str, model: str, tokens: int) -> float:
    """计算成本估算 (USD)"""
    provider_prices = EMBEDDING_PRICING.get(provider, {})
    price_per_1k = provider_prices.get(model, 0.0001)
    return (tokens / 1000) * price_per_1k


async def record_embedding_usage(
    session: AsyncSession,
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
    """记录 embedding 使用审计"""
    from sqlalchemy import text
    
    cost_estimate = calculate_cost(provider, model, estimated_tokens)
    
    await session.execute(
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


def generate_point_id(evidence_id: str) -> str:
    """生成 Qdrant point ID"""
    hash_bytes = hashlib.md5(evidence_id.encode()).hexdigest()
    return f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}"


# ============================================================
# 同步逻辑
# ============================================================

async def sync_vectors(
    tenant_id: str,
    site_id: Optional[str] = None,
    dry_run: bool = False,
    batch_size: int = BATCH_SIZE,
    settings: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    全量同步向量

    Args:
        tenant_id: 租户 ID
        site_id: 站点 ID（可选）
        dry_run: 只统计，不写入
        batch_size: 批次大小
        settings: 配置（包含 API keys）

    Returns:
        同步结果统计
    """
    from app.database.models import Evidence, VectorSyncJob

    settings = settings or {}
    start_time = time.time()
    job_id = str(uuid4())

    logger.info(
        "sync_vectors_start",
        job_id=job_id,
        tenant_id=tenant_id,
        site_id=site_id,
        dry_run=dry_run,
    )

    # 创建数据库连接
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 统计
    stats = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "site_id": site_id,
        "dry_run": dry_run,
        "total": 0,
        "success": 0,
        "skip": 0,
        "failure": 0,
        "errors": [],
    }

    async with async_session() as session:
        # 1. 创建同步任务记录
        if not dry_run:
            job = VectorSyncJob(
                id=job_id,
                tenant_id=tenant_id,
                site_id=site_id,
                job_type="full_sync",
                status="running",
                started_at=datetime.now(timezone.utc),
                config={"batch_size": batch_size, "dry_run": dry_run},
                triggered_by="cli",
            )
            session.add(job)
            await session.commit()

        # 2. 查询 evidence 总数
        count_stmt = select(func.count(Evidence.id)).where(
            Evidence.tenant_id == tenant_id,
            Evidence.deleted_at.is_(None),
        )
        if site_id:
            count_stmt = count_stmt.where(Evidence.site_id == site_id)

        result = await session.execute(count_stmt)
        total_count = result.scalar() or 0
        stats["total"] = total_count

        logger.info("sync_vectors_total", total=total_count)

        if total_count == 0:
            logger.info("sync_vectors_no_data")
            return stats

        # 3. 初始化 Qdrant
        if not dry_run:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance

            qdrant = QdrantClient(url=QDRANT_URL, timeout=30)

            # 确保 collection 存在
            collections = qdrant.get_collections().collections
            collection_names = [c.name for c in collections]
            if QDRANT_COLLECTION not in collection_names:
                qdrant.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=VECTOR_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("qdrant_collection_created", name=QDRANT_COLLECTION)

        # 4. 分批处理
        total_batches = (total_count + batch_size - 1) // batch_size
        current_batch = 0

        offset = 0
        while offset < total_count:
            current_batch += 1
            logger.info(
                "sync_vectors_batch",
                batch=current_batch,
                total_batches=total_batches,
                offset=offset,
            )

            # 查询一批 evidence
            stmt = (
                select(Evidence)
                .where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.deleted_at.is_(None),
                )
                .order_by(Evidence.created_at)
                .offset(offset)
                .limit(batch_size)
            )
            if site_id:
                stmt = stmt.where(Evidence.site_id == site_id)

            result = await session.execute(stmt)
            evidences = result.scalars().all()

            if not evidences:
                break

            # 处理每条 evidence
            points_to_upsert = []
            evidence_ids_to_update = []

            for evidence in evidences:
                try:
                    # 计算内容 hash
                    content_hash = compute_content_hash(evidence.title, evidence.excerpt)

                    # 检查是否需要更新（去重）
                    if evidence.vector_hash == content_hash:
                        stats["skip"] += 1
                        # 记录 dedup_hit
                        if not dry_run:
                            await record_embedding_usage(
                                session=session,
                                tenant_id=evidence.tenant_id,
                                site_id=evidence.site_id,
                                object_type="evidence",
                                object_id=evidence.id,
                                provider="dedup",
                                model="hash_check",
                                embedding_dim=0,
                                input_chars=len(evidence.excerpt),
                                estimated_tokens=estimate_tokens(evidence.excerpt),
                                latency_ms=0,
                                status="dedup_hit",
                                content_hash=content_hash,
                                job_id=job_id,
                            )
                        continue

                    if dry_run:
                        stats["success"] += 1
                        continue

                    # 构建文本
                    text_parts = []
                    if evidence.title:
                        text_parts.append(evidence.title)
                    text_parts.append(evidence.excerpt)
                    text = "\n".join(text_parts)

                    # 获取向量（带审计）
                    embed_result = await get_embedding_with_audit(text, settings)
                    
                    # 记录 embedding_usage
                    await record_embedding_usage(
                        session=session,
                        tenant_id=evidence.tenant_id,
                        site_id=evidence.site_id,
                        object_type="evidence",
                        object_id=evidence.id,
                        provider=embed_result.provider,
                        model=embed_result.model,
                        embedding_dim=embed_result.embedding_dim,
                        input_chars=embed_result.input_chars,
                        estimated_tokens=embed_result.estimated_tokens,
                        latency_ms=embed_result.latency_ms,
                        status=embed_result.status,
                        error_type=embed_result.error_type,
                        error_message=embed_result.error_message,
                        backoff_seconds=embed_result.backoff_seconds,
                        content_hash=content_hash,
                        job_id=job_id,
                    )
                    
                    if not embed_result.embedding:
                        stats["failure"] += 1
                        stats["errors"].append({
                            "evidence_id": evidence.id,
                            "error": embed_result.status,
                        })
                        continue
                    
                    embedding = embed_result.embedding

                    # 构建 point
                    from qdrant_client.models import PointStruct

                    point_id = generate_point_id(evidence.id)
                    points_to_upsert.append(
                        PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "evidence_id": evidence.id,
                                "tenant_id": evidence.tenant_id,
                                "site_id": evidence.site_id,
                                "source_type": evidence.source_type,
                                "source_ref": evidence.source_ref,
                                "title": evidence.title,
                                "excerpt": evidence.excerpt[:500],
                                "confidence": evidence.confidence,
                                "verified": evidence.verified,
                                "tags": evidence.tags or [],
                                "domains": evidence.domains or [],
                            },
                        )
                    )
                    evidence_ids_to_update.append((evidence.id, content_hash))
                    stats["success"] += 1

                except Exception as e:
                    stats["failure"] += 1
                    stats["errors"].append({
                        "evidence_id": evidence.id,
                        "error": str(e),
                    })
                    logger.error("sync_vectors_evidence_error", evidence_id=evidence.id, error=str(e))

            # 批量写入 Qdrant
            if points_to_upsert and not dry_run:
                qdrant.upsert(
                    collection_name=QDRANT_COLLECTION,
                    points=points_to_upsert,
                )
                logger.info("qdrant_upsert", count=len(points_to_upsert))

            # 批量更新 evidence.vector_updated_at
            if evidence_ids_to_update and not dry_run:
                now = datetime.now(timezone.utc)
                for eid, ehash in evidence_ids_to_update:
                    await session.execute(
                        update(Evidence)
                        .where(Evidence.id == eid)
                        .values(vector_updated_at=now, vector_hash=ehash)
                    )
                await session.commit()

            # 更新任务进度
            if not dry_run:
                progress = min(100.0, (offset + len(evidences)) / total_count * 100)
                await session.execute(
                    update(VectorSyncJob)
                    .where(VectorSyncJob.id == job_id)
                    .values(
                        progress_percent=progress,
                        current_batch=current_batch,
                        total_batches=total_batches,
                        success_count=stats["success"],
                        skip_count=stats["skip"],
                        failure_count=stats["failure"],
                    )
                )
                await session.commit()

            offset += batch_size

        # 5. 完成任务
        elapsed = time.time() - start_time
        stats["elapsed_seconds"] = elapsed

        if not dry_run:
            status = "success" if stats["failure"] == 0 else "partial_failed"
            await session.execute(
                update(VectorSyncJob)
                .where(VectorSyncJob.id == job_id)
                .values(
                    status=status,
                    finished_at=datetime.now(timezone.utc),
                    total_items=stats["total"],
                    success_count=stats["success"],
                    skip_count=stats["skip"],
                    failure_count=stats["failure"],
                    progress_percent=100.0,
                    error_summary={"errors": stats["errors"][:100]},  # 只保留前 100 条错误
                )
            )
            await session.commit()

        logger.info(
            "sync_vectors_complete",
            job_id=job_id,
            total=stats["total"],
            success=stats["success"],
            skip=stats["skip"],
            failure=stats["failure"],
            elapsed_seconds=elapsed,
        )

    await engine.dispose()
    return stats


# ============================================================
# CLI
# ============================================================

def print_stats(stats: Dict[str, Any]) -> None:
    """打印统计结果"""
    print("\n" + "=" * 60)
    print("📊 向量同步结果")
    print("=" * 60)
    print(f"  Job ID:       {stats['job_id']}")
    print(f"  Tenant:       {stats['tenant_id']}")
    print(f"  Site:         {stats.get('site_id', 'all')}")
    print(f"  Dry Run:      {stats['dry_run']}")
    print("-" * 60)
    print(f"  总 Evidence:  {stats['total']}")
    print(f"  成功向量化:   {stats['success']}")
    print(f"  跳过(重复):   {stats['skip']}")
    print(f"  失败:         {stats['failure']}")
    print("-" * 60)

    if stats['total'] > 0:
        coverage = (stats['success'] + stats['skip']) / stats['total'] * 100
        print(f"  覆盖率:       {coverage:.1f}%")

    if 'elapsed_seconds' in stats:
        print(f"  耗时:         {stats['elapsed_seconds']:.2f}s")

    if stats['errors']:
        print("-" * 60)
        print(f"  错误详情 (前 5 条):")
        for err in stats['errors'][:5]:
            print(f"    - {err['evidence_id']}: {err['error']}")

    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="向量索引全量同步")
    parser.add_argument("--tenant-id", required=True, help="租户 ID")
    parser.add_argument("--site-id", help="站点 ID（可选）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="批次大小")
    parser.add_argument("--openai-key", help="OpenAI API Key")
    parser.add_argument("--baidu-key", help="Baidu API Key")
    parser.add_argument("--baidu-secret", help="Baidu Secret Key")

    args = parser.parse_args()

    # 构建配置
    import os
    settings = {
        "OPENAI_API_KEY": args.openai_key or os.environ.get("OPENAI_API_KEY", ""),
        "BAIDU_API_KEY": args.baidu_key or os.environ.get("BAIDU_API_KEY", ""),
        "BAIDU_SECRET_KEY": args.baidu_secret or os.environ.get("BAIDU_SECRET_KEY", ""),
        "BAIDU_BCE_KEY": os.environ.get("BAIDU_BCE_KEY", ""),
    }

    print(f"\n🚀 开始向量同步...")
    print(f"   Tenant: {args.tenant_id}")
    print(f"   Site:   {args.site_id or 'all'}")
    print(f"   Mode:   {'DRY RUN' if args.dry_run else 'LIVE'}")

    stats = await sync_vectors(
        tenant_id=args.tenant_id,
        site_id=args.site_id,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        settings=settings,
    )

    print_stats(stats)

    # 返回码
    if stats["failure"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
