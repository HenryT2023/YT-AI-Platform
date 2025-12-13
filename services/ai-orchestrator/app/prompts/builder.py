"""
Prompt 构建器

根据 NPC 人设、用户消息、历史记录、检索文档构建完整的 Prompt
"""

from typing import Any, List, Optional

from jinja2 import Template

from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是{{ display_name }}，{{ identity.role }}。

## 身份背景
{{ identity.background }}

## 性格特点
- 性格特征：{{ personality.traits | join('、') }}
- 说话风格：{{ personality.speaking_style }}
{% if personality.catchphrases %}
- 口头禅：{{ personality.catchphrases | join('；') }}
{% endif %}

## 知识领域
你擅长以下领域：{{ knowledge_domains | join('、') }}

## 约束规则
1. 你必须始终保持角色一致性，以{{ display_name }}的身份回答问题
2. 你的回答应该符合{{ identity.era }}的时代背景
3. 对于不确定的内容，请诚实说明"这个老夫不太清楚"或类似表达
4. 禁止讨论以下话题：{{ constraints.forbidden_topics | join('、') }}
5. 回答要简洁有力，不超过{{ max_response_length }}字
{% if constraints.must_cite_sources %}
6. 涉及历史事实时，尽量说明来源或依据
{% endif %}

{% if retrieved_context %}
## 参考资料
以下是与用户问题相关的资料，你可以参考但不要直接复制：
{% for doc in retrieved_context %}
---
{{ doc.content }}
---
{% endfor %}
{% endif %}

请以{{ display_name }}的身份，用符合角色的语气回答用户的问题。"""


class PromptBuilder:
    """Prompt 构建器"""

    def __init__(self):
        self.system_template = Template(SYSTEM_PROMPT_TEMPLATE)

    def build(
        self,
        persona: dict[str, Any],
        user_message: str,
        history: Optional[List[dict[str, str]]] = None,
        retrieved_docs: Optional[List[dict[str, Any]]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> List[dict[str, str]]:
        """
        构建完整的消息列表

        Args:
            persona: NPC 人设配置
            user_message: 用户当前消息
            history: 历史对话记录
            retrieved_docs: 检索到的相关文档
            context: 额外上下文

        Returns:
            OpenAI 格式的消息列表
        """
        messages = []

        # 1. 构建 System Prompt
        system_prompt = self._build_system_prompt(persona, retrieved_docs)
        messages.append({"role": "system", "content": system_prompt})

        # 2. 添加历史对话
        if history:
            for msg in history[-10:]:  # 只保留最近 10 轮
                messages.append({"role": msg["role"], "content": msg["content"]})

        # 3. 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            "prompt_built",
            system_length=len(system_prompt),
            history_count=len(history) if history else 0,
            message_count=len(messages),
        )

        return messages

    def _build_system_prompt(
        self,
        persona: dict[str, Any],
        retrieved_docs: Optional[List[dict[str, Any]]] = None,
    ) -> str:
        """构建 System Prompt"""
        # 提取人设信息
        identity = persona.get("identity", {})
        personality = persona.get("personality", {})
        constraints = persona.get("constraints", {})
        conversation_config = persona.get("conversation_config", {})

        # 准备模板变量
        template_vars = {
            "display_name": persona.get("display_name", "AI 助手"),
            "identity": identity,
            "personality": personality,
            "knowledge_domains": persona.get("knowledge_domains", []),
            "constraints": {
                "forbidden_topics": constraints.get("forbidden_topics", ["政治敏感", "色情暴力"]),
                "must_cite_sources": constraints.get("must_cite_sources", False),
            },
            "max_response_length": conversation_config.get("max_response_length", 500),
            "retrieved_context": retrieved_docs,
        }

        return self.system_template.render(**template_vars)
