#!/usr/bin/env python3
"""
数据库种子数据导入脚本

用法：
    python scripts/seed_db.py                    # 导入默认种子数据
    python scripts/seed_db.py --file seeds.json  # 导入指定文件
    python scripts/seed_db.py --reset            # 清空并重新导入
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database.engine import async_session_maker
from app.core.security import get_password_hash


async def seed_tenant(session, data: dict) -> str:
    """导入租户"""
    await session.execute(
        text("""
            INSERT INTO tenants (id, name, display_name, description, plan, status)
            VALUES (:id, :name, :display_name, :description, :plan, 'active')
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                plan = EXCLUDED.plan,
                updated_at = NOW()
        """),
        {
            "id": data["id"],
            "name": data["name"],
            "display_name": data.get("display_name"),
            "description": data.get("description"),
            "plan": data.get("plan", "free"),
        },
    )
    print(f"  ✅ Tenant: {data['id']}")
    return data["id"]


async def seed_site(session, tenant_id: str, data: dict) -> str:
    """导入站点"""
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
            "id": data["id"],
            "tenant_id": tenant_id,
            "name": data["name"],
            "display_name": data.get("display_name"),
            "description": data.get("description"),
            "config": json.dumps(data.get("config", {})),
            "theme": json.dumps(data.get("theme", {})),
            "location_lat": data.get("location_lat"),
            "location_lng": data.get("location_lng"),
            "timezone": data.get("timezone", "Asia/Shanghai"),
        },
    )
    print(f"  ✅ Site: {data['id']}")
    return data["id"]


async def seed_user(session, tenant_id: str, data: dict) -> None:
    """导入用户"""
    hashed_password = get_password_hash(data.get("password", "password123"))
    await session.execute(
        text("""
            INSERT INTO users (tenant_id, username, email, display_name, 
                               hashed_password, role, is_active, status)
            VALUES (:tenant_id, :username, :email, :display_name,
                    :hashed_password, :role, true, 'active')
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                role = EXCLUDED.role,
                updated_at = NOW()
        """),
        {
            "tenant_id": tenant_id,
            "username": data["username"],
            "email": data.get("email"),
            "display_name": data.get("display_name"),
            "hashed_password": hashed_password,
            "role": data.get("role", "operator"),
        },
    )
    print(f"  ✅ User: {data['username']} ({data.get('role', 'operator')})")


async def seed_npc_profile(session, tenant_id: str, site_id: str, data: dict) -> None:
    """导入 NPC 人设"""
    persona = data.get("persona", {})
    await session.execute(
        text("""
            INSERT INTO npc_profiles (
                tenant_id, site_id, npc_id, version, active,
                name, display_name, npc_type, persona,
                era, role, background,
                personality_traits, speaking_style, tone, catchphrases,
                knowledge_domains, greeting_templates, fallback_responses,
                max_response_length, forbidden_topics, must_cite_sources, time_awareness,
                status
            ) VALUES (
                :tenant_id, :site_id, :npc_id, 1, true,
                :name, :display_name, :npc_type, :persona::jsonb,
                :era, :role, :background,
                :personality_traits, :speaking_style, :tone, :catchphrases,
                :knowledge_domains, :greeting_templates, :fallback_responses,
                :max_response_length, :forbidden_topics, :must_cite_sources, :time_awareness,
                'active'
            )
            ON CONFLICT (npc_id, version) DO UPDATE SET
                name = EXCLUDED.name,
                display_name = EXCLUDED.display_name,
                persona = EXCLUDED.persona,
                updated_at = NOW()
        """),
        {
            "tenant_id": tenant_id,
            "site_id": site_id,
            "npc_id": data["npc_id"],
            "name": data["name"],
            "display_name": data.get("display_name"),
            "npc_type": data.get("npc_type"),
            "persona": json.dumps(persona),
            "era": persona.get("identity", {}).get("era"),
            "role": persona.get("identity", {}).get("role"),
            "background": persona.get("identity", {}).get("background"),
            "personality_traits": persona.get("personality", {}).get("traits", []),
            "speaking_style": persona.get("personality", {}).get("speaking_style"),
            "tone": persona.get("personality", {}).get("tone"),
            "catchphrases": persona.get("personality", {}).get("catchphrases", []),
            "knowledge_domains": persona.get("knowledge_domains", []),
            "greeting_templates": persona.get("conversation_config", {}).get("greeting_templates", []),
            "fallback_responses": persona.get("conversation_config", {}).get("fallback_responses", []),
            "max_response_length": persona.get("conversation_config", {}).get("max_response_length", 500),
            "forbidden_topics": persona.get("constraints", {}).get("forbidden_topics", []),
            "must_cite_sources": persona.get("constraints", {}).get("must_cite_sources", True),
            "time_awareness": persona.get("constraints", {}).get("time_awareness"),
        },
    )
    print(f"  ✅ NPC: {data['npc_id']} ({data['name']})")


async def seed_content(session, tenant_id: str, site_id: str, data: dict) -> None:
    """导入内容"""
    await session.execute(
        text("""
            INSERT INTO contents (
                tenant_id, site_id, content_type,
                title, summary, body,
                category, tags, domains,
                source, credibility_score, verified,
                status
            ) VALUES (
                :tenant_id, :site_id, :content_type,
                :title, :summary, :body,
                :category, :tags, :domains,
                :source, :credibility_score, :verified,
                'published'
            )
        """),
        {
            "tenant_id": tenant_id,
            "site_id": site_id,
            "content_type": data.get("content_type", "knowledge"),
            "title": data["title"],
            "summary": data.get("summary"),
            "body": data["body"],
            "category": data.get("category"),
            "tags": data.get("tags", []),
            "domains": data.get("domains", []),
            "source": data.get("source"),
            "credibility_score": data.get("credibility_score", 1.0),
            "verified": data.get("verified", False),
        },
    )
    print(f"  ✅ Content: {data['title'][:40]}...")


async def seed_evidence(session, tenant_id: str, site_id: str, data: dict) -> None:
    """导入证据"""
    await session.execute(
        text("""
            INSERT INTO evidences (
                tenant_id, site_id, source_type, source_ref,
                title, excerpt, confidence,
                tags, domains, verified, status
            ) VALUES (
                :tenant_id, :site_id, :source_type, :source_ref,
                :title, :excerpt, :confidence,
                :tags, :domains, :verified, 'active'
            )
        """),
        {
            "tenant_id": tenant_id,
            "site_id": site_id,
            "source_type": data.get("source_type", "knowledge_base"),
            "source_ref": data.get("source_ref"),
            "title": data.get("title"),
            "excerpt": data["excerpt"],
            "confidence": data.get("confidence", 1.0),
            "tags": data.get("tags", []),
            "domains": data.get("domains", []),
            "verified": data.get("verified", False),
        },
    )
    print(f"  ✅ Evidence: {data.get('title', data['excerpt'][:30])}...")


async def reset_database(session) -> None:
    """清空所有数据（保留表结构）"""
    tables = [
        "user_feedbacks", "trace_ledger", "messages", "conversations",
        "evidences", "quest_steps", "quests", "npc_profiles", "contents",
        "users", "sites", "tenants"
    ]
    for table in tables:
        await session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    print("🗑️  All tables truncated")


async def seed_all(seed_file: Path, reset: bool = False) -> None:
    """执行完整的种子数据导入"""
    print(f"📦 Loading seed data from: {seed_file}")

    with open(seed_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session_maker() as session:
        try:
            if reset:
                await reset_database(session)

            # 1. 导入租户
            print("\n📁 Importing tenants...")
            tenant_data = data.get("tenant", {"id": "yantian", "name": "严田"})
            tenant_id = await seed_tenant(session, tenant_data)

            # 2. 导入站点
            print("\n📍 Importing sites...")
            site_data = data.get("site", {})
            if site_data:
                site_id = await seed_site(session, tenant_id, site_data)
            else:
                site_id = f"{tenant_id}-main"

            # 3. 导入用户
            print("\n👤 Importing users...")
            users = data.get("users", [
                {"username": "admin", "password": "admin123", "role": "super_admin", "display_name": "管理员"}
            ])
            for user in users:
                await seed_user(session, tenant_id, user)

            # 4. 导入 NPC
            print("\n🎭 Importing NPCs...")
            npcs = data.get("npcs", [])
            for npc in npcs:
                await seed_npc_profile(session, tenant_id, site_id, npc)

            # 5. 导入内容
            print("\n📝 Importing contents...")
            contents = data.get("contents", [])
            for content in contents:
                await seed_content(session, tenant_id, site_id, content)

            # 6. 导入证据
            print("\n🔍 Importing evidences...")
            evidences = data.get("evidences", [])
            for evidence in evidences:
                await seed_evidence(session, tenant_id, site_id, evidence)

            await session.commit()
            print("\n✅ All seed data imported successfully!")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(description="Database seed script")
    parser.add_argument(
        "--file", "-f",
        type=str,
        default="seeds/v0.1.0.json",
        help="Seed data file path (relative to data/ directory)",
    )
    parser.add_argument(
        "--reset", "-r",
        action="store_true",
        help="Reset database before seeding",
    )
    args = parser.parse_args()

    # 确定种子文件路径
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    seed_file = data_dir / args.file

    if not seed_file.exists():
        print(f"❌ Seed file not found: {seed_file}")
        sys.exit(1)

    asyncio.run(seed_all(seed_file, args.reset))


if __name__ == "__main__":
    main()
