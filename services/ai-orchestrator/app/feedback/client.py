"""
Feedback Client

用于 ai-orchestrator 向 core-backend 提交用户反馈
"""

import httpx
import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

logger = structlog.get_logger(__name__)


class FeedbackSubmission(BaseModel):
    """反馈提交请求"""
    trace_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    feedback_type: str = "correction"
    severity: str = "medium"
    content: str
    original_response: Optional[str] = None
    suggested_fix: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    tenant_id: str = "yantian"
    site_id: str = "yantian-main"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeedbackResult(BaseModel):
    """反馈提交结果"""
    feedback_id: str
    status: str
    created_at: datetime


class FeedbackClient:
    """
    反馈客户端

    用于向 core-backend 提交用户反馈
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = base_url or settings.CORE_BACKEND_URL
        self.timeout = timeout

    async def submit_feedback(
        self,
        submission: FeedbackSubmission,
    ) -> Optional[FeedbackResult]:
        """
        提交反馈

        Args:
            submission: 反馈提交请求

        Returns:
            FeedbackResult 或 None（失败时）
        """
        log = logger.bind(
            trace_id=submission.trace_id,
            feedback_type=submission.feedback_type,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/feedback",
                    json=submission.model_dump(),
                    headers={
                        "Content-Type": "application/json",
                        "X-Internal-API-Key": settings.INTERNAL_API_KEY,
                    },
                )

                if response.status_code == 201:
                    data = response.json()
                    log.info("feedback_submitted", feedback_id=data.get("id"))
                    return FeedbackResult(
                        feedback_id=data["id"],
                        status=data["status"],
                        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
                    )
                else:
                    log.error(
                        "feedback_submit_failed",
                        status_code=response.status_code,
                        response=response.text[:200],
                    )
                    return None

        except Exception as e:
            log.error("feedback_submit_error", error=str(e))
            return None

    async def submit_correction(
        self,
        trace_id: str,
        content: str,
        original_response: str,
        suggested_fix: Optional[str] = None,
        severity: str = "medium",
        tenant_id: str = "yantian",
        site_id: str = "yantian-main",
        npc_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[FeedbackResult]:
        """
        提交纠错反馈（便捷方法）

        Args:
            trace_id: 关联的 trace ID
            content: 纠错内容
            original_response: 原始回答
            suggested_fix: 建议的修正
            severity: 严重程度
            tenant_id: 租户 ID
            site_id: 站点 ID
            npc_id: NPC ID
            conversation_id: 会话 ID

        Returns:
            FeedbackResult 或 None
        """
        submission = FeedbackSubmission(
            trace_id=trace_id,
            conversation_id=conversation_id,
            feedback_type="correction",
            severity=severity,
            content=content,
            original_response=original_response,
            suggested_fix=suggested_fix,
            tags=["auto_correction", f"npc:{npc_id}"] if npc_id else ["auto_correction"],
            tenant_id=tenant_id,
            site_id=site_id,
            metadata={"npc_id": npc_id, "source": "ai_orchestrator"},
        )
        return await self.submit_feedback(submission)


# 全局实例
_client_instance: Optional[FeedbackClient] = None


def get_feedback_client() -> FeedbackClient:
    """获取反馈客户端实例"""
    global _client_instance
    if _client_instance is None:
        _client_instance = FeedbackClient()
    return _client_instance
