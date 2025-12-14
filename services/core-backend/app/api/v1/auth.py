"""
认证 API

处理用户登录、令牌刷新、登出等

Refresh Token 机制：
- access_token: 短有效期（默认 15min），存储在 HttpOnly cookie
- refresh_token: 长有效期（默认 7d），存储在 HttpOnly cookie，落库可撤销
- 每次 refresh 会 rotate：生成新 refresh_token，旧的作废
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.core.config import settings
from app.core.security import create_access_token, decode_token, verify_password
from app.core.rbac import ALLOWED_LOGIN_ROLES
from app.core.redis_client import get_redis, LoginRateLimiter
from app.db import get_db
from app.database.models.user import User, UserRole
from app.database.models.refresh_token import RefreshToken

logger = structlog.get_logger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ============================================================
# Schemas
# ============================================================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int
    refresh_expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str


class RefreshResponse(BaseModel):
    """刷新令牌响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int
    refresh_expires_in: int


class LogoutRequest(BaseModel):
    """登出请求"""
    refresh_token: str


class LogoutResponse(BaseModel):
    """登出响应"""
    ok: bool
    message: str


class UserInfo(BaseModel):
    """用户信息响应"""
    id: str
    username: Optional[str]
    display_name: Optional[str]
    role: str
    is_active: bool


# ============================================================
# Helper Functions
# ============================================================

def generate_refresh_token() -> str:
    """生成随机 refresh token（32 字节 = 64 字符 hex）"""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """对 token 进行 SHA-256 哈希"""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_refresh_token_in_db(
    db: AsyncSession,
    user_id: str,
    token: str,
    expires_days: int = None,
    user_agent: str = None,
    ip_address: str = None,
) -> RefreshToken:
    """
    在数据库中创建 refresh token 记录
    
    只存储 token 的 hash，不存明文
    """
    if expires_days is None:
        expires_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    
    token_hash = hash_token(token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=expires_days)
    
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        issued_at=now,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    
    db.add(refresh_token)
    await db.flush()
    
    return refresh_token


async def validate_refresh_token(
    db: AsyncSession,
    token: str,
) -> Optional[RefreshToken]:
    """
    验证 refresh token
    
    返回 RefreshToken 记录（如果有效），否则返回 None
    """
    token_hash = hash_token(token)
    
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
    )
    refresh_token = result.scalar_one_or_none()
    
    if not refresh_token:
        return None
    
    # 检查是否过期
    if refresh_token.is_expired:
        return None
    
    return refresh_token


