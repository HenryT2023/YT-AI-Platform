#!/usr/bin/env python3
"""
Prompt 导入脚本

从 data/prompts/ 目录导入 Prompt 到数据库
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database.engine import async_session_maker
from app.database.models import NPCPrompt
from app.core.config import settings


async def import_prompt(
    file_path: Path,
    tenant_id: str,
    site_id: str,
    force: bool = False,
) -> bool:
    """导入单个 Prompt 文件"""
    print(f"Importing: {file_path.name}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    meta = data.get("meta", {})
    policy = data.get("policy", {})
    prompt = data.get("prompt", "")

    npc_id = meta.get("npc_id")
    version = meta.get("version", 1)

    if not npc_id:
        print(f"  ❌ Missing npc_id in {file_path.name}")
        return False

    async with async_session_maker() as session:
        # 检查是否已存在
        stmt = select(NPCPrompt).where(
            NPCPrompt.tenant_id == tenant_id,
            NPCPrompt.site_id == site_id,
            NPCPrompt.npc_id == npc_id,
            NPCPrompt.version == version,
            NPCPrompt.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and not force:
            print(f"  ⚠️  Already exists: {npc_id} v{version} (use --force to overwrite)")
            return False

        if existing and force:
            # 更新现有记录
            existing.content = prompt
            existing.meta = meta
            existing.policy = policy
            existing.author = meta.get("author", "system")
            existing.description = meta.get("description")
            print(f"  ✅ Updated: {npc_id} v{version}")
        else:
            # 创建新记录
            new_prompt = NPCPrompt(
                tenant_id=tenant_id,
                site_id=site_id,
                npc_id=npc_id,
                version=version,
                active=True,  # 首次导入设为激活
                content=prompt,
                meta=meta,
                policy=policy,
                author=meta.get("author", "system"),
                description=meta.get("description"),
            )
            session.add(new_prompt)
            print(f"  ✅ Created: {npc_id} v{version} (active)")

        await session.commit()

    return True


async def main():
    parser = argparse.ArgumentParser(description="Import prompts from YAML files")
    parser.add_argument(
        "--file",
        type=str,
        help="Import specific file (relative to data/prompts/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing versions",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=settings.DEFAULT_TENANT_ID,
        help=f"Tenant ID (default: {settings.DEFAULT_TENANT_ID})",
    )
    parser.add_argument(
        "--site-id",
        type=str,
        default=settings.DEFAULT_SITE_ID,
        help=f"Site ID (default: {settings.DEFAULT_SITE_ID})",
    )
    args = parser.parse_args()

    prompts_dir = Path(__file__).parent.parent.parent.parent / "data" / "prompts"

    if not prompts_dir.exists():
        print(f"❌ Prompts directory not found: {prompts_dir}")
        sys.exit(1)

    if args.file:
        # 导入指定文件
        file_path = prompts_dir / args.file
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            sys.exit(1)
        await import_prompt(file_path, args.tenant_id, args.site_id, args.force)
    else:
        # 导入所有 YAML 文件（排除模板和 README）
        yaml_files = [
            f for f in prompts_dir.glob("*.yaml")
            if not f.name.startswith("_")
        ]

        if not yaml_files:
            print(f"❌ No YAML files found in {prompts_dir}")
            sys.exit(1)

        print(f"Found {len(yaml_files)} prompt files")
        print(f"Tenant: {args.tenant_id}, Site: {args.site_id}")
        print("-" * 40)

        success = 0
        for file_path in yaml_files:
            if await import_prompt(file_path, args.tenant_id, args.site_id, args.force):
                success += 1

        print("-" * 40)
        print(f"Imported: {success}/{len(yaml_files)}")


if __name__ == "__main__":
    asyncio.run(main())
