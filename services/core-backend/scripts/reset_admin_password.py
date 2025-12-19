#!/usr/bin/env python3
"""
重置管理员密码脚本
用于修复 bcrypt 升级后的密码哈希兼容性问题
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.security import get_password_hash
from app.db.session import async_session_maker
from app.database.models import User


async def reset_admin_password():
    """重置 admin 用户密码为 admin123"""
    async with async_session_maker() as db:
        # 查找 admin 用户
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        
        if not admin:
            print("❌ 未找到 admin 用户")
            return
        
        # 生成新的密码哈希
        new_hash = get_password_hash("admin123")
        admin.hashed_password = new_hash
        
        await db.commit()
        print("✅ admin 密码已重置为: admin123")
        print(f"   新哈希: {new_hash[:50]}...")


if __name__ == "__main__":
    asyncio.run(reset_admin_password())
