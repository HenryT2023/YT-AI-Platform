#!/usr/bin/env python3
"""
生成测试 Evidence 数据

用于验证向量同步功能
"""

import asyncio
import os
import sys
from uuid import uuid4

sys.path.insert(0, "/Users/hal/YT-AI-Platform/services/core-backend")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://yantian:{os.environ.get('POSTGRES_PASSWORD', 'yantian_dev_password')}@localhost:5432/yantian"
)

# 严田相关的测试数据
TEST_EVIDENCES = [
    {
        "source_type": "knowledge_base",
        "title": "严氏宗祠历史",
        "excerpt": "严氏宗祠始建于明朝嘉靖年间，距今已有近500年历史。宗祠坐北朝南，三进两天井，是典型的徽派建筑风格。祠堂内保存有多块明清时期的匾额和楹联，记录了严氏家族的兴衰历程。",
        "confidence": 0.95,
        "verified": True,
        "tags": ["宗祠", "历史", "建筑"],
        "domains": ["文化遗产", "家族史"],
    },
    {
        "source_type": "oral_history",
        "title": "严田村名由来",
        "excerpt": "相传严田村因严姓先祖在此开垦田地而得名。明朝初年，严氏先祖从江西婺源迁徙至此，见此地山清水秀、土地肥沃，遂定居于此，世代耕读传家。",
        "confidence": 0.8,
        "verified": False,
        "tags": ["村史", "传说", "迁徙"],
        "domains": ["地方史", "家族史"],
    },
    {
        "source_type": "document",
        "title": "严田古樟树",
        "excerpt": "村口的古樟树已有800多年树龄，树干需要六人合抱。据村志记载，此树为严氏先祖迁居时所植，被村民视为风水树和守护神。每年春节，村民都会在树下举行祭祀活动。",
        "confidence": 0.9,
        "verified": True,
        "tags": ["古树", "风水", "民俗"],
        "domains": ["自然遗产", "民俗文化"],
    },
    {
        "source_type": "knowledge_base",
        "title": "严田油菜花节",
        "excerpt": "每年三月，严田村的油菜花田金黄一片，吸引大量游客前来观赏。油菜花节期间，村民会举办农耕体验、民俗表演等活动，展示传统农耕文化。",
        "confidence": 0.95,
        "verified": True,
        "tags": ["节庆", "油菜花", "旅游"],
        "domains": ["农耕文化", "乡村旅游"],
    },
    {
        "source_type": "genealogy",
        "title": "严氏家训",
        "excerpt": "严氏家训共十二条，强调耕读传家、孝悌忠信。其中「读书明理、勤俭持家」被视为核心要义，历代严氏子孙皆以此为行为准则。",
        "confidence": 0.85,
        "verified": True,
        "tags": ["家训", "家风", "教育"],
        "domains": ["家族文化", "传统教育"],
    },
    {
        "source_type": "archive",
        "title": "严田水利工程",
        "excerpt": "清朝乾隆年间，严氏族人集资修建了灌溉水渠，全长约3公里，至今仍在使用。这条水渠采用了独特的分水技术，确保上下游农田都能得到充足的灌溉。",
        "confidence": 0.9,
        "verified": True,
        "tags": ["水利", "农业", "工程"],
        "domains": ["农耕文化", "水利史"],
    },
    {
        "source_type": "oral_history",
        "title": "严田豆腐制作",
        "excerpt": "严田豆腐以本地山泉水和自种黄豆制作，口感细腻、豆香浓郁。传统制作工艺包括浸泡、磨浆、煮浆、点卤、压制等步骤，需要经验丰富的师傅才能做出上等豆腐。",
        "confidence": 0.85,
        "verified": False,
        "tags": ["美食", "手工艺", "传统"],
        "domains": ["饮食文化", "非遗"],
    },
    {
        "source_type": "document",
        "title": "严田古道",
        "excerpt": "严田古道是古代徽商往来的重要通道，全长约15公里，沿途设有多处凉亭和茶寮。古道上保存有多处明清时期的石刻和碑记，记录了当年商旅往来的繁忙景象。",
        "confidence": 0.9,
        "verified": True,
        "tags": ["古道", "徽商", "交通"],
        "domains": ["商业史", "交通史"],
    },
    {
        "source_type": "knowledge_base",
        "title": "严田民居建筑",
        "excerpt": "严田村保存有大量明清时期的民居建筑，以马头墙、天井、木雕为特色。其中「大夫第」是保存最完整的一座，建于清朝道光年间，占地约800平方米。",
        "confidence": 0.95,
        "verified": True,
        "tags": ["建筑", "民居", "文物"],
        "domains": ["建筑文化", "文化遗产"],
    },
    {
        "source_type": "oral_history",
        "title": "严田龙灯会",
        "excerpt": "每年正月十五，严田村都会举办盛大的龙灯会。龙灯由村中青壮年舞动，从村头舞到村尾，寓意驱邪祈福、风调雨顺。这一传统已延续了三百多年。",
        "confidence": 0.8,
        "verified": False,
        "tags": ["民俗", "节庆", "龙灯"],
        "domains": ["民俗文化", "非遗"],
    },
]


async def seed_evidences():
    """插入测试数据"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. 确保 tenant 存在
        result = await session.execute(
            text("SELECT id FROM tenants WHERE id = 'yantian'")
        )
        if not result.scalar():
            await session.execute(
                text("""
                    INSERT INTO tenants (id, name, status)
                    VALUES ('yantian', '严田文旅', 'active')
                """)
            )
            print("  ✓ 创建 tenant: yantian")

        # 2. 确保 site 存在
        result = await session.execute(
            text("SELECT id FROM sites WHERE id = 'yantian-main'")
        )
        if not result.scalar():
            await session.execute(
                text("""
                    INSERT INTO sites (id, tenant_id, name, status)
                    VALUES ('yantian-main', 'yantian', '严田主站', 'active')
                """)
            )
            print("  ✓ 创建 site: yantian-main")

        await session.commit()

        # 3. 检查是否已有 evidence 数据
        result = await session.execute(
            text("SELECT COUNT(*) FROM evidences WHERE tenant_id = 'yantian'")
        )
        count = result.scalar()
        if count > 0:
            print(f"⚠️  已存在 {count} 条 evidence 数据，跳过插入")
            return count

        # 插入测试数据
        for i, ev in enumerate(TEST_EVIDENCES):
            evidence_id = str(uuid4())
            await session.execute(
                text("""
                    INSERT INTO evidences (
                        id, tenant_id, site_id, source_type, title, excerpt,
                        confidence, verified, tags, domains, status
                    ) VALUES (
                        :id, :tenant_id, :site_id, :source_type, :title, :excerpt,
                        :confidence, :verified, :tags, :domains, :status
                    )
                """),
                {
                    "id": evidence_id,
                    "tenant_id": "yantian",
                    "site_id": "yantian-main",
                    "source_type": ev["source_type"],
                    "title": ev["title"],
                    "excerpt": ev["excerpt"],
                    "confidence": ev["confidence"],
                    "verified": ev["verified"],
                    "tags": ev["tags"],
                    "domains": ev["domains"],
                    "status": "active",
                },
            )
            print(f"  ✓ [{i+1}/{len(TEST_EVIDENCES)}] {ev['title']}")

        await session.commit()
        print(f"\n✅ 成功插入 {len(TEST_EVIDENCES)} 条测试 evidence")

    await engine.dispose()
    return len(TEST_EVIDENCES)


if __name__ == "__main__":
    print("🌱 开始生成测试 Evidence 数据...\n")
    asyncio.run(seed_evidences())
