"""
MCP 工具客户端

负责调用 core-backend 的 MCP 工具 API
"""

import uuid
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.mcp.protocol import MCPToolCall, MCPToolResult, MCPToolDefinition, MCPToolStatus

logger = get_logger(__name__)


class MCPToolClientError(Exception):
    """MCP 工具客户端错误"""

    def __init__(self, message: str, error_code: str = "CLIENT_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class MCPToolClient:
    """MCP 工具客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        internal_api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url or settings.CORE_BACKEND_URL
        self.internal_api_key = internal_api_key or settings.INTERNAL_API_KEY
        self.timeout = timeout
        self._tool_definitions: Optional[List[MCPToolDefinition]] = None

    async def get_tool_definitions(
        self,
        category: Optional[str] = None,
        ai_callable_only: bool = True,
        force_refresh: bool = False,
    ) -> List[MCPToolDefinition]:
        """
        获取可用的工具定义列表

        Args:
            category: 工具类别过滤
            ai_callable_only: 仅返回 AI 可调用的工具
            force_refresh: 强制刷新缓存

        Returns:
            工具定义列表
        """
        if self._tool_definitions and not force_refresh:
            tools = self._tool_definitions
            if category:
                tools = [t for t in tools if t.category == category]
            if ai_callable_only:
                tools = [t for t in tools if t.ai_callable]
            return tools

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            params = {"ai_callable_only": ai_callable_only}
            if category:
                params["category"] = category

            response = await client.get(
                f"{self.base_url}/api/v1/mcp-tools/definitions",
                params=params,
            )

            if response.status_code != 200:
                raise MCPToolClientError(
                    f"Failed to get tool definitions: {response.text}",
                    error_code="GET_DEFINITIONS_FAILED",
                )

            data = response.json()
            self._tool_definitions = [
                MCPToolDefinition.from_dict(item) for item in data
            ]

            return self._tool_definitions

    async def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取 OpenAI function calling 格式的工具列表"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/mcp-tools/openai-format",
            )

            if response.status_code != 200:
                raise MCPToolClientError(
                    f"Failed to get OpenAI tools: {response.text}",
                    error_code="GET_OPENAI_TOOLS_FAILED",
                )

            return response.json()

    async def execute(
        self,
        tool_call: MCPToolCall,
        auth_token: Optional[str] = None,
    ) -> MCPToolResult:
        """
        执行 MCP 工具调用

        Args:
            tool_call: 工具调用请求
            auth_token: 用户认证令牌（如果有）

        Returns:
            工具调用结果
        """
        logger.info(
            "executing_mcp_tool",
            tool_name=tool_call.tool_name,
            trace_id=tool_call.trace_id,
        )

        headers = {
            "X-Trace-ID": tool_call.trace_id,
            "X-Internal-API-Key": self.internal_api_key,
        }

        if tool_call.tenant_id:
            headers["X-Tenant-ID"] = tool_call.tenant_id
        if tool_call.site_id:
            headers["X-Site-ID"] = tool_call.site_id
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        request_body = {
            "tool_name": tool_call.tool_name,
            "params": tool_call.params,
            "session_id": tool_call.session_id,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/mcp-tools/execute/internal",
                    json=request_body,
                    headers=headers,
                )

                if response.status_code == 401:
                    return MCPToolResult(
                        tool_name=tool_call.tool_name,
                        status=MCPToolStatus.FAILED,
                        trace_id=tool_call.trace_id,
                        error="Authentication failed",
                        error_code="AUTH_FAILED",
                    )

                data = response.json()
                result = MCPToolResult.from_api_response(data)

                logger.info(
                    "mcp_tool_executed",
                    tool_name=tool_call.tool_name,
                    trace_id=tool_call.trace_id,
                    success=result.success,
                    duration_ms=result.duration_ms,
                )

                return result

        except httpx.TimeoutException:
            logger.error(
                "mcp_tool_timeout",
                tool_name=tool_call.tool_name,
                trace_id=tool_call.trace_id,
            )
            return MCPToolResult(
                tool_name=tool_call.tool_name,
                status=MCPToolStatus.TIMEOUT,
                trace_id=tool_call.trace_id,
                error="Tool execution timed out",
                error_code="TIMEOUT",
            )

        except Exception as e:
            logger.error(
                "mcp_tool_error",
                tool_name=tool_call.tool_name,
                trace_id=tool_call.trace_id,
                error=str(e),
            )
            return MCPToolResult(
                tool_name=tool_call.tool_name,
                status=MCPToolStatus.FAILED,
                trace_id=tool_call.trace_id,
                error=str(e),
                error_code="CLIENT_ERROR",
            )

    async def execute_batch(
        self,
        tool_calls: List[MCPToolCall],
        auth_token: Optional[str] = None,
    ) -> List[MCPToolResult]:
        """批量执行工具调用"""
        import asyncio

        tasks = [self.execute(call, auth_token) for call in tool_calls]
        return await asyncio.gather(*tasks)


# 全局客户端实例
_mcp_client: Optional[MCPToolClient] = None


def get_mcp_client() -> MCPToolClient:
    """获取 MCP 工具客户端单例"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPToolClient()
    return _mcp_client
