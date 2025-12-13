"""
AI Orchestrator 配置
"""

from functools import lru_cache
from typing import List, Optional

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
    PORT: int = 8001

    # Core Backend 服务地址
    CORE_BACKEND_URL: str = "http://localhost:8000"
    INTERNAL_API_KEY: str = "your-internal-api-key"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # LLM 配置
    LLM_PROVIDER: str = "openai"  # openai / qwen / ollama

    # OpenAI 配置
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"

    # Qwen 配置
    QWEN_API_KEY: str = ""
    QWEN_API_BASE: str = "https://dashscope.aliyuncs.com/api/v1"
    QWEN_MODEL: str = "qwen-max"

    # Ollama 配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # Embedding 配置
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Qdrant 向量数据库配置
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "yantian_knowledge"

    # 对话配置
    MAX_CONTEXT_TOKENS: int = 4000
    MAX_RESPONSE_TOKENS: int = 1000
    TEMPERATURE: float = 0.7

    # 记忆配置
    MEMORY_TTL_SECONDS: int = 86400  # 24 小时

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
