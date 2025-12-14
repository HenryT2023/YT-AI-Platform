"""
认证 API

处理用户登录、注册、令牌刷新等
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.db import get_db
from app.database.models.user import User, UserRole

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class Token(BaseModel):
    """令牌响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class TokenRefresh(BaseModel):
    """刷新令牌请求"""

    refresh_token: str


class UserInfo(BaseModel):
    """用户信息响应"""
    id: str
    username: Optional[str]
    display_name: Optional[str]
    role: str
    is_active: bool


@router.post("/login", response_model=LoginResponse)
async def admin_login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """
    管理员登录
    
    验证用户名密码，返回 JWT token
    """
    # 查找用户
    result = await db.execute(
        select(User).where(
            User.username == data.username,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    # 验证密码
    if not user.hashed_password or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    # 检查是否为系统用户（非游客）
    if user.role == UserRole.VISITOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="游客账户无法登录管理后台",
        )
    
    # 检查账户状态
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    
    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    
    # 生成 token
    expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=expires_minutes),
        extra_claims={
            "username": user.username,
            "role": user.role,
        },
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_minutes * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.post("/token", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    """
    OAuth2 兼容的登录端点
    """
    # 查找用户
    result = await db.execute(
        select(User).where(
            User.username == form_data.username,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    
    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    
    expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=expires_minutes),
        extra_claims={
            "username": user.username,
            "role": user.role,
        },
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_minutes * 60,
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserInfo:
    """获取当前登录用户信息"""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return UserInfo(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(data: TokenRefresh) -> Token:
    """刷新访问令牌"""
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(
        subject=payload["sub"],
        expires_delta=timedelta(minutes=expires_minutes),
    )
    new_refresh_token = create_refresh_token(subject=payload["sub"])

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_minutes * 60,
    )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """获取当前用户依赖"""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload["sub"]
