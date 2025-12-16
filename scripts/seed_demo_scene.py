#!/usr/bin/env python3
"""
P0.5 Demo 场景数据 Seed 脚本

功能：
- 插入 3 个 NPC
- 插入 5 个 POI
- 插入 3 个 Quest

特性：
- 幂等：可重复运行，按 npc_id / poi_id / quest_id 覆盖
- 固定 tenant_id / site_id: yantian / yantian-main

使用方法：
    python scripts/seed_demo_scene.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# 添加 core-backend 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "core-backend"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 配置
TENANT_ID = "yantian"
SITE_ID = "yantian-main"
DATABASE_URL = "postgresql+asyncpg://yantian:yantian_dev_password@localhost:5432/yantian"

# ============================================================
# Demo 数据定义
# ============================================================

DEMO_NPCS = [
    {
        "npc_id": "npc_elder_chen",
        "name": "陈老伯",
        "display_name": "陈老伯",
        "role": "村中长者",
        "npc_type": "elder",
        "avatar_url": "/avatars/chen.png",
        "era": "当代",
        "background": "严田村的老一辈，见证了村庄的变迁，熟知各种传统习俗和历史故事。在村里生活了七十多年。",
        "personality_traits": ["慈祥", "健谈", "博学"],
        "speaking_style": "温和、富有智慧，喜欢引用古语",
        "tone": "温和",
        "knowledge_domains": ["村史", "家训", "传统习俗", "老建筑"],
        "greeting_templates": [
            "年轻人，欢迎来到严田村。我在这里生活了七十多年，有什么想知道的尽管问。"
        ],
        "fallback_responses": [
            "这个问题我得好好想想，你可以问问别人。",
            "老朽年纪大了，有些事记不太清了。"
        ],
        "extra": {
            "color": "from-amber-500 to-orange-600",
            "avatar_emoji": "👴",
            "intro": "熟悉严田村历史的长者，见证了村庄七十年变迁"
        }
    },
    {
        "npc_id": "npc_xiaomei",
        "name": "小美",
        "display_name": "小美",
        "role": "返乡创业青年",
        "npc_type": "youth",
        "avatar_url": "/avatars/xiaomei.png",
        "era": "当代",
        "background": "从城市回到家乡的年轻人，正在用新技术帮助村民发展智慧农业。去年刚从城里回来。",
        "personality_traits": ["活泼", "热情", "创新"],
        "speaking_style": "年轻活泼，偶尔用网络用语",
        "tone": "活泼",
        "knowledge_domains": ["智慧农业", "电商", "新农村建设", "年轻人视角"],
        "greeting_templates": [
            "嗨！我是小美，去年从城里回来帮村里搞智慧农业。你对我们的项目感兴趣吗？"
        ],
        "fallback_responses": [
            "这个我还在学习中，要不你问问陈老伯？",
            "哈哈，这个问题有点难住我了。"
        ],
        "extra": {
            "color": "from-pink-500 to-rose-600",
            "avatar_emoji": "👩",
            "intro": "从城市回到家乡的年轻人，用新技术帮助村民发展农业"
        }
    },
    {
        "npc_id": "npc_master_li",
        "name": "李师傅",
        "display_name": "李师傅",
        "role": "非遗传承人",
        "npc_type": "craftsman",
        "avatar_url": "/avatars/li.png",
        "era": "当代",
        "background": "传统手工艺的守护者，精通竹编、木雕等多项非遗技艺。从祖辈那里学来的手艺，已经传承了三代。",
        "personality_traits": ["专注", "严谨", "朴实"],
        "speaking_style": "朴实无华，说话直接",
        "tone": "朴实",
        "knowledge_domains": ["竹编", "木雕", "非遗技艺", "传统工艺"],
        "greeting_templates": [
            "欢迎来到我的工坊。这些竹编和木雕都是祖辈传下来的手艺，你想了解哪一样？"
        ],
        "fallback_responses": [
            "这个我不太懂，我只会做手艺活。",
            "手艺人嘛，别的事不太清楚。"
        ],
        "extra": {
            "color": "from-emerald-500 to-teal-600",
            "avatar_emoji": "👨‍🔧",
            "intro": "传统手工艺的守护者，精通竹编、木雕等多项非遗技艺"
        }
    },
]

DEMO_POIS = [
    {
        "poi_id": "poi_ancestral_hall",
        "name": "严氏宗祠",
        "description": "严田村最重要的文化建筑，始建于明代，是严氏家族祭祀祖先的场所。",
        "category": "历史建筑",
        "tags": ["宗族", "历史", "建筑"],
        "extra": {
            "location": "村中心",
            "open_hours": "8:00-17:00",
            "highlight": "明代建筑风格，保存完好"
        }
    },
    {
        "poi_id": "poi_old_well",
        "name": "古井",
        "description": "村中百年古井，至今仍有清泉涌出，是村民日常取水的地方。",
        "category": "历史遗迹",
        "tags": ["历史", "生活", "水源"],
        "extra": {
            "location": "村东",
            "age": "约200年",
            "highlight": "清泉甘甜，四季不竭"
        }
    },
    {
        "poi_id": "poi_bamboo_workshop",
        "name": "竹编工坊",
        "description": "李师傅的竹编工坊，展示和传授传统竹编技艺。",
        "category": "非遗工坊",
        "tags": ["非遗", "手工艺", "体验"],
        "extra": {
            "location": "村西",
            "master": "李师傅",
            "highlight": "可体验竹编制作"
        }
    },
    {
        "poi_id": "poi_smart_farm",
        "name": "智慧农场",
        "description": "小美创办的智慧农业示范基地，展示现代农业技术。",
        "category": "现代农业",
        "tags": ["农业", "科技", "创新"],
        "extra": {
            "location": "村北",
            "founder": "小美",
            "highlight": "物联网监控、无人机巡田"
        }
    },
    {
        "poi_id": "poi_village_gate",
        "name": "村口牌坊",
        "description": "严田村的标志性建筑，刻有\"严田\"二字，是进村的第一道风景。",
        "category": "地标建筑",
        "tags": ["地标", "入口", "建筑"],
        "extra": {
            "location": "村口",
            "age": "清代重建",
            "highlight": "村庄标志，拍照打卡点"
        }
    },
]

DEMO_QUESTS = [
    {
        "quest_id": "quest_family_rules",
        "name": "认祖归宗",
        "display_name": "认祖归宗：家训三问",
        "description": "了解严氏家训的核心精神，感受传统文化的智慧。",
        "quest_type": "dialogue",
        "category": "文化探索",
        "difficulty": "easy",
        "estimated_duration_minutes": 15,
        "tags": ["家训", "文化", "对话"],
        "rewards": {
            "badge": "家训徽章",
            "points": 100
        },
        "steps": [
            {"step_number": 1, "name": "询问家训", "description": "向陈老伯询问严氏家训", "step_type": "dialogue", "target_config": {"npc_id": "npc_elder_chen", "topic": "家训"}},
            {"step_number": 2, "name": "找出核心", "description": "找出家训中最重要的一条", "step_type": "quiz", "target_config": {"question": "家训核心"}},
            {"step_number": 3, "name": "现代意义", "description": "思考其现代意义", "step_type": "reflection", "target_config": {"topic": "现代意义"}},
        ]
    },
    {
        "quest_id": "quest_craftsman",
        "name": "匠心传承",
        "display_name": "匠心传承：非遗体验",
        "description": "跟随李师傅学习传统竹编技艺，感受匠人精神。",
        "quest_type": "experience",
        "category": "非遗体验",
        "difficulty": "medium",
        "estimated_duration_minutes": 30,
        "tags": ["非遗", "手工艺", "体验"],
        "rewards": {
            "badge": "匠心徽章",
            "points": 200,
            "item": "竹编小作品"
        },
        "steps": [
            {"step_number": 1, "name": "拜访工坊", "description": "前往竹编工坊拜访李师傅", "step_type": "visit", "target_config": {"poi_id": "poi_bamboo_workshop"}},
            {"step_number": 2, "name": "了解历史", "description": "听李师傅讲述竹编的历史", "step_type": "dialogue", "target_config": {"npc_id": "npc_master_li", "topic": "竹编历史"}},
            {"step_number": 3, "name": "动手体验", "description": "亲手尝试编织一个简单的竹编", "step_type": "activity", "target_config": {"activity": "竹编体验"}},
        ]
    },
    {
        "quest_id": "quest_village_tour",
        "name": "村庄漫步",
        "display_name": "村庄漫步：发现严田",
        "description": "漫步严田村，探访主要景点，了解村庄全貌。",
        "quest_type": "exploration",
        "category": "探索游览",
        "difficulty": "easy",
        "estimated_duration_minutes": 45,
        "tags": ["探索", "游览", "打卡"],
        "rewards": {
            "badge": "探索者徽章",
            "points": 150
        },
        "steps": [
            {"step_number": 1, "name": "村口打卡", "description": "在村口牌坊拍照打卡", "step_type": "visit", "target_config": {"poi_id": "poi_village_gate"}},
            {"step_number": 2, "name": "参观宗祠", "description": "参观严氏宗祠", "step_type": "visit", "target_config": {"poi_id": "poi_ancestral_hall"}},
            {"step_number": 3, "name": "古井寻幽", "description": "探访百年古井", "step_type": "visit", "target_config": {"poi_id": "poi_old_well"}},
            {"step_number": 4, "name": "智慧农场", "description": "参观智慧农场", "step_type": "visit", "target_config": {"poi_id": "poi_smart_farm"}},
        ]
    },
]


# ============================================================
# Seed 函数
# ============================================================

async def seed_npcs(session: AsyncSession) -> int:
    """Seed NPC 数据"""
    from app.database.models.npc_profile import NPCProfile
    
    count = 0
    for npc_data in DEMO_NPCS:
        npc_id = npc_data["npc_id"]
        
        # 检查是否存在
        stmt = select(NPCProfile).where(
            NPCProfile.tenant_id == TENANT_ID,
            NPCProfile.site_id == SITE_ID,
            NPCProfile.npc_id == npc_id,
            NPCProfile.active == True,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新
            existing.name = npc_data["name"]
            existing.display_name = npc_data["display_name"]
            existing.role = npc_data["role"]
            existing.npc_type = npc_data["npc_type"]
            existing.avatar_url = npc_data["avatar_url"]
            existing.era = npc_data["era"]
            existing.background = npc_data["background"]
            existing.personality_traits = npc_data["personality_traits"]
            existing.speaking_style = npc_data["speaking_style"]
            existing.tone = npc_data["tone"]
            existing.knowledge_domains = npc_data["knowledge_domains"]
            existing.greeting_templates = npc_data["greeting_templates"]
            existing.fallback_responses = npc_data["fallback_responses"]
            existing.persona = {"extra": npc_data["extra"]}
            print(f"  ✓ 更新 NPC: {npc_id}")
        else:
            # 插入
            npc = NPCProfile(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                site_id=SITE_ID,
                npc_id=npc_id,
                version=1,
                active=True,
                name=npc_data["name"],
                display_name=npc_data["display_name"],
                role=npc_data["role"],
                npc_type=npc_data["npc_type"],
                avatar_url=npc_data["avatar_url"],
                era=npc_data["era"],
                background=npc_data["background"],
                personality_traits=npc_data["personality_traits"],
                speaking_style=npc_data["speaking_style"],
                tone=npc_data["tone"],
                knowledge_domains=npc_data["knowledge_domains"],
                greeting_templates=npc_data["greeting_templates"],
                fallback_responses=npc_data["fallback_responses"],
                persona={"extra": npc_data["extra"]},
            )
            session.add(npc)
            print(f"  + 新增 NPC: {npc_id}")
        count += 1
    
    return count


async def seed_pois(session: AsyncSession) -> int:
    """Seed POI 数据（使用 Content 表，type=poi）"""
    from app.database.models.content import Content
    
    count = 0
    for poi_data in DEMO_POIS:
        poi_id = poi_data["poi_id"]
        
        # 检查是否存在（通过 slug 匹配）
        stmt = select(Content).where(
            Content.tenant_id == TENANT_ID,
            Content.site_id == SITE_ID,
            Content.content_type == "poi",
            Content.slug == poi_id,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新
            existing.title = poi_data["name"]
            existing.summary = poi_data["description"]
            existing.body = poi_data["description"]
            existing.category = poi_data["category"]
            existing.tags = poi_data["tags"]
            existing.extra_data = poi_data["extra"]
            existing.status = "published"
            print(f"  ✓ 更新 POI: {poi_id}")
        else:
            # 插入
            poi = Content(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                site_id=SITE_ID,
                content_type="poi",
                slug=poi_id,
                title=poi_data["name"],
                summary=poi_data["description"],
                body=poi_data["description"],
                category=poi_data["category"],
                tags=poi_data["tags"],
                extra_data=poi_data["extra"],
                status="published",
                credibility_score=1.0,
            )
            session.add(poi)
            print(f"  + 新增 POI: {poi_id}")
        count += 1
    
    return count


async def seed_quests(session: AsyncSession) -> int:
    """Seed Quest 数据"""
    from app.database.models.quest import Quest, QuestStep
    
    count = 0
    for quest_data in DEMO_QUESTS:
        quest_id = quest_data["quest_id"]
        
        # 检查是否存在（通过 name 匹配）
        stmt = select(Quest).where(
            Quest.tenant_id == TENANT_ID,
            Quest.site_id == SITE_ID,
            Quest.name == quest_data["name"],
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新
            existing.display_name = quest_data["display_name"]
            existing.description = quest_data["description"]
            existing.quest_type = quest_data["quest_type"]
            existing.category = quest_data["category"]
            existing.difficulty = quest_data["difficulty"]
            existing.estimated_duration_minutes = quest_data["estimated_duration_minutes"]
            existing.tags = quest_data["tags"]
            existing.rewards = quest_data["rewards"]
            existing.config = {"quest_id": quest_id}
            existing.status = "active"
            
            # 删除旧步骤
            await session.execute(
                text("DELETE FROM quest_steps WHERE quest_id = :quest_id"),
                {"quest_id": existing.id}
            )
            
            # 添加新步骤
            for step_data in quest_data["steps"]:
                step = QuestStep(
                    id=str(uuid4()),
                    tenant_id=TENANT_ID,
                    site_id=SITE_ID,
                    quest_id=existing.id,
                    step_number=step_data["step_number"],
                    name=step_data["name"],
                    description=step_data["description"],
                    step_type=step_data["step_type"],
                    target_config=step_data["target_config"],
                )
                session.add(step)
            
            print(f"  ✓ 更新 Quest: {quest_id}")
        else:
            # 插入
            quest = Quest(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                site_id=SITE_ID,
                name=quest_data["name"],
                display_name=quest_data["display_name"],
                description=quest_data["description"],
                quest_type=quest_data["quest_type"],
                category=quest_data["category"],
                difficulty=quest_data["difficulty"],
                estimated_duration_minutes=quest_data["estimated_duration_minutes"],
                tags=quest_data["tags"],
                rewards=quest_data["rewards"],
                config={"quest_id": quest_id},
                status="active",
            )
            session.add(quest)
            await session.flush()  # 获取 quest.id
            
            # 添加步骤
            for step_data in quest_data["steps"]:
                step = QuestStep(
                    id=str(uuid4()),
                    tenant_id=TENANT_ID,
                    site_id=SITE_ID,
                    quest_id=quest.id,
                    step_number=step_data["step_number"],
                    name=step_data["name"],
                    description=step_data["description"],
                    step_type=step_data["step_type"],
                    target_config=step_data["target_config"],
                )
                session.add(step)
            
            print(f"  + 新增 Quest: {quest_id}")
        count += 1
    
    return count


async def main():
    """主函数"""
    print("=" * 60)
    print("P0.5 Demo 场景数据 Seed")
    print("=" * 60)
    print(f"Tenant: {TENANT_ID}")
    print(f"Site: {SITE_ID}")
    print()
    
    # 创建数据库连接
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Seed NPCs
            print("📦 Seeding NPCs...")
            npc_count = await seed_npcs(session)
            
            # Seed POIs
            print("\n📍 Seeding POIs...")
            poi_count = await seed_pois(session)
            
            # Seed Quests
            print("\n🎯 Seeding Quests...")
            quest_count = await seed_quests(session)
            
            # 提交
            await session.commit()
            
            print("\n" + "=" * 60)
            print("✅ Seed 完成!")
            print(f"  NPCs: {npc_count}")
            print(f"  POIs: {poi_count}")
            print(f"  Quests: {quest_count}")
            print("=" * 60)
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Seed 失败: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
