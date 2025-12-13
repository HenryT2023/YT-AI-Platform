#!/usr/bin/env python3
"""
开发环境种子数据导入脚本

从 data/seeds/ 目录读取 JSON 文件，导入到数据库
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


async def load_seed_data(seed_file: Path) -> dict:
    """加载种子数据文件"""
    with open(seed_file, "r", encoding="utf-8") as f:
        return json.load(f)


async def seed_site(data: dict) -> None:
    """导入站点数据"""
    async with async_session_maker() as session:
        site_data = data.get("site", {})
        if not site_data:
            print("No site data found")
            return

        # 插入站点
        await session.execute(
            text("""
                INSERT INTO sites (id, name, display_name, description, config, theme, 
                                   location_lat, location_lng, timezone, status)
                VALUES (:id, :name, :display_name, :description, :config::jsonb, :theme::jsonb,
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
