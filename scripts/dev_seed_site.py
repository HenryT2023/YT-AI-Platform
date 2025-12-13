#!/usr/bin/env python3
"""
开发环境种子数据导入脚本

从 data/seeds/ 目录读取 JSON 文件，导入到数据库
支持：租户、站点、场景、NPC、知识条目、用户
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "core-backend"))

from sqlalchemy import text
from app.db.session import async_session_maker
from app.core.security import get_password_hash


async def load_seed_data(seed_file: Path) -> dict:
    """加载种子数据文件"""
    with open(seed_file, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed_tenant(session, tenant_data: dict) -> None:
    """导入租户数据"""
    await session.execute(
        text("""
            INSERT INTO tenants (id, name, display_name, description, plan, status)
            VALUES (:id, :name, :display_name, :description, :plan, 'active')
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                updated_at = NOW()
        """),
        {
            "id": tenant_data["id"],
            "name": tenant_data["name"],
            "display_name": tenant_data.get("display_name"),
            "description": tenant_data.get("description"),
            "plan": tenant_data.get("plan", "free"),
        },
    )
    print(f"✅ Tenant '{tenant_data['id']}' imported")


async def seed_admin_user(session, tenant_id: str, user_data: dict) -> None:
    """导入管理员用户"""
    hashed_password = get_password_hash(user_data.get("password", "admin123"))
    await session.execute(
        text("""
            INSERT INTO users (id, tenant_id, username, email, display_name, 
                               hashed_password, role, is_active, status)
            VALUES (gen_random_uuid(), :tenant_id, :username, :email, :display_name,
                    :hashed_password, :role, true, 'active')
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                role = EXCLUDED.role,
                updated_at = NOW()
        """),
        {
            "tenant_id": tenant_id,
            "username": user_data["username"],
            "email": user_data.get("email"),
            "display_name": user_data.get("display_name"),
            "hashed_password": hashed_password,
            "role": user_data.get("role", "tenant_admin"),
        },
    )
    print(f"✅ User '{user_data['username']}' imported")


async def seed_site(data: dict) -> None:
    """导入站点数据"""
    async with async_session_maker() as session:
        # 先导入租户
        tenant_data = data.get("tenant", {"id": "yantian", "name": "严田"})
        await seed_tenant(session, tenant_data)

        # 导入管理员用户
        admin_users = data.get("users", [
            {"username": "admin", "password": "admin123", "role": "super_admin", "display_name": "超级管理员"}
        ])
        for user in admin_users:
            await seed_admin_user(session, tenant_data["id"], user)

        site_data = data.get("site", {})
        if not site_data:
            print("No site data found")
            await session.commit()
            return

        # 插入站点（包含 tenant_id）
        await session.execute(
            text("""
                INSERT INTO sites (id, tenant_id, name, display_name, description, config, theme, 
                                   location_lat, location_lng, timezone, status)
                VALUES (:id, :tenant_id, :name, :display_name, :description, :config::jsonb, :theme::jsonb,
                        :location_lat, :location_lng, :timezone, 'active')
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    config = EXCLUDED.config,
                    theme = EXCLUDED.theme,
                    updated_at = NOW()
            """),
            {
                "id": site_data["id"],
                "tenant_id": tenant_data["id"],
                "name": site_data["name"],
                "display_name": site_data.get("display_name"),
                "description": site_data.get("description"),
                "config": json.dumps(site_data.get("config", {})),
                "theme": json.dumps(site_data.get("theme", {})),
                "location_lat": site_data.get("location_lat"),
                "location_lng": site_data.get("location_lng"),
                "timezone": site_data.get("timezone", "Asia/Shanghai"),
            },
        )
        print(f"✅ Site '{site_data['id']}' imported")

        # 插入场景
        scenes = data.get("scenes", [])
        scene_id_map = {}
        for scene in scenes:
            scene_id = str(uuid4())
            scene_id_map[scene["name"]] = scene_id
            await session.execute(
                text("""
                    INSERT INTO scenes (id, site_id, name, display_name, description, 
                                        scene_type, sort_order, status)
                    VALUES (:id, :site_id, :name, :display_name, :description,
                            :scene_type, :sort_order, 'active')
                """),
                {
                    "id": scene_id,
                    "site_id": site_data["id"],
                    "name": scene["name"],
                    "display_name": scene.get("display_name"),
                    "description": scene.get("description"),
                    "scene_type": scene.get("scene_type"),
                    "sort_order": scene.get("sort_order", 0),
                },
            )
        print(f"✅ {len(scenes)} scenes imported")

        # 插入 NPC
        npcs = data.get("npcs", [])
        for npc in npcs:
            npc_id = str(uuid4())
            await session.execute(
                text("""
                    INSERT INTO npcs (id, site_id, name, display_name, npc_type, 
                                      persona, status)
                    VALUES (:id, :site_id, :name, :display_name, :npc_type,
                            :persona::jsonb, 'active')
                """),
                {
                    "id": npc_id,
                    "site_id": site_data["id"],
                    "name": npc["name"],
                    "display_name": npc.get("display_name"),
                    "npc_type": npc.get("npc_type"),
                    "persona": json.dumps(npc.get("persona", {})),
                },
            )
        print(f"✅ {len(npcs)} NPCs imported")

        # 插入知识条目
        knowledge_entries = data.get("knowledge", [])
        for entry in knowledge_entries:
            entry_id = str(uuid4())
            await session.execute(
                text("""
                    INSERT INTO knowledge_entries (id, tenant_id, site_id, title, content, 
                                                   summary, knowledge_type, domains, tags,
                                                   source, credibility_score, verified, status)
                    VALUES (:id, :tenant_id, :site_id, :title, :content,
                            :summary, :knowledge_type, :domains, :tags,
                            :source, :credibility_score, :verified, 'active')
                """),
                {
                    "id": entry_id,
                    "tenant_id": tenant_data["id"],
                    "site_id": site_data["id"],
                    "title": entry["title"],
                    "content": entry["content"],
                    "summary": entry.get("summary"),
                    "knowledge_type": entry.get("knowledge_type", "other"),
                    "domains": entry.get("domains", []),
                    "tags": entry.get("tags", []),
                    "source": entry.get("source"),
                    "credibility_score": entry.get("credibility_score", 1.0),
                    "verified": entry.get("verified", False),
                },
            )
        print(f"✅ {len(knowledge_entries)} knowledge entries imported")

        await session.commit()
        print("✅ All seed data imported successfully!")


async def main():
    """主函数"""
    seed_dir = Path(__file__).parent.parent / "data" / "seeds"
    
    # 默认导入 yantian-main.json
    seed_file = seed_dir / "yantian-main.json"
    
    if len(sys.argv) > 1:
        seed_file = seed_dir / sys.argv[1]
    
    if not seed_file.exists():
        print(f"❌ Seed file not found: {seed_file}")
        sys.exit(1)
    
    print(f"📦 Loading seed data from: {seed_file}")
    data = await load_seed_data(seed_file)
    await seed_site(data)


if __name__ == "__main__":
    asyncio.run(main())
