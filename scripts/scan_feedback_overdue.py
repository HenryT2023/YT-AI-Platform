#!/usr/bin/env python3
"""
反馈逾期扫描脚本

扫描 status != resolved/closed 且 sla_due_at < now 的反馈，标记为 overdue

使用方式:
    python scripts/scan_feedback_overdue.py --dry-run
    python scripts/scan_feedback_overdue.py
"""

import argparse
import asyncio
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, "/Users/hal/YT-AI-Platform/services/core-backend")

import structlog
from sqlalchemy import text, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)

# 数据库连接
import os
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
)


async def scan_feedback_overdue(
    dry_run: bool = False,
    tenant_id: str = None,
) -> dict:
    """
    扫描并标记逾期反馈
    
    Args:
        dry_run: 只统计，不更新
        tenant_id: 租户 ID（可选，不指定则扫描所有）
        
    Returns:
        扫描结果
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    now = datetime.utcnow()
    
    async with async_session() as session:
        # 构建条件（使用数据库的 now() 避免时区问题）
        where_clauses = [
            "sla_due_at < now()",
            "overdue_flag = false",
            "status NOT IN ('resolved', 'closed')",
        ]
        params = {}
        
        if tenant_id:
            where_clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        
        where_sql = " AND ".join(where_clauses)
        
        # 统计待标记数量
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM user_feedbacks WHERE {where_sql}"),
            params,
        )
        count = count_result.scalar()
        
        if dry_run:
            # 获取详情
            detail_result = await session.execute(
                text(f"""
                    SELECT id, tenant_id, site_id, severity, feedback_type, sla_due_at, status
                    FROM user_feedbacks
                    WHERE {where_sql}
                    ORDER BY sla_due_at
                    LIMIT 20
                """),
                params,
            )
            details = [
                {
                    "id": str(row[0]),
                    "tenant_id": row[1],
                    "site_id": row[2],
                    "severity": row[3],
                    "feedback_type": row[4],
                    "sla_due_at": row[5].isoformat() if row[5] else None,
                    "status": row[6],
                }
                for row in detail_result.all()
            ]
            
            logger.info(
                "scan_feedback_overdue_dry_run",
                count=count,
                tenant_id=tenant_id,
            )
            
            return {
                "status": "dry_run",
                "count": count,
                "tenant_id": tenant_id,
                "sample": details,
            }
        
        # 执行更新
        update_result = await session.execute(
            text(f"""
                UPDATE user_feedbacks
                SET overdue_flag = true, updated_at = now()
                WHERE {where_sql}
            """),
            params,
        )
        await session.commit()
        
        updated = update_result.rowcount
        
        logger.info(
            "scan_feedback_overdue_complete",
            updated=updated,
            tenant_id=tenant_id,
        )
        
        return {
            "status": "success",
            "updated": updated,
            "tenant_id": tenant_id,
            "scanned_at": now.isoformat(),
        }
    
    await engine.dispose()


async def main():
    parser = argparse.ArgumentParser(description="扫描并标记逾期反馈")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不更新")
    parser.add_argument("--tenant-id", type=str, help="租户 ID（可选）")
    
    args = parser.parse_args()
    
    print(f"\n🔍 反馈逾期扫描")
    print(f"   模式: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"   租户: {args.tenant_id or 'all'}")
    print()
    
    result = await scan_feedback_overdue(
        dry_run=args.dry_run,
        tenant_id=args.tenant_id,
    )
    
    if args.dry_run:
        print(f"📊 待标记逾期: {result['count']}")
        if result.get("sample"):
            print("\n示例记录:")
            for item in result["sample"][:5]:
                print(f"  - {item['id'][:8]}... | {item['severity']} | {item['feedback_type']} | SLA: {item['sla_due_at']}")
    else:
        print(f"✅ 已标记逾期: {result['updated']}")


if __name__ == "__main__":
    asyncio.run(main())
