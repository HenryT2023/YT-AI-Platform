"""
数据向量化脚本

将农耕知识、节气、NPC 人设、任务等内容向量化并存入 Qdrant。

Usage:
    python scripts/vectorize_data.py --collection knowledge
    python scripts/vectorize_data.py --collection all
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import async_session_factory
from app.database.models import (
    FarmingKnowledge,
    SolarTerm,
    Quest,
    Content,
)
from app.services.vector_store import VectorStore, get_vector_store
from app.core.logging import get_logger

logger = get_logger(__name__)


async def vectorize_farming_knowledge(
    session: AsyncSession,
    vector_store: VectorStore,
    tenant_id: str = "yantian",
    site_id: str = "main",
) -> int:
    """向量化农耕知识"""
    print("📚 开始向量化农耕知识...")

    result = await session.execute(
        select(FarmingKnowledge).where(
            FarmingKnowledge.tenant_id == tenant_id,
            FarmingKnowledge.site_id == site_id,
            FarmingKnowledge.is_active == True,
        )
    )
    items = result.scalars().all()

    if not items:
        print("  ⚠️ 没有找到农耕知识数据")
        return 0

    documents = []
    for item in items:
        # 组合内容
        content = f"{item.title}\n\n{item.content}"

        documents.append({
            "id": str(item.id),
            "content": content,
            "metadata": {
                "type": "farming_knowledge",
                "category": item.category,
                "solar_term_code": item.solar_term_code,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "title": item.title,
            },
        })

    count = await vector_store.upsert_batch("knowledge", documents)
    print(f"  ✅ 已向量化 {count} 条农耕知识")
    return count


async def vectorize_solar_terms(
    session: AsyncSession,
    vector_store: VectorStore,
) -> int:
    """向量化节气数据"""
    print("🌿 开始向量化节气数据...")

    result = await session.execute(select(SolarTerm))
    items = result.scalars().all()

    if not items:
        print("  ⚠️ 没有找到节气数据")
        return 0

    documents = []
    for item in items:
        # 组合内容：名称 + 描述 + 农耕建议 + 诗词
        parts = [f"节气：{item.name}"]

        if item.description:
            parts.append(f"简介：{item.description}")

        if item.farming_advice:
            parts.append(f"农耕建议：{item.farming_advice}")

        if item.cultural_customs:
            customs = item.cultural_customs.get("customs", [])
            foods = item.cultural_customs.get("foods", [])
            if customs:
                parts.append(f"习俗：{'、'.join(customs)}")
            if foods:
                parts.append(f"食俗：{'、'.join(foods)}")

        if item.poems:
            for poem in item.poems[:2]:
                parts.append(f"诗词：{poem.get('content', '')}")

        content = "\n".join(parts)

        documents.append({
            "id": f"solar_term_{item.code}",
            "content": content,
            "metadata": {
                "type": "solar_term",
                "code": item.code,
                "name": item.name,
                "order": item.order,
                "month": item.month,
            },
        })

    count = await vector_store.upsert_batch("knowledge", documents)
    print(f"  ✅ 已向量化 {count} 个节气")
    return count


async def vectorize_quests(
    session: AsyncSession,
    vector_store: VectorStore,
    tenant_id: str = "yantian",
    site_id: str = "main",
) -> int:
    """向量化任务数据"""
    print("🎯 开始向量化任务数据...")

    result = await session.execute(
        select(Quest).where(
            Quest.tenant_id == tenant_id,
            Quest.site_id == site_id,
            Quest.status == "active",
        )
    )
    items = result.scalars().all()

    if not items:
        print("  ⚠️ 没有找到任务数据")
        return 0

    documents = []
    for item in items:
        # 组合内容
        parts = [f"任务：{item.display_name or item.name}"]

        if item.description:
            parts.append(f"描述：{item.description}")

        if item.tags:
            parts.append(f"标签：{'、'.join(item.tags)}")

        content = "\n".join(parts)

        documents.append({
            "id": str(item.id),
            "content": content,
            "metadata": {
                "type": "quest",
                "quest_type": item.quest_type,
                "category": item.category,
                "difficulty": item.difficulty,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "title": item.display_name or item.name,
            },
        })

    count = await vector_store.upsert_batch("quest_content", documents)
    print(f"  ✅ 已向量化 {count} 个任务")
    return count


async def vectorize_contents(
    session: AsyncSession,
    vector_store: VectorStore,
    tenant_id: str = "yantian",
    site_id: str = "main",
) -> int:
    """向量化文化内容"""
    print("📖 开始向量化文化内容...")

    result = await session.execute(
        select(Content).where(
            Content.tenant_id == tenant_id,
            Content.site_id == site_id,
            Content.status == "published",
        )
    )
    items = result.scalars().all()

    if not items:
        print("  ⚠️ 没有找到文化内容数据")
        return 0

    documents = []
    for item in items:
        # 组合内容
        content = f"{item.title}\n\n{item.body or ''}"

        documents.append({
            "id": str(item.id),
            "content": content[:2000],  # 限制长度
            "metadata": {
                "type": "content",
                "content_type": item.content_type,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "title": item.title,
            },
        })

    count = await vector_store.upsert_batch("knowledge", documents)
    print(f"  ✅ 已向量化 {count} 条文化内容")
    return count


async def init_collections(vector_store: VectorStore):
    """初始化所有 Collections"""
    print("🔧 初始化向量数据库 Collections...")

    collections = ["knowledge", "npc_persona", "quest_content"]
    for name in collections:
        success = await vector_store.create_collection(name)
        if success:
            print(f"  ✅ Collection '{name}' 已就绪")
        else:
            print(f"  ❌ Collection '{name}' 创建失败")


async def main(collection: str, tenant_id: str, site_id: str):
    """主函数"""
    print("=" * 50)
    print("🚀 严田 AI - 数据向量化工具")
    print("=" * 50)

    vector_store = get_vector_store()

    # 健康检查
    if not await vector_store.health_check():
        print("❌ 无法连接到 Qdrant，请确保服务已启动")
        print("   运行: docker-compose up -d qdrant")
        return

    print("✅ Qdrant 连接成功")

    # 初始化 Collections
    await init_collections(vector_store)

    async with async_session_factory() as session:
        total = 0

        if collection in ["knowledge", "all"]:
            total += await vectorize_farming_knowledge(session, vector_store, tenant_id, site_id)
            total += await vectorize_solar_terms(session, vector_store)
            total += await vectorize_contents(session, vector_store, tenant_id, site_id)

        if collection in ["quest", "quest_content", "all"]:
            total += await vectorize_quests(session, vector_store, tenant_id, site_id)

        print("=" * 50)
        print(f"🎉 向量化完成！共处理 {total} 条数据")

        # 显示 Collection 统计
        print("\n📊 Collection 统计：")
        for name in ["knowledge", "quest_content"]:
            info = await vector_store.get_collection_info(name)
            if info:
                print(f"  - {name}: {info['points_count']} 条向量")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据向量化工具")
    parser.add_argument(
        "--collection",
        type=str,
        default="all",
        choices=["knowledge", "quest", "all"],
        help="要向量化的 Collection",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="yantian",
        help="租户 ID",
    )
    parser.add_argument(
        "--site-id",
        type=str,
        default="main",
        help="站点 ID",
    )

    args = parser.parse_args()

    asyncio.run(main(args.collection, args.tenant_id, args.site_id))
