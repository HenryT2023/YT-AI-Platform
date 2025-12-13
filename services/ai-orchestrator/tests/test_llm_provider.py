"""
LLM Provider 集成测试

测试场景：
1. Sandbox 模式（模拟响应）
2. 真实 API 调用（需配置 API Key）
3. 降级处理
4. 错误分类
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.providers.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMError,
    LLMErrorType,
)
from app.providers.llm.baidu_ernie import BaiduERNIEProvider
from app.providers.llm.factory import get_llm_provider, reset_provider


class TestBaiduERNIEProvider:
    """百度 ERNIE Provider 测试"""

    @pytest.fixture
    def sandbox_provider(self):
        """Sandbox 模式 Provider"""
        return BaiduERNIEProvider(sandbox_mode=True)

    @pytest.fixture
    def mock_provider(self):
        """Mock Provider（用于测试错误处理）"""
        return BaiduERNIEProvider(
            api_key="test-key",
            secret_key="test-secret",
            sandbox_mode=False,
        )

    @pytest.mark.asyncio
    async def test_sandbox_generate_with_citations(self, sandbox_provider):
        """测试 Sandbox 模式生成（有证据）"""
        request = LLMRequest(
            system_prompt="你是严氏先祖。",
            user_message="请问严氏家训有哪些？",
            citations=[
                {
                    "id": "evidence-001",
                    "title": "严氏家训十则",
                    "excerpt": "一曰孝悌为本，二曰耕读传家...",
                }
            ],
            trace_id="test-trace-001",
            npc_id="ancestor_yan",
        )

        response = await sandbox_provider.generate(request)

        assert response.text
        assert "严氏先祖" in response.text or "家训" in response.text
        assert response.model == "ernie-bot-4-sandbox"
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_sandbox_generate_without_citations(self, sandbox_provider):
        """测试 Sandbox 模式生成（无证据）"""
        request = LLMRequest(
            system_prompt="你是严氏先祖。",
            user_message="请问外星人存在吗？",
            citations=[],
            trace_id="test-trace-002",
        )

        response = await sandbox_provider.generate(request)

        assert response.text
        assert "不太清楚" in response.text or "建议" in response.text

    @pytest.mark.asyncio
    async def test_health_check_sandbox(self, sandbox_provider):
        """测试 Sandbox 模式健康检查"""
        result = await sandbox_provider.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_provider_name(self, sandbox_provider):
        """测试 Provider 名称"""
        assert sandbox_provider.provider_name == "baidu"
        assert sandbox_provider.model_name == "ernie-bot-4"

    @pytest.mark.asyncio
    async def test_audit_record(self, sandbox_provider):
        """测试审计记录"""
        request = LLMRequest(
            system_prompt="你是测试 NPC。",
            user_message="测试问题",
            trace_id="test-trace-003",
        )

        await sandbox_provider.generate(request)

        assert len(sandbox_provider.audit_records) == 1
        record = sandbox_provider.audit_records[0]
        assert record.trace_id == "test-trace-003"
        assert record.provider == "baidu"
        assert record.status == "success"


class TestLLMProviderFactory:
    """LLM Provider 工厂测试"""

    def setup_method(self):
        """每个测试前重置 Provider"""
        reset_provider()

    def test_get_baidu_provider_sandbox(self):
        """测试获取百度 Provider（Sandbox 模式）"""
        provider = get_llm_provider(provider="baidu", sandbox_mode=True)

        assert provider is not None
        assert provider.provider_name == "baidu"

    def test_get_unknown_provider_fallback(self):
        """测试未知 Provider 回退到 Sandbox"""
        provider = get_llm_provider(provider="unknown", sandbox_mode=True)

        assert provider is not None


class TestLLMError:
    """LLM 错误测试"""

    def test_error_types(self):
        """测试错误类型"""
        auth_error = LLMError(
            error_type=LLMErrorType.AUTH,
            message="Invalid API key",
            retryable=False,
        )
        assert auth_error.error_type == LLMErrorType.AUTH
        assert not auth_error.retryable

        timeout_error = LLMError(
            error_type=LLMErrorType.TIMEOUT,
            message="Request timeout",
            retryable=True,
        )
        assert timeout_error.error_type == LLMErrorType.TIMEOUT
        assert timeout_error.retryable

    def test_error_str(self):
        """测试错误字符串"""
        error = LLMError(
            error_type=LLMErrorType.RATE_LIMIT,
            message="Too many requests",
        )
        assert "[rate_limit]" in str(error)
        assert "Too many requests" in str(error)


class TestBaiduERNIEProviderRetry:
    """百度 ERNIE Provider 重试测试"""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """测试超时重试"""
        provider = BaiduERNIEProvider(
            api_key="test-key",
            secret_key="test-secret",
            max_retries=2,
            base_retry_delay=0.1,
        )

        # Mock _do_generate 抛出超时错误
        call_count = 0

        async def mock_do_generate(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise LLMError(
                    error_type=LLMErrorType.TIMEOUT,
                    message="Timeout",
                    retryable=True,
                )
            return LLMResponse(
                text="Success after retry",
                model="ernie-bot-4",
                tokens_input=10,
                tokens_output=20,
            )

        provider._do_generate = mock_do_generate
        provider._access_token = "mock-token"
        provider._token_expires_at = 9999999999

        request = LLMRequest(
            system_prompt="Test",
            user_message="Test",
            trace_id="test-retry",
        )

        response = await provider.generate(request)

        assert call_count == 3
        assert response.text == "Success after retry"

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """测试认证错误不重试"""
        provider = BaiduERNIEProvider(
            api_key="test-key",
            secret_key="test-secret",
            max_retries=3,
        )

        call_count = 0

        async def mock_do_generate(request):
            nonlocal call_count
            call_count += 1
            raise LLMError(
                error_type=LLMErrorType.AUTH,
                message="Invalid API key",
                retryable=False,
            )

        provider._do_generate = mock_do_generate
        provider._access_token = "mock-token"
        provider._token_expires_at = 9999999999

        request = LLMRequest(
            system_prompt="Test",
            user_message="Test",
        )

        with pytest.raises(LLMError) as exc_info:
            await provider.generate(request)

        assert call_count == 1  # 不重试
        assert exc_info.value.error_type == LLMErrorType.AUTH


class TestLLMProviderFallback:
    """LLM Provider 降级测试"""

    @pytest.mark.asyncio
    async def test_generate_with_fallback(self):
        """测试带降级的生成"""
        provider = BaiduERNIEProvider(sandbox_mode=False)

        # Mock generate 抛出错误
        async def mock_generate(request):
            raise LLMError(
                error_type=LLMErrorType.SERVER,
                message="Server error",
                retryable=False,
            )

        provider.generate = mock_generate

        request = LLMRequest(
            system_prompt="Test",
            user_message="Test",
        )

        response = await provider.generate_with_fallback(
            request,
            fallback_text="服务暂时不可用",
        )

        assert response.text == "服务暂时不可用"
        assert response.finish_reason == "fallback"


# 真实 API 测试（需要配置环境变量）
@pytest.mark.skipif(
    True,  # 默认跳过，手动运行时改为 False
    reason="需要配置 BAIDU_API_KEY 和 BAIDU_SECRET_KEY"
)
class TestBaiduERNIERealAPI:
    """百度 ERNIE 真实 API 测试"""

    @pytest.mark.asyncio
    async def test_real_api_call(self):
        """测试真实 API 调用"""
        from app.core.config import settings

        provider = BaiduERNIEProvider(
            api_key=settings.BAIDU_API_KEY,
            secret_key=settings.BAIDU_SECRET_KEY,
            model="ernie-bot-4",
        )

        request = LLMRequest(
            system_prompt="你是一个友好的助手。",
            user_message="你好，请用一句话介绍自己。",
            max_tokens=100,
        )

        response = await provider.generate(request)

        assert response.text
        assert response.tokens_input > 0
        assert response.tokens_output > 0
        print(f"Response: {response.text}")
        print(f"Tokens: {response.tokens_input} + {response.tokens_output}")
