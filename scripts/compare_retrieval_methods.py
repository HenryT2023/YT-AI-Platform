#!/usr/bin/env python3
"""
检索方法对比脚本

对比 LIKE vs pg_trgm 在同一查询下的命中结果差异

使用方法:
    python scripts/compare_retrieval_methods.py --query "严氏家训" --tenant yantian --site yantian-main

输出:
    - LIKE 命中结果
    - TRGM 命中结果
    - 差异分析（仅 LIKE、仅 TRGM、两者都有）
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# 添加项目路径
sys.path.insert(0, "services/core-backend")


@dataclass
class RetrievalResult:
    """检索结果"""
    id: str
    title: Optional[str]
    excerpt: str
    confidence: float
    retrieval_score: Optional[float]
    method: str


async def retrieve_like(
    session,
    tenant_id: str,
    site_id: str,
    query: str,
    limit: int = 10,
) -> List[RetrievalResult]:
    """使用 LIKE 检索"""
    from sqlalchemy import select, text
    from app.database.models import Evidence

    like_pattern = f"%{query}%"

    stmt = select(Evidence).where(
        Evidence.tenant_id == tenant_id,
        Evidence.site_id == site_id,
        Evidence.deleted_at.is_(None),
        (Evidence.excerpt.ilike(like_pattern) | Evidence.title.ilike(like_pattern)),
    ).order_by(Evidence.confidence.desc()).limit(limit)

    result = await session.execute(stmt)
    evidences = result.scalars().all()

    return [
        RetrievalResult(
            id=str(e.id),
            title=e.title,
            excerpt=e.excerpt[:200] if e.excerpt else "",
            confidence=e.confidence,
            retrieval_score=None,
            method="like",
        )
        for e in evidences
    ]


async def retrieve_trgm(
    session,
    tenant_id: str,
    site_id: str,
    query: str,
    min_score: float = 0.3,
    limit: int = 10,
) -> List[RetrievalResult]:
    """使用 pg_trgm 检索"""
    from sqlalchemy import text

    sql = text("""
        SELECT
            id,
            title,
            excerpt,
            confidence,
            GREATEST(
                COALESCE(similarity(title, :query), 0),
                COALESCE(similarity(excerpt, :query), 0)
            ) AS retrieval_score
        FROM evidences
        WHERE tenant_id = :tenant_id
          AND site_id = :site_id
          AND deleted_at IS NULL
          AND (
              title % :query
              OR excerpt % :query
          )
          AND GREATEST(
              COALESCE(similarity(title, :query), 0),
              COALESCE(similarity(excerpt, :query), 0)
          ) >= :min_score
        ORDER BY retrieval_score DESC, confidence DESC
        LIMIT :limit
    """)

    result = await session.execute(sql, {
        "tenant_id": tenant_id,
        "site_id": site_id,
        "query": query,
        "min_score": min_score,
        "limit": limit,
    })
    rows = result.fetchall()

    return [
        RetrievalResult(
            id=str(row.id),
            title=row.title,
            excerpt=row.excerpt[:200] if row.excerpt else "",
            confidence=float(row.confidence) if row.confidence else 1.0,
            retrieval_score=float(row.retrieval_score) if row.retrieval_score else 0.0,
            method="trgm",
        )
        for row in rows
    ]


def analyze_diff(
    like_results: List[RetrievalResult],
    trgm_results: List[RetrievalResult],
) -> Dict[str, Any]:
    """分析差异"""
    like_ids = {r.id for r in like_results}
    trgm_ids = {r.id for r in trgm_results}

    only_like = like_ids - trgm_ids
    only_trgm = trgm_ids - like_ids
    both = like_ids & trgm_ids

    return {
        "like_count": len(like_results),
        "trgm_count": len(trgm_results),
        "only_like_count": len(only_like),
        "only_trgm_count": len(only_trgm),
        "both_count": len(both),
        "only_like_ids": list(only_like),
        "only_trgm_ids": list(only_trgm),
        "both_ids": list(both),
    }


def print_results(
    query: str,
    like_results: List[RetrievalResult],
    trgm_results: List[RetrievalResult],
    diff: Dict[str, Any],
):
    """打印结果"""
    print("=" * 80)
    print(f"查询: {query}")
    print("=" * 80)

    print("\n## LIKE 结果")
    print("-" * 40)
    if like_results:
        for i, r in enumerate(like_results, 1):
            print(f"{i}. [{r.id[:8]}] {r.title or '(无标题)'}")
            print(f"   confidence: {r.confidence:.2f}")
            print(f"   excerpt: {r.excerpt[:80]}...")
    else:
        print("无结果")

    print("\n## TRGM 结果")
    print("-" * 40)
    if trgm_results:
        for i, r in enumerate(trgm_results, 1):
            print(f"{i}. [{r.id[:8]}] {r.title or '(无标题)'}")
            print(f"   retrieval_score: {r.retrieval_score:.3f}, confidence: {r.confidence:.2f}")
            print(f"   excerpt: {r.excerpt[:80]}...")
    else:
        print("无结果")

    print("\n## 差异分析")
    print("-" * 40)
    print(f"LIKE 命中数: {diff['like_count']}")
    print(f"TRGM 命中数: {diff['trgm_count']}")
    print(f"仅 LIKE 命中: {diff['only_like_count']}")
    print(f"仅 TRGM 命中: {diff['only_trgm_count']}")
    print(f"两者都命中: {diff['both_count']}")

    if diff['only_like_ids']:
        print(f"\n仅 LIKE 命中的 ID: {diff['only_like_ids']}")
    if diff['only_trgm_ids']:
        print(f"\n仅 TRGM 命中的 ID: {diff['only_trgm_ids']}")

    # 计算召回率变化
    if diff['like_count'] > 0:
        recall_change = (diff['trgm_count'] - diff['like_count']) / diff['like_count'] * 100
        print(f"\n召回率变化: {recall_change:+.1f}%")

    print("\n" + "=" * 80)


async def main():
    parser = argparse.ArgumentParser(description="对比 LIKE vs TRGM 检索结果")
    parser.add_argument("--query", "-q", required=True, help="搜索查询")
    parser.add_argument("--tenant", "-t", default="yantian", help="租户 ID")
    parser.add_argument("--site", "-s", default="yantian-main", help="站点 ID")
    parser.add_argument("--limit", "-l", type=int, default=10, help="返回数量限制")
    parser.add_argument("--min-score", type=float, default=0.3, help="TRGM 最小相似度")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    # 初始化数据库连接
    from app.database.session import async_session_maker

    async with async_session_maker() as session:
        # 执行两种检索
        like_results = await retrieve_like(
            session,
            args.tenant,
            args.site,
            args.query,
            args.limit,
        )

        trgm_results = await retrieve_trgm(
            session,
            args.tenant,
            args.site,
            args.query,
            args.min_score,
            args.limit,
        )

        # 分析差异
        diff = analyze_diff(like_results, trgm_results)

        if args.json:
            output = {
                "query": args.query,
                "like_results": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "excerpt": r.excerpt,
                        "confidence": r.confidence,
                    }
                    for r in like_results
                ],
                "trgm_results": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "excerpt": r.excerpt,
                        "confidence": r.confidence,
                        "retrieval_score": r.retrieval_score,
                    }
                    for r in trgm_results
                ],
                "diff": diff,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print_results(args.query, like_results, trgm_results, diff)


if __name__ == "__main__":
    asyncio.run(main())
