"""
百度 ERNIE Bot LLM Provider

支持百度文心一言系列模型：
- ernie-bot-4 (ERNIE 4.0)
- ernie-bot-turbo (ERNIE 3.5 Turbo)
- ernie-bot (ERNIE 3.5)

特性：
- 超时控制
- 指数退避重试
- 错误分类
- 审计记录
"""

import asyncio
import hashlib
import json
import time
import structlog
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.providers.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMError,
    LLMErrorType,
    LLMAuditRecord,
)

logger = structlog.get_logger(__name__)

# 百度千帆 API 端点（新版 V2 API）
# 文档: https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Fm2vrveyu
BAIDU_QIANFAN_BASE = "https://qianfan.baidubce.com/v2"
BAIDU_CHAT_ENDPOINT = f"{BAIDU_QIANFAN_BASE}/chat/completions"

# 模型名称映射（新版 API 使用统一端点，通过 model 参数指定模型）
BAIDU_MODEL_MAPPING = {
    "ernie-bot-4": "ernie-4.0-8k",
    "ernie-4.0-8k": "ernie-4.0-8k",
    "ernie-bot-turbo": "ernie-3.5-8k",
    "ernie-bot": "ernie-3.5-8k",
    "ernie-3.5-8k": "ernie-3.5-8k",
}

# 旧版 API 端点（备用）
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_CHAT_ENDPOINTS_LEGACY = {
    "ernie-bot-4": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro",
    "ernie-4.0-8k": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro",
    "ernie-bot-turbo": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/eb-instant",
    "ernie-bot": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
    "ernie-3.5-8k": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
}


