"""
护栏测试
"""

import pytest

from app.guardrails.cultural import CulturalGuardrail


@pytest.fixture
def guardrail():
    return CulturalGuardrail()


@pytest.fixture
def historical_persona():
    return {
        "display_name": "严氏先祖",
        "constraints": {
            "forbidden_topics": ["政治敏感"],
            "time_awareness": "historical",
        },
        "conversation_config": {
            "max_response_length": 500,
        },
    }


@pytest.mark.asyncio
async def test_guardrail_passes_clean_response(guardrail, historical_persona):
    """测试正常响应通过护栏"""
    response = "吾严氏家训有云：读书明理，勤俭持家。此乃祖宗之法，不可轻废。"
    result = await guardrail.check(response, historical_persona)
    assert result.passed is True


@pytest.mark.asyncio
async def test_guardrail_blocks_forbidden_words(guardrail, historical_persona):
    """测试禁用词被拦截"""
    response = "关于政治敏感话题，老夫不便多言。"
    result = await guardrail.check(response, historical_persona)
    assert result.passed is False
    assert "禁用词" in result.reason


@pytest.mark.asyncio
async def test_guardrail_blocks_anachronism(guardrail, historical_persona):
    """测试时代不一致被拦截"""
    response = "你可以用手机查一下这个问题。"
    result = await guardrail.check(response, historical_persona)
    assert result.passed is False
    assert "时代不一致" in result.reason


@pytest.mark.asyncio
async def test_guardrail_allows_contemporary_npc(guardrail):
    """测试当代 NPC 可以提及现代事物"""
    contemporary_persona = {
        "display_name": "木雕师傅",
        "constraints": {
            "time_awareness": "contemporary",
        },
        "conversation_config": {
            "max_response_length": 500,
        },
    }
    response = "现在很多人用手机拍照记录木雕作品。"
    result = await guardrail.check(response, contemporary_persona)
    assert result.passed is True
