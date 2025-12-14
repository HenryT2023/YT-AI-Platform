"""
Refresh Token 模型

用于存储和管理 refresh token，支持：
- Token 撤销（logout）
- Token 轮换（rotate）
- 链式追踪（replaced_by）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class RefreshToken(Base):
    """
    Refresh Token 实体
    
    存储 refresh token 的 hash（不存明文），支持：
    - 撤销：revoked_at 不为空表示已撤销
    - 轮换：replaced_by_id 指向新 token
    """
    
    __tablename__ = "refresh_tokens"
    
    # 主键
    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    
    # 关联用户
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Token hash（SHA-256）
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    
    # 时间戳
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    # 撤销时间（不为空表示已撤销）
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # 轮换链：指向替换此 token 的新 token
    replaced_by_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # 客户端信息（可选，用于审计）
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    
    # 关系
    user = relationship("User", backref="refresh_tokens")
    replaced_by = relationship("RefreshToken", remote_side=[id], uselist=False)
    
    # 索引
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_revoked", "user_id", "revoked_at"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.is_revoked})>"
    
    @property
    def is_revoked(self) -> bool:
        """是否已撤销"""
        return self.revoked_at is not None
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """是否有效（未撤销且未过期）"""
        return not self.is_revoked and not self.is_expired
    
    def revoke(self) -> None:
        """撤销此 token"""
        from datetime import timezone
        if not self.revoked_at:
            self.revoked_at = datetime.now(timezone.utc)
    
    def rotate(self, new_token_id: str) -> None:
        """
        轮换此 token
        
        撤销当前 token 并指向新 token
        """
        self.revoke()
        self.replaced_by_id = new_token_id
