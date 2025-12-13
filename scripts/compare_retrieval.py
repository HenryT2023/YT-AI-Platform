#!/usr/bin/env python3
"""
检索策略对比脚本

对比 trgm vs qdrant vs hybrid 的命中情况

用法:
    python scripts/compare_retrieval.py --query "严氏是什么时候迁来的"
    python scripts/compare_retrieval.py --file queries.txt
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime

import httpx


@dataclass
class RetrievalResult:
    """检索结果"""
    id: str
    title: Optional[str]
    excerpt: str
    score: float
    trgm_score: Optional[float]
    qdrant_score: Optional[float]


@dataclass
class ComparisonResult:
    """对比结果"""
    query: str
    trgm_results: List[RetrievalResult]
    qdrant_results: List[RetrievalResult]
    hybrid_results: List[RetrievalResult]
    trgm_ids: set
    qdrant_ids: set
    hybrid_ids: set
    overlap_trgm_qdrant: set
    only_trgm: set
    only_qdrant: set
    metrics: dict


async def retrieve(
    base_url: str,
    query: str,
    strategy: str,
    tenant_id: str = "yantian",
    site_id: str = "yantian-main",
    limit: int = 10,
    min_score: float = 0.3,
) -> List[RetrievalResult]:
    """调用检索 API"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base_url}/tools/call",
            json={
                "tool_name": "retrieve_evidence",
                "input": {
                    "query": query,
                    "strategy": strategy,
                    "limit": limit,
                    "min_score": min_score,
                },
                "context": {
                    "tenant_id": tenant_id,
                    "site_id": site_id,
                    "trace_id": f"compare-{datetime.now().isoformat()}",
                },
            },
        )

        if resp.status_code != 200:
            print(f"Error: {resp.status_code} - {resp.text}")
            return []

        data = resp.json()
        if not data.get("success"):
            print(f"Error: {data.get('error')}")
            return []

        items = data.get("output", {}).get("items", [])
        return [
            RetrievalResult(
                id=item["id"],
                title=item.get("title"),
                excerpt=item.get("excerpt", "")[:100],
                score=item.get("retrieval_score", 0),
                trgm_score=item.get("trgm_score"),
                qdrant_score=item.get("qdrant_score"),
            )
            for item in items
        ]


async def compare_query(
    base_url: str,
    query: str,
    tenant_id: str = "yantian",
    site_id: str = "yantian-main",
) -> ComparisonResult:
    """对比单个查询"""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    # 并行执行三种检索
    trgm_task = retrieve(base_url, query, "trgm", tenant_id, site_id)
    qdrant_task = retrieve(base_url, query, "qdrant", tenant_id, site_id)
    hybrid_task = retrieve(base_url, query, "hybrid", tenant_id, site_id)

    trgm_results, qdrant_results, hybrid_results = await asyncio.gather(
        trgm_task, qdrant_task, hybrid_task
    )

    # 提取 ID 集合
    trgm_ids = {r.id for r in trgm_results}
    qdrant_ids = {r.id for r in qdrant_results}
    hybrid_ids = {r.id for r in hybrid_results}

    # 计算重叠
    overlap = trgm_ids & qdrant_ids
    only_trgm = trgm_ids - qdrant_ids
    only_qdrant = qdrant_ids - trgm_ids

    # 计算指标
    metrics = {
        "trgm_count": len(trgm_results),
        "qdrant_count": len(qdrant_results),
        "hybrid_count": len(hybrid_results),
        "overlap_count": len(overlap),
        "only_trgm_count": len(only_trgm),
        "only_qdrant_count": len(only_qdrant),
        "overlap_ratio": len(overlap) / max(len(trgm_ids | qdrant_ids), 1),
        "trgm_avg_score": sum(r.score for r in trgm_results) / max(len(trgm_results), 1),
        "qdrant_avg_score": sum(r.score for r in qdrant_results) / max(len(qdrant_results), 1),
        "hybrid_avg_score": sum(r.score for r in hybrid_results) / max(len(hybrid_results), 1),
    }

    # 打印结果
    print(f"\n📊 Results Summary:")
    print(f"  trgm:   {metrics['trgm_count']} hits (avg score: {metrics['trgm_avg_score']:.3f})")
    print(f"  qdrant: {metrics['qdrant_count']} hits (avg score: {metrics['qdrant_avg_score']:.3f})")
    print(f"  hybrid: {metrics['hybrid_count']} hits (avg score: {metrics['hybrid_avg_score']:.3f})")

    print(f"\n🔗 Overlap Analysis:")
    print(f"  Both:       {metrics['overlap_count']}")
    print(f"  Only trgm:  {metrics['only_trgm_count']}")
    print(f"  Only qdrant:{metrics['only_qdrant_count']}")
    print(f"  Overlap %:  {metrics['overlap_ratio']*100:.1f}%")

    if trgm_results:
        print(f"\n📝 Top trgm results:")
        for i, r in enumerate(trgm_results[:3]):
            print(f"  {i+1}. [{r.score:.3f}] {r.title or 'N/A'}")

    if qdrant_results:
        print(f"\n📝 Top qdrant results:")
        for i, r in enumerate(qdrant_results[:3]):
            print(f"  {i+1}. [{r.score:.3f}] {r.title or 'N/A'}")

    if hybrid_results:
        print(f"\n📝 Top hybrid results:")
        for i, r in enumerate(hybrid_results[:3]):
            trgm = f"trgm:{r.trgm_score:.3f}" if r.trgm_score else "trgm:N/A"
            qdrant = f"qdrant:{r.qdrant_score:.3f}" if r.qdrant_score else "qdrant:N/A"
            print(f"  {i+1}. [{r.score:.3f}] {r.title or 'N/A'} ({trgm}, {qdrant})")

    return ComparisonResult(
        query=query,
        trgm_results=trgm_results,
        qdrant_results=qdrant_results,
        hybrid_results=hybrid_results,
        trgm_ids=trgm_ids,
        qdrant_ids=qdrant_ids,
        hybrid_ids=hybrid_ids,
        overlap_trgm_qdrant=overlap,
        only_trgm=only_trgm,
        only_qdrant=only_qdrant,
        metrics=metrics,
    )


