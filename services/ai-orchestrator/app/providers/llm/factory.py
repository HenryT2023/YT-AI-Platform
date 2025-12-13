"""
LLM Provider 工厂

根据配置创建对应的 LLM Provider 实例
"""

import structlog
from typing import Optional

from app.core.config import settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.baidu_ernie import BaiduERNIEProvider

logger = structlog.get_logger(__name__)

# 全局 Provider 实例缓存
_provider_instance: Optional[LLMProvider] = None


def get_llm_provider(
    provider: Optional[str] = None,
    sandbox_mode: bool = False,
) -> LLMProvider:
    """
    获取 LLM Provider 实例

    Args:
        provider: 提供者名称（baidu/openai/qwen），默认从配置读取
        sandbox_mode: 是否使用 Sandbox 模式（返回模拟响应）

    Returns:
        LLMProvider: LLM Provider 实例
    """
    global _provider_instance

    provider_name = provider or settings.LLM_PROVIDER

    # 如果已有缓存实例且不是 sandbox 模式切换，直接返回
    if _provider_instance and not sandbox_mode:
        return _provider_instance

    log = logger.bind(provider=provider_name, sandbox=sandbox_mode)
    log.info("creating_llm_provider")

    if provider_name == "baidu":
        instance = BaiduERNIEProvider(
            api_key=settings.BAIDU_API_KEY,
            secret_key=settings.BAIDU_SECRET_KEY,
            model=settings.BAIDU_MODEL,
            timeout_seconds=60.0,
            max_retries=3,
            sandbox_mode=sandbox_mode,
        )
    elif provider_name == "openai":
        # TODO: 实现 OpenAI Provider
        log.warning("openai_provider_not_implemented", fallback="baidu")
        instance = BaiduERNIEProvider(sandbox_mode=True)
    elif provider_name == "qwen":
        # TODO: 实现 Qwen Provider
        log.warning("qwen_provider_not_implemented", fallback="baidu")
        instance = BaiduERNIEProvider(sandbox_mode=True)
    else:
        log.warning("unknown_provider", provider=provider_name, fallback="baidu_sandbox")
        instance = BaiduERNIEProvider(sandbox_mode=True)

    if not sandbox_mode:
        _provider_instance = instance

    return instance


def reset_provider() -> None:
    """重置 Provider 实例（用于测试）"""
    global _provider_instance
    _provider_instance = None
