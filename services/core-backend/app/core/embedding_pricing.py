"""
Embedding 定价配置

用于成本估算
"""

from typing import Dict

# Embedding 定价表 (USD per 1K tokens)
EMBEDDING_PRICING: Dict[str, Dict[str, float]] = {
    "openai": {
        "text-embedding-3-small": 0.00002,
        "text-embedding-3-large": 0.00013,
        "text-embedding-ada-002": 0.0001,
    },
    "baidu": {
        "embedding-v1": 0.0001,
        "bge-large-zh": 0.0001,
        "bge-large-en": 0.0001,
    },
    "local": {
        "bge-large-zh": 0.0,
        "bge-small-zh": 0.0,
    },
}

# 默认价格（未知模型）
DEFAULT_PRICE_PER_1K = 0.0001


def get_embedding_price(provider: str, model: str) -> float:
    """
    获取 embedding 价格 (USD per 1K tokens)
    
    Args:
        provider: 提供者名称 (openai/baidu/local)
        model: 模型名称
        
    Returns:
        每 1K tokens 的价格 (USD)
    """
    provider_lower = provider.lower()
    model_lower = model.lower()
    
    if provider_lower in EMBEDDING_PRICING:
        provider_prices = EMBEDDING_PRICING[provider_lower]
        if model_lower in provider_prices:
            return provider_prices[model_lower]
        # 尝试部分匹配
        for key, price in provider_prices.items():
            if key in model_lower or model_lower in key:
                return price
    
    return DEFAULT_PRICE_PER_1K


def get_all_pricing() -> Dict[str, Dict[str, float]]:
    """获取所有定价配置"""
    return EMBEDDING_PRICING.copy()
