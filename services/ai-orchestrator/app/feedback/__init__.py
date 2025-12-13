"""
反馈模块

提供用户纠错闭环功能
"""

from app.feedback.client import (
    FeedbackClient,
    FeedbackSubmission,
    FeedbackResult,
    get_feedback_client,
)

__all__ = [
    "FeedbackClient",
    "FeedbackSubmission",
    "FeedbackResult",
    "get_feedback_client",
]
