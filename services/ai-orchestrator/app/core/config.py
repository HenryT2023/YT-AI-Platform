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

    # Tool Server 配置（指向 core-backend 的 /tools 接口）
    TOOLS_BASE_URL: str = "http://localhost:8000/api/tools"
    TOOLS_TIMEOUT_SECONDS: int = 30

    # 百度 LLM 配置
    BAIDU_API_KEY: str = ""
    BAIDU_SECRET_KEY: str = ""
    BAIDU_MODEL: str = "ernie-bot-4"
    BAIDU_TIMEOUT_SECONDS: float = 60.0
    BAIDU_MAX_RETRIES: int = 3

    # LLM 降级配置
    LLM_FALLBACK_ENABLED: bool = True
    LLM_SANDBOX_MODE: bool = False  # 开启后使用模拟响应

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 300

    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:8000"]

    # LLM 配置
    LLM_PROVIDER: str = "baidu"  # baidu / openai / qwen / ollama

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
    MEMORY_MAX_MESSAGES: int = 10    # 最大消息条数
    MEMORY_MAX_CHARS: int = 4000     # 最大字符数
    MEMORY_ENABLED: bool = True      # 是否启用会话记忆

    # 多租户默认配置
    DEFAULT_TENANT_ID: str = "yantian"
    DEFAULT_SITE_ID: str = "yantian-main"

    # 证据链配置（临时放宽，允许 LLM 直接回复）
    MIN_EVIDENCE_COUNT: int = 0
    MIN_CONFIDENCE_THRESHOLD: float = 0.0
    REQUIRE_VERIFIED_FOR_HISTORY: bool = False

    # 意图分类器配置
    INTENT_CLASSIFIER_USE_LLM: bool = False  # 是否使用 LLM 意图分类器
    INTENT_CLASSIFIER_CACHE_TTL: int = 300   # 缓存 TTL（秒）

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