async def main():
    parser = argparse.ArgumentParser(description="Compare retrieval strategies")
    parser.add_argument("--query", "-q", help="Single query to test")
    parser.add_argument("--file", "-f", help="File with queries (one per line)")
    parser.add_argument("--url", default="http://localhost:8000/api", help="Core backend URL")
    parser.add_argument("--tenant", default="yantian", help="Tenant ID")
    parser.add_argument("--site", default="yantian-main", help="Site ID")
    parser.add_argument("--output", "-o", help="Output JSON file")

    args = parser.parse_args()

    queries = []
    if args.query:
        queries.append(args.query)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            queries = [line.strip() for line in f if line.strip()]
    else:
        # 默认测试查询
        queries = [
            "严氏是什么时候迁来的",
            "严田村有什么历史",
            "族谱记载了什么",
            "这里的建筑有什么特点",
            "农耕文化",
        ]

    results = []
    for query in queries:
        result = await compare_query(args.url, query, args.tenant, args.site)
        results.append(result)

    # 汇总统计
    print(f"\n{'='*60}")
    print("📈 Overall Summary")
    print(f"{'='*60}")

    total_trgm = sum(r.metrics["trgm_count"] for r in results)
    total_qdrant = sum(r.metrics["qdrant_count"] for r in results)
    total_hybrid = sum(r.metrics["hybrid_count"] for r in results)
    total_overlap = sum(r.metrics["overlap_count"] for r in results)

    print(f"  Total queries:  {len(results)}")
    print(f"  Total trgm:     {total_trgm}")
    print(f"  Total qdrant:   {total_qdrant}")
    print(f"  Total hybrid:   {total_hybrid}")
    print(f"  Total overlap:  {total_overlap}")

    avg_overlap_ratio = sum(r.metrics["overlap_ratio"] for r in results) / max(len(results), 1)
    print(f"  Avg overlap %:  {avg_overlap_ratio*100:.1f}%")

    # 输出 JSON
    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "queries": len(results),
            "summary": {
                "total_trgm": total_trgm,
                "total_qdrant": total_qdrant,
                "total_hybrid": total_hybrid,
                "total_overlap": total_overlap,
                "avg_overlap_ratio": avg_overlap_ratio,
            },
            "results": [
                {
                    "query": r.query,
                    "metrics": r.metrics,
                    "trgm_ids": list(r.trgm_ids),
                    "qdrant_ids": list(r.qdrant_ids),
                    "overlap": list(r.overlap_trgm_qdrant),
                }
                for r in results
            ],
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n📁 Results saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
