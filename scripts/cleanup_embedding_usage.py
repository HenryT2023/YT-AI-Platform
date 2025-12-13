#!/usr/bin/env python3
"""
Embedding Usage 数据清理脚本

定期清理过期的 embedding_usage 记录，保留指定天数的数据。

使用方式:
    python scripts/cleanup_embedding_usage.py --days 30 --dry-run
    python scripts/cleanup_embedding_usage.py --days 30
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, "/Users/hal/YT-AI-Platform/services/core-backend")

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)

# 数据库连接
import os
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
)


async def cleanup_embedding_usage(
    days: int = 30,
    dry_run: bool = False,
) -> dict:
    """
    清理过期的 embedding_usage 记录
    
    Args:
        days: 保留天数
        dry_run: 只统计，不删除
        
    Returns:
        清理结果
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    async with async_session() as session:
        # 统计待删除记录数
        count_result = await session.execute(
            text("SELECT COUNT(*) FROM embedding_usage WHERE created_at < :cutoff"),
            {"cutoff": cutoff_date},
        )
        count = count_result.scalar()
        
        if dry_run:
            logger.info(
                "cleanup_dry_run",
                days=days,
                cutoff_date=cutoff_date.isoformat(),
                records_to_delete=count,
            )
            return {
                "status": "dry_run",
                "days": days,
                "cutoff_date": cutoff_date.isoformat(),
                "records_to_delete": count,
            }
        
        # 执行删除
        delete_result = await session.execute(
            text("DELETE FROM embedding_usage WHERE created_at < :cutoff"),
            {"cutoff": cutoff_date},
        )
        await session.commit()
        
        deleted = delete_result.rowcount
        logger.info(
            "cleanup_complete",
            days=days,
            cutoff_date=cutoff_date.isoformat(),
            deleted=deleted,
        )
        
        return {
            "status": "success",
            "days": days,
            "cutoff_date": cutoff_date.isoformat(),
            "deleted": deleted,
        }
    
    await engine.dispose()


async def main():
    parser = argparse.ArgumentParser(description="清理过期的 embedding_usage 记录")
    parser.add_argument("--days", type=int, default=30, help="保留天数（默认 30）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不删除")
    
    args = parser.parse_args()
    
    print(f"\n🧹 Embedding Usage 数据清理")
    print(f"   保留天数: {args.days}")
    print(f"   模式: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()
    
    result = await cleanup_embedding_usage(
        days=args.days,
        dry_run=args.dry_run,
    )
    
    if args.dry_run:
        print(f"📊 待删除记录: {result['records_to_delete']}")
        print(f"   截止日期: {result['cutoff_date']}")
    else:
        print(f"✅ 已删除记录: {result['deleted']}")
        print(f"   截止日期: {result['cutoff_date']}")


if __name__ == "__main__":
    asyncio.run(main())
