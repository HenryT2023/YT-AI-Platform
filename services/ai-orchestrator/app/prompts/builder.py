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

{% if env_context %}
## 当前环境感知
- 节气：{{ env_context.solar_term.name }}{% if env_context.solar_term.farming_advice %}（{{ env_context.solar_term.farming_advice[:50] }}...）{% endif %}

- 时段：{{ env_context.time_of_day_cn }}（{{ env_context.current_time }}）
{% if env_context.solar_term.poem %}
- 应景诗词：{{ env_context.solar_term.poem }}
{% endif %}
{% endif %}

{% if user_context and not user_context.is_anonymous %}
## 游客信息
- 称呼：{{ user_context.name or "游客" }}
{% if user_context.tags %}
- 兴趣标签：{{ user_context.tags | join('、') }}
{% endif %}
{% if user_context.stats %}
- 已完成任务：{{ user_context.stats.quest_completed_count }}个
- 打卡次数：{{ user_context.stats.check_in_count }}次
{% endif %}
{% if user_context.recent_quests %}
- 最近完成：{{ user_context.recent_quests | join('、') }}
{% endif %}
{% if user_context.unlocked_achievements %}
- 已获成就：{{ user_context.unlocked_achievements[:3] | join('、') }}
{% endif %}
{% endif %}

{% if dialogue_strategy %}
## 对话策略
{{ dialogue_strategy }}
{% endif %}

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

        # 1. 构建 System Prompt（包含上下文感知）
        system_prompt = self._build_system_prompt(persona, retrieved_docs, context)
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
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """构建 System Prompt（支持上下文感知）"""
        # 提取人设信息
        identity = persona.get("identity", {})
        personality = persona.get("personality", {})
        constraints = persona.get("constraints", {})
        conversation_config = persona.get("conversation_config", {})

        # 提取上下文信息
        user_context = context.get("user") if context else None
        env_context = context.get("environment") if context else None

        # 生成对话策略
        dialogue_strategy = self._generate_dialogue_strategy(user_context, env_context)

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
            "user_context": user_context,
            "env_context": env_context,
            "dialogue_strategy": dialogue_strategy,
        }

        return self.system_template.render(**template_vars)

    def _generate_dialogue_strategy(
        self,
        user_context: Optional[dict[str, Any]],
        env_context: Optional[dict[str, Any]],
    ) -> Optional[str]:
        """根据上下文生成对话策略提示"""
        if not user_context and not env_context:
            return None

        strategies = []

        # 基于用户画像的策略
        if user_context:
            tags = user_context.get("tags", [])
            stats = user_context.get("stats", {})
            quest_count = stats.get("quest_completed_count", 0)

            if quest_count == 0:
                strategies.append("这是新游客，请热情欢迎并介绍基础任务和景点。")
            elif quest_count >= 5:
                strategies.append("这是资深游客，可以推荐更有深度的文化内容。")

            if "亲子" in tags:
                strategies.append("游客带着孩子，请用通俗易懂的语言，多讲有趣的故事。")
            if "摄影" in tags or "摄影爱好者" in tags:
                strategies.append("游客喜欢摄影，可以推荐最佳拍摄点和光线时机。")
            if "历史" in tags or "文化" in tags:
                strategies.append("游客对历史文化感兴趣，可以深入讲解徽派文化和家族故事。")

        # 基于环境的策略
        if env_context:
            solar_term = env_context.get("solar_term", {})
            term_code = solar_term.get("code")
            time_of_day = env_context.get("time_of_day")

            if term_code:
                strategies.append(f"当前是{solar_term.get('name')}节气，可以主动提及相关的农耕习俗和养生知识。")

            if time_of_day == "night":
                strategies.append("现在是夜间，可以讲述夜游祠堂的神秘故事。")
            elif time_of_day == "early_morning":
                strategies.append("现在是清晨，可以介绍晨起养生和田园风光。")

        return "\n".join(strategies) if strategies else None
