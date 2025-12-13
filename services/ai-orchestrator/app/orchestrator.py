"""
NPC 对话编排器

核心职责：
1. 加载 NPC 人设
2. 检索相关知识
3. 构建 Prompt
4. 调用 LLM
5. 应用护栏检查
6. 管理会话记忆
"""

from typing import Any, Optional
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.llm import get_llm_client, LLMClient
from app.memory.session import SessionMemory
from app.prompts.builder import PromptBuilder
from app.retrieval.knowledge import KnowledgeRetriever
from app.guardrails.cultural import CulturalGuardrail

logger = get_logger(__name__)


class NPCOrchestrator:
    """NPC 对话编排器"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        knowledge_retriever: Optional[KnowledgeRetriever] = None,
        session_memory: Optional[SessionMemory] = None,
        guardrail: Optional[CulturalGuardrail] = None,
    ):
        self.llm = llm_client or get_llm_client()
        self.retriever = knowledge_retriever or KnowledgeRetriever()
        self.memory = session_memory or SessionMemory()
        self.guardrail = guardrail or CulturalGuardrail()
        self.prompt_builder = PromptBuilder()

    async def chat(
        self,
        npc_id: UUID,
        npc_persona: dict[str, Any],
        user_message: str,
        session_id: str,
        visitor_id: Optional[UUID] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        处理 NPC 对话请求

        Args:
            npc_id: NPC ID
            npc_persona: NPC 人设配置
            user_message: 用户消息
            session_id: 会话 ID
            visitor_id: 游客 ID（可选）
            context: 额外上下文（场景、时间等）

        Returns:
            对话响应，包含回复内容和元数据
        """
        logger.info(
            "processing_chat",
            npc_id=str(npc_id),
            session_id=session_id,
            message_length=len(user_message),
        )

        # 1. 获取会话历史
        history = await self.memory.get_history(session_id)

        # 2. 检索相关知识
        knowledge_domains = npc_persona.get("knowledge_domains", [])
        relevant_docs = await self.retriever.search(
            query=user_message,
            domains=knowledge_domains,
            top_k=3,
        )

        # 3. 构建 Prompt
        messages = self.prompt_builder.build(
            persona=npc_persona,
            user_message=user_message,
            history=history,
            retrieved_docs=relevant_docs,
            context=context,
        )

        # 4. 调用 LLM
        response = await self.llm.chat(
            messages=messages,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_RESPONSE_TOKENS,
        )

        # 5. 护栏检查
        guardrail_result = await self.guardrail.check(
            response=response.content,
            persona=npc_persona,
        )

        if not guardrail_result.passed:
            logger.warning(
                "guardrail_triggered",
                npc_id=str(npc_id),
                reason=guardrail_result.reason,
            )
            # 使用兜底回复
            fallback_responses = npc_persona.get("conversation_config", {}).get(
                "fallback_responses", ["抱歉，这个问题我不太清楚。"]
            )
            response_content = fallback_responses[0] if fallback_responses else "抱歉，请换个问题。"
        else:
            response_content = response.content

        # 6. 保存到会话记忆
        await self.memory.add_message(session_id, "user", user_message)
        await self.memory.add_message(session_id, "assistant", response_content)

        return {
            "content": response_content,
            "npc_id": str(npc_id),
            "session_id": session_id,
            "sources": [doc.get("title", "") for doc in relevant_docs],
            "guardrail_passed": guardrail_result.passed,
            "tokens_used": response.usage.total_tokens if response.usage else None,
        }

    async def get_greeting(
        self,
        npc_persona: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """获取 NPC 问候语"""
        templates = npc_persona.get("conversation_config", {}).get("greeting_templates", [])
        if templates:
            # TODO: 根据上下文选择合适的问候语
            return templates[0]
        return "你好！有什么可以帮助你的吗？"
