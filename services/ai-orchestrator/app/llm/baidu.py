"""
百度 LLM Adapter

支持百度文心一言（ERNIE Bot）系列模型
v0.1.0: 占位实现，返回模拟响应
"""

import structlog
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.llm.base import BaseLLMAdapter, LLMResponse, Citation

logger = structlog.get_logger(__name__)


class BaiduLLMAdapter(BaseLLMAdapter):
    """
    百度 LLM Adapter

    v0.1.0: 占位实现
    后续版本将接入百度 ERNIE Bot API
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.BAIDU_API_KEY
        self.secret_key = secret_key or settings.BAIDU_SECRET_KEY
        self.model = model or settings.BAIDU_MODEL
        self._access_token: Optional[str] = None

    async def _get_access_token(self) -> str:
        """
        获取百度 API access_token

        TODO: 实现真实的 token 获取逻辑
        """
        if self._access_token:
            return self._access_token

        # v0.1.0: 占位实现
        logger.warning("baidu_llm_placeholder", message="Using placeholder implementation")
        return "placeholder_token"

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        生成回复

        v0.1.0: 占位实现，返回基于模板的模拟响应
        """
        log = logger.bind(model=self.model)
        log.info("baidu_llm_generate_start")

        # 构建引用信息
        citation_objects = []
        citation_text = ""

        if citations:
            for i, c in enumerate(citations):
                citation_objects.append(Citation(
                    evidence_id=c.get("id", f"evidence-{i}"),
                    title=c.get("title"),
                    source_ref=c.get("source_ref"),
                    excerpt=c.get("excerpt", "")[:100] if c.get("excerpt") else None,
                ))
                if c.get("title"):
                    citation_text += f"\n- {c['title']}"

        # v0.1.0: 占位实现 - 返回模拟响应
        # 根据用户问题生成简单的模板回复
        if self.api_key and self.secret_key:
            # TODO: 实现真实的百度 API 调用
            response_text = await self._call_baidu_api(
                system_prompt, user_message, context, citations, max_tokens, temperature
            )
        else:
            # 占位响应
            response_text = self._generate_placeholder_response(
                system_prompt, user_message, citations
            )

        log.info("baidu_llm_generate_complete", tokens=len(response_text))

        return LLMResponse(
            text=response_text,
            citations=citation_objects,
            tokens_used=len(response_text),  # 简化估算
            model=self.model,
            finish_reason="stop",
        )

    async def _call_baidu_api(
        self,
        system_prompt: str,
        user_message: str,
        context: Optional[Dict[str, Any]],
        citations: Optional[List[Dict[str, Any]]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """
        调用百度 ERNIE Bot API

        TODO: 实现真实的 API 调用
        """
        # 占位实现
        return self._generate_placeholder_response(system_prompt, user_message, citations)

    def _generate_placeholder_response(
        self,
        system_prompt: str,
        user_message: str,
        citations: Optional[List[Dict[str, Any]]],
    ) -> str:
        """生成占位响应"""
        # 提取 NPC 名称（从 system_prompt 中）
        npc_name = "我"
        if "你是" in system_prompt:
            start = system_prompt.find("你是") + 2
            end = system_prompt.find("。", start)
            if end > start:
                npc_name = system_prompt[start:end]

        # 构建响应
        if citations and len(citations) > 0:
            # 有证据时，引用证据回答
            first_citation = citations[0]
            response = f"关于您问的「{user_message[:20]}...」，{npc_name}可以告诉您：\n\n"
            if first_citation.get("excerpt"):
                response += first_citation["excerpt"][:200]
            else:
                response += f"根据{first_citation.get('title', '相关记载')}，这个问题涉及到我们的历史传承。"

            if first_citation.get("title"):
                response += f"\n\n（参考：{first_citation['title']}）"
        else:
            # 无证据时，返回保守回答
            response = f"这个问题{npc_name}不太清楚，建议您询问村中其他长辈或查阅相关文献。"

        return response

    async def health_check(self) -> bool:
        """健康检查"""
        # v0.1.0: 总是返回 True
        return True
