#!/usr/bin/env python3
"""
创建管理员用户脚本

用法：
    # 使用环境变量
    ADMIN_USERNAME=admin ADMIN_PASSWORD=secret123 python scripts/create_admin_user.py
    
    # 使用命令行参数
    python scripts/create_admin_user.py --username admin --password secret123 --role admin
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash
from app.database.models.user import User, UserRole


async def create_admin_user(
    username: str,
    password: str,
    role: str = UserRole.SUPER_ADMIN,
    display_name: str | None = None,
    email: str | None = None,
) -> None:
    """创建管理员用户"""
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 检查用户是否已存在
        result = await session.execute(
            select(User).where(User.username == username)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"用户 '{username}' 已存在 (ID: {existing_user.id}, Role: {existing_user.role})")
            
            # 询问是否更新密码
            update = input("是否更新密码? (y/N): ").strip().lower()
            if update == 'y':
                existing_user.hashed_password = get_password_hash(password)
                existing_user.role = role
                await session.commit()
                print(f"用户 '{username}' 密码和角色已更新")
            return
        
        # 创建新用户
        user = User(
            username=username,
            hashed_password=get_password_hash(password),
            role=role,
            display_name=display_name or username,
            email=email,
            is_active=True,
            is_verified=True,
            status="active",
        )
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        print(f"管理员用户创建成功:")
        print(f"  ID: {user.id}")
        print(f"  Username: {user.username}")
        print(f"  Role: {user.role}")
        print(f"  Display Name: {user.display_name}")
    
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="创建管理员用户")
    parser.add_argument(
        "--username", "-u",
        default=os.environ.get("ADMIN_USERNAME", "admin"),
        help="用户名 (默认: admin 或 ADMIN_USERNAME 环境变量)",
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("ADMIN_PASSWORD"),
        help="密码 (必需，或设置 ADMIN_PASSWORD 环境变量)",
    )
    parser.add_argument(
        "--role", "-r",
        default=os.environ.get("ADMIN_ROLE", UserRole.SUPER_ADMIN),
        choices=[UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.SITE_ADMIN, UserRole.OPERATOR, UserRole.VIEWER],
        help="角色 (默认: super_admin)",
    )
    parser.add_argument(
        "--display-name", "-d",
        default=os.environ.get("ADMIN_DISPLAY_NAME"),
        help="显示名称",
    )
    parser.add_argument(
        "--email", "-e",
        default=os.environ.get("ADMIN_EMAIL"),
        help="邮箱",
    )
    
    args = parser.parse_args()
    
    if not args.password:
        print("错误: 必须提供密码 (--password 或 ADMIN_PASSWORD 环境变量)")
        sys.exit(1)
    
    if len(args.password) < 6:
        print("错误: 密码长度至少 6 位")
        sys.exit(1)
    
    print(f"正在创建管理员用户...")
    print(f"  数据库: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    
    asyncio.run(create_admin_user(
        username=args.username,
        password=args.password,
        role=args.role,
        display_name=args.display_name,
        email=args.email,
    ))


if __name__ == "__main__":
    main()