async def rotate_refresh_token(
    db: AsyncSession,
    old_token: RefreshToken,
    new_token: str,
    user_agent: str = None,
    ip_address: str = None,
) -> RefreshToken:
    """
    轮换 refresh token
    
    撤销旧 token，创建新 token，并建立链接
    """
    # 创建新 token
    new_refresh = await create_refresh_token_in_db(
        db=db,
        user_id=old_token.user_id,
        token=new_token,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    
    # 撤销旧 token 并指向新 token
    old_token.rotate(new_refresh.id)
    
    return new_refresh


async def revoke_refresh_token(
    db: AsyncSession,
    token: str,
) -> bool:
    """
    撤销 refresh token
    
    返回是否成功撤销
    """
    token_hash = hash_token(token)
    
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_token = result.scalar_one_or_none()
    
    if not refresh_token:
        return False
    
    refresh_token.revoke()
    return True


async def revoke_all_user_tokens(
    db: AsyncSession,
    user_id: str,
) -> int:
    """
    撤销用户的所有 refresh token
    
    返回撤销的数量
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    tokens = result.scalars().all()
    
    count = 0
    for token in tokens:
        token.revoke()
        count += 1
    
    return count


@router.post("/login", response_model=LoginResponse)
async def admin_login(
    data: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """
    管理员登录
    
    验证用户名密码，返回：
    - access_token: JWT，短有效期
    - refresh_token: 随机串，长有效期，落库
    
    安全机制：
    - 登录失败超过阈值后锁定（按 username + IP）
    """
    # 获取客户端 IP
    client_ip = request.client.host if request.client else "unknown"
    log = logger.bind(username=data.username, ip=client_ip)
    
    # 检查是否被锁定
    try:
        redis_client = await get_redis()
        rate_limiter = LoginRateLimiter(redis_client)
        
        is_locked, remaining_seconds = await rate_limiter.check_locked(data.username, client_ip)
        
        if is_locked:
            log.warning("login_blocked_by_rate_limit", remaining_seconds=remaining_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"登录失败次数过多，请在 {remaining_seconds} 秒后重试",
                    "remaining_seconds": remaining_seconds,
                    "locked": True,
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis 不可用时不阻止登录，但记录警告
        log.warning("redis_unavailable_for_rate_limit", error=str(e))
        rate_limiter = None
    
    # 查找用户
    result = await db.execute(
        select(User).where(
            User.username == data.username,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    # 验证失败的统一处理函数
    async def handle_login_failure(reason: str):
        if rate_limiter:
            count, remaining = await rate_limiter.record_failure(data.username, client_ip)
            log.warning("login_failed", reason=reason, fail_count=count, remaining_attempts=remaining)
            
            if remaining == 0:
                # 已达到锁定阈值
                lockout_info = await rate_limiter.get_lockout_info(data.username, client_ip)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": f"登录失败次数过多，账户已锁定 {settings.AUTH_LOCKOUT_MINUTES} 分钟",
                        "remaining_seconds": lockout_info["remaining_seconds"],
                        "locked": True,
                    },
                )
        else:
            log.warning("login_failed", reason=reason)
    
    if not user:
        await handle_login_failure("user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    # 验证密码
    if not user.hashed_password or not verify_password(data.password, user.hashed_password):
        await handle_login_failure("invalid_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    
    # 检查是否为允许登录后台的角色
    if user.role not in ALLOWED_LOGIN_ROLES:
        await handle_login_failure("invalid_role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"角色 [{user.role}] 无权登录管理后台，仅允许 admin/operator/viewer 角色",
        )
    
    # 检查账户状态
    if not user.is_active:
        await handle_login_failure("account_disabled")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    
    # 登录成功，清除失败记录
    if rate_limiter:
        await rate_limiter.clear_failures(data.username, client_ip)
    
    # 更新最后登录时间和 IP
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = client_ip
    
    # 生成 access token (JWT)
    access_expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=access_expires_minutes),
        extra_claims={
            "username": user.username,
            "role": user.role,
        },
    )
    
    # 生成 refresh token（随机串）并存入数据库
    refresh_token_plain = generate_refresh_token()
    refresh_expires_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    
    # 获取客户端信息
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    await create_refresh_token_in_db(
        db=db,
        user_id=str(user.id),
        token=refresh_token_plain,
        expires_days=refresh_expires_days,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    
    await db.commit()
    
    log.info("login_success", user_id=str(user.id), role=user.role)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_plain,
        token_type="bearer",
        access_expires_in=access_expires_minutes * 60,
        refresh_expires_in=refresh_expires_days * 24 * 60 * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserInfo:
    """
    获取当前登录用户信息
    
    若 access_token 过期返回 401，前端应触发 refresh
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌无效或已过期",
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
            detail="用户不存在",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    
    return UserInfo(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_access_token(
    data: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshResponse:
    """
    刷新访问令牌
    
    使用 refresh_token 获取新的 access_token 和 refresh_token
    每次刷新会 rotate：旧 refresh_token 作废，生成新的
    """
    # 验证 refresh token
    old_refresh = await validate_refresh_token(db, data.refresh_token)
    
    if not old_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期",
        )
    
    # 获取用户信息
    result = await db.execute(
        select(User).where(
            User.id == old_refresh.user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    
    # 检查角色是否仍然允许登录
    if user.role not in ALLOWED_LOGIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"角色 [{user.role}] 无权访问管理后台",
        )
    
    # 生成新的 access token
    access_expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=access_expires_minutes),
        extra_claims={
            "username": user.username,
            "role": user.role,
        },
    )
    
    # 生成新的 refresh token 并 rotate
    new_refresh_token_plain = generate_refresh_token()
    refresh_expires_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    
    # 获取客户端信息
    user_agent = request.headers.get("User-Agent", "")[:500]
    client_ip = request.client.host if request.client else None
    
    await rotate_refresh_token(
        db=db,
        old_token=old_refresh,
        new_token=new_refresh_token_plain,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    
    await db.commit()
    
    return RefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token_plain,
        token_type="bearer",
        access_expires_in=access_expires_minutes * 60,
        refresh_expires_in=refresh_expires_days * 24 * 60 * 60,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    data: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogoutResponse:
    """
    登出
    
    撤销 refresh_token，使其失效
    """
    success = await revoke_refresh_token(db, data.refresh_token)
    await db.commit()
    
    if success:
        return LogoutResponse(ok=True, message="登出成功")
    else:
        # 即使 token 不存在也返回成功（幂等）
        return LogoutResponse(ok=True, message="登出成功")


async def get_current_user(token: Annotated[Optional[str], Depends(oauth2_scheme)]) -> str:
    """获取当前用户依赖"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="访问令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload["sub"]