class BaiduERNIEProvider(LLMProvider):
    """
    百度 ERNIE Bot LLM Provider

    实现统一 LLMProvider 接口，支持：
    - 超时控制
    - 指数退避重试
    - 错误分类
    - 审计记录
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
        sandbox_mode: bool = False,
    ):
        self._api_key = api_key or settings.BAIDU_API_KEY
        self._secret_key = secret_key or settings.BAIDU_SECRET_KEY
        self._model = model or settings.BAIDU_MODEL
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay
        self._sandbox_mode = sandbox_mode

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # 审计记录列表（可由外部收集）
        self.audit_records: list[LLMAuditRecord] = []

    @property
    def provider_name(self) -> str:
        return "baidu"

    @property
    def model_name(self) -> str:
        return self._model

    async def _get_access_token(self) -> str:
        """获取百度 API access_token"""
        # 检查缓存的 token 是否有效
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token

        if not self._api_key or not self._secret_key:
            raise LLMError(
                error_type=LLMErrorType.AUTH,
                message="Missing BAIDU_API_KEY or BAIDU_SECRET_KEY",
                retryable=False,
            )

        log = logger.bind(provider="baidu")
        log.info("fetching_access_token")

        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(
                    BAIDU_TOKEN_URL,
                    params={
                        "grant_type": "client_credentials",
                        "client_id": self._api_key,
                        "client_secret": self._secret_key,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "access_token" not in data:
                    raise LLMError(
                        error_type=LLMErrorType.AUTH,
                        message=f"Failed to get access token: {data.get('error_description', 'Unknown error')}",
                        raw_error=data,
                        retryable=False,
                    )

                self._access_token = data["access_token"]
                # Token 有效期通常为 30 天
                self._token_expires_at = time.time() + data.get("expires_in", 2592000)

                log.info("access_token_obtained", expires_in=data.get("expires_in"))
                return self._access_token

        except httpx.TimeoutException:
            raise LLMError(
                error_type=LLMErrorType.TIMEOUT,
                message="Timeout while fetching access token",
                retryable=True,
            )
        except httpx.HTTPStatusError as e:
            raise LLMError(
                error_type=LLMErrorType.AUTH,
                message=f"HTTP error while fetching access token: {e.response.status_code}",
                status_code=e.response.status_code,
                retryable=False,
            )

    def _get_chat_endpoint(self) -> str:
        """获取聊天 API 端点"""
        endpoint = BAIDU_CHAT_ENDPOINTS.get(self._model)
        if not endpoint:
            # 默认使用 ERNIE 4.0
            return BAIDU_CHAT_ENDPOINTS["ernie-bot-4"]
        return endpoint

    def _classify_error(self, status_code: int, error_data: Dict[str, Any]) -> LLMError:
        """分类错误"""
        error_code = error_data.get("error_code", 0)
        error_msg = error_data.get("error_msg", "Unknown error")

        # 百度错误码分类
        # https://cloud.baidu.com/doc/WENXINWORKSHOP/s/tlmyncueh
        if error_code in [110, 111]:
            return LLMError(
                error_type=LLMErrorType.AUTH,
                message=f"Authentication error: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=False,
            )
        elif error_code == 18:
            return LLMError(
                error_type=LLMErrorType.RATE_LIMIT,
                message=f"Rate limit exceeded: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=True,
            )
        elif error_code in [336000, 336001, 336002, 336003]:
            return LLMError(
                error_type=LLMErrorType.INVALID_REQUEST,
                message=f"Invalid request: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=False,
            )
        elif error_code == 336100:
            return LLMError(
                error_type=LLMErrorType.CONTENT_FILTER,
                message=f"Content filtered: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=False,
            )
        elif status_code >= 500:
            return LLMError(
                error_type=LLMErrorType.SERVER,
                message=f"Server error: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=True,
            )
        else:
            return LLMError(
                error_type=LLMErrorType.UNKNOWN,
                message=f"Unknown error: {error_msg}",
                status_code=status_code,
                raw_error=error_data,
                retryable=False,
            )

    def _build_messages(self, request: LLMRequest) -> list[Dict[str, str]]:
        """构建消息列表"""
        # 百度 API 不支持 system role，需要将 system prompt 放入第一条 user 消息
        # 或使用 system 参数（部分模型支持）
        messages = []

        # 构建用户消息（包含证据）
        user_content = request.user_message
        if request.citations:
            user_content += "\n\n【参考资料】\n"
            for i, c in enumerate(request.citations, 1):
                title = c.get("title", f"资料{i}")
                excerpt = c.get("excerpt", "")[:200]
                user_content += f"{i}. {title}: {excerpt}\n"

        messages.append({"role": "user", "content": user_content})

        return messages

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """生成回复（带重试）"""
        log = logger.bind(
            provider="baidu",
            model=self._model,
            trace_id=request.trace_id,
            npc_id=request.npc_id,
        )
        log.info("llm_generate_start")

        start_time = time.time()
        last_error: Optional[LLMError] = None

        # Sandbox 模式：返回模拟响应
        if self._sandbox_mode:
            return self._generate_sandbox_response(request)

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._do_generate(request)

                # 记录审计
                latency_ms = int((time.time() - start_time) * 1000)
                self._record_audit(
                    request=request,
                    response=response,
                    latency_ms=latency_ms,
                    status="success",
                )

                log.info(
                    "llm_generate_success",
                    tokens_input=response.tokens_input,
                    tokens_output=response.tokens_output,
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )

                return response

            except LLMError as e:
                last_error = e
                latency_ms = int((time.time() - start_time) * 1000)

                log.warning(
                    "llm_generate_error",
                    error_type=e.error_type.value,
                    error=e.message,
                    attempt=attempt + 1,
                    retryable=e.retryable,
                )

                if not e.retryable or attempt >= self._max_retries:
                    # 记录失败审计
                    self._record_audit(
                        request=request,
                        response=None,
                        latency_ms=latency_ms,
                        status="error",
                        error=e,
                    )
                    raise

                # 指数退避
                delay = self._base_retry_delay * (2 ** attempt)
                log.info("llm_retry_delay", delay_seconds=delay)
                await asyncio.sleep(delay)

        # 不应该到达这里
        raise last_error or LLMError(
            error_type=LLMErrorType.UNKNOWN,
            message="Max retries exceeded",
            retryable=False,
        )

    async def _do_generate(self, request: LLMRequest) -> LLMResponse:
        """执行单次生成（使用新版千帆 V2 API）"""
        # 构建 Authorization header（Bearer bce-v3/API_KEY/SECRET_KEY）
        auth_header = f"Bearer bce-v3/{self._api_key}/{self._secret_key}"
        
        # 获取模型名称
        model_name = BAIDU_MODEL_MAPPING.get(self._model, "ernie-4.0-8k")

        messages = self._build_messages(request)

        # 新版 API payload 格式
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # 添加 system message（新版 API 通过 messages 传递）
        if request.system_prompt:
            payload["messages"] = [
                {"role": "system", "content": request.system_prompt}
            ] + messages

        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
                response = await client.post(
                    BAIDU_CHAT_ENDPOINT,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": auth_header,
                    },
                )

                latency_ms = int((time.time() - start_time) * 1000)
                data = response.json()

                # 检查错误
                if "error" in data:
                    raise self._classify_error(response.status_code, data)

                # 解析响应（新版 API 格式）
                choices = data.get("choices", [])
                result_text = choices[0]["message"]["content"] if choices else ""
                usage = data.get("usage", {})

                return LLMResponse(
                    text=result_text,
                    model=self._model,
                    tokens_input=usage.get("prompt_tokens", 0),
                    tokens_output=usage.get("completion_tokens", 0),
                    finish_reason=data.get("finish_reason", "stop"),
                    latency_ms=latency_ms,
                    raw_response=data,
                )

        except httpx.TimeoutException:
            raise LLMError(
                error_type=LLMErrorType.TIMEOUT,
                message=f"Request timeout after {self._timeout}s",
                retryable=True,
            )
        except httpx.NetworkError as e:
            raise LLMError(
                error_type=LLMErrorType.NETWORK,
                message=f"Network error: {str(e)}",
                retryable=True,
            )

    def _generate_sandbox_response(self, request: LLMRequest) -> LLMResponse:
        """生成 Sandbox 模式响应"""
        # 提取 NPC 名称
        npc_name = "我"
        if "你是" in request.system_prompt:
            start = request.system_prompt.find("你是") + 2
            end = request.system_prompt.find("。", start)
            if end > start:
                npc_name = request.system_prompt[start:end]

        # 构建响应
        if request.citations:
            first_citation = request.citations[0]
            response_text = f"关于您问的「{request.user_message[:20]}...」，{npc_name}可以告诉您：\n\n"
            if first_citation.get("excerpt"):
                response_text += first_citation["excerpt"][:200]
            else:
                response_text += f"根据{first_citation.get('title', '相关记载')}，这个问题涉及到我们的历史传承。"
            if first_citation.get("title"):
                response_text += f"\n\n（参考：{first_citation['title']}）"
        else:
            response_text = f"这个问题{npc_name}不太清楚，建议您询问村中其他长辈或查阅相关文献。"

        return LLMResponse(
            text=response_text,
            model=f"{self._model}-sandbox",
            tokens_input=len(request.system_prompt) + len(request.user_message),
            tokens_output=len(response_text),
            finish_reason="stop",
            latency_ms=50,
        )

    def _record_audit(
        self,
        request: LLMRequest,
        response: Optional[LLMResponse],
        latency_ms: int,
        status: str,
        error: Optional[LLMError] = None,
    ) -> None:
        """记录审计"""
        # 计算请求 hash
        request_str = json.dumps({
            "system_prompt": request.system_prompt[:100],
            "user_message": request.user_message[:100],
            "npc_id": request.npc_id,
        }, sort_keys=True, ensure_ascii=False)
        request_hash = hashlib.sha256(request_str.encode()).hexdigest()[:16]

        record = LLMAuditRecord(
            trace_id=request.trace_id or "",
            provider=self.provider_name,
            model=self._model,
            request_hash=request_hash,
            tokens_input=response.tokens_input if response else 0,
            tokens_output=response.tokens_output if response else 0,
            latency_ms=latency_ms,
            status=status,
            error_type=error.error_type.value if error else None,
            error_message=error.message if error else None,
        )

        self.audit_records.append(record)

    async def health_check(self) -> bool:
        """健康检查"""
        if self._sandbox_mode:
            return True

        try:
            await self._get_access_token()
            return True
        except LLMError:
            return False
