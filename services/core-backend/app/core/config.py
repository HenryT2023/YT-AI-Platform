"""
应用配置

使用 pydantic-settings 管理环境变量配置
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 基础配置
    ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://yantian:yantian@localhost:5432/yantian"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "yantian"
    POSTGRES_PASSWORD: str = "yantian"
    POSTGRES_DB: str = "yantian"

    # 数据库连接池配置
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # 30 分钟

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT 配置
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # 登录安全配置
    AUTH_MAX_LOGIN_FAILS: int = 5  # 最大登录失败次数
    AUTH_LOCKOUT_MINUTES: int = 10  # 锁定时间（分钟）

    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:8000"]

    # 内部 API Key（服务间通信）
    INTERNAL_API_KEY: str = "your-internal-api-key"

    # AI Orchestrator 服务地址
    AI_ORCHESTRATOR_URL: str = "http://localhost:8001"

    # 对象存储配置
    S3_ENDPOINT: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "yantian-assets"

    # 多租户配置
    DEFAULT_TENANT_ID: str = "yantian"
    DEFAULT_SITE_ID: str = "yantian-main"

    # 内部服务通信密钥
    INTERNAL_API_KEY: str = "your-internal-api-key-change-in-production"

    # Qdrant 配置
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "yantian_evidence"
    QDRANT_ENABLED: bool = True

    # Embedding 配置
    OPENAI_API_KEY: str = ""
    BAIDU_API_KEY: str = ""
    BAIDU_SECRET_KEY: str = ""

    # 检索配置
    RETRIEVAL_STRATEGY: str = "hybrid"  # trgm / qdrant / hybrid
    RETRIEVAL_TRGM_WEIGHT: float = 0.4
    RETRIEVAL_QDRANT_WEIGHT: float = 0.6

    # 功能开关
    FEATURE_IOT_ENABLED: bool = False
    FEATURE_FARMING_ENGINE_ENABLED: bool = False
    FEATURE_ANALYTICS_ENABLED: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
