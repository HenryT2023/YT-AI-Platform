"""
证据链模块

提供证据链构建、验证、追溯能力
确保 NPC 输出的文化准确性可追溯
"""

from app.evidence.chain import EvidenceChainBuilder, EvidenceChainResult
from app.evidence.validator import EvidenceValidator, ValidationResult

__all__ = [
    "EvidenceChainBuilder",
    "EvidenceChainResult",
    "EvidenceValidator",
    "ValidationResult",
]
