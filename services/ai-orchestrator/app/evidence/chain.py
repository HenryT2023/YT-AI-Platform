"""
证据链构建器

从 MCP 工具调用结果中构建证据链
用于追溯 NPC 输出的来源
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.logging import get_logger
from app.mcp.protocol import MCPToolResult
from app.mcp.schemas import EvidenceItem, EvidenceChain

logger = get_logger(__name__)


@dataclass
class EvidenceChainResult:
    """证据链构建结果"""

    trace_id: str
    evidence_chain: EvidenceChain
    has_sufficient_evidence: bool
    confidence_score: float
    warnings: List[str] = field(default_factory=list)

    @property
    def should_use_fallback(self) -> bool:
        """是否应该使用保守回答"""
        return not self.has_sufficient_evidence or self.confidence_score < 0.5


class EvidenceChainBuilder:
    """证据链构建器"""

    def __init__(
        self,
        min_evidence_count: int = 1,
        min_confidence_threshold: float = 0.5,
        require_verified: bool = False,
    ):
        """
        初始化证据链构建器

        Args:
            min_evidence_count: 最少需要的证据数量
            min_confidence_threshold: 最低可信度阈值
            require_verified: 是否要求至少有一条经过验证的证据
        """
        self.min_evidence_count = min_evidence_count
        self.min_confidence_threshold = min_confidence_threshold
        self.require_verified = require_verified

    def build_from_tool_results(
        self,
        tool_results: List[MCPToolResult],
        trace_id: Optional[str] = None,
    ) -> EvidenceChainResult:
        """
        从工具调用结果构建证据链

        Args:
            tool_results: MCP 工具调用结果列表
            trace_id: 追踪 ID

        Returns:
            证据链构建结果
        """
        trace_id = trace_id or str(uuid4())
        evidences: List[EvidenceItem] = []
        evidence_ids: List[str] = []
        warnings: List[str] = []

        for result in tool_results:
            if not result.success:
                warnings.append(f"Tool {result.tool_name} failed: {result.error}")
                continue

            # 从结果中提取证据
            extracted = self._extract_evidences(result)
            evidences.extend(extracted)
            evidence_ids.extend([e.id for e in extracted])

        # 构建证据链
        chain = EvidenceChain(
            trace_id=trace_id,
            evidence_ids=evidence_ids,
            evidences=evidences,
        )
        chain.compute_credibility()

        # 评估证据充分性
        has_sufficient = self._evaluate_sufficiency(chain, warnings)
        confidence = chain.total_credibility

        logger.info(
            "evidence_chain_built",
            trace_id=trace_id,
            evidence_count=len(evidences),
            confidence=confidence,
            has_sufficient=has_sufficient,
        )

        return EvidenceChainResult(
            trace_id=trace_id,
            evidence_chain=chain,
            has_sufficient_evidence=has_sufficient,
            confidence_score=confidence,
            warnings=warnings,
        )

    def _extract_evidences(self, result: MCPToolResult) -> List[EvidenceItem]:
        """从工具结果中提取证据"""
        evidences = []

        if not result.result:
            return evidences

        # 处理 knowledge.search 结果
        if result.tool_name == "knowledge.search":
            for item in result.result.get("results", []):
                evidences.append(
                    EvidenceItem(
                        id=item.get("id", ""),
                        title=item.get("title", ""),
                        content_snippet=item.get("content", "")[:500],
                        source=item.get("source"),
                        credibility_score=item.get("credibility_score", 0.8),
                        verified=item.get("verified", False),
                        knowledge_type=item.get("knowledge_type"),
                    )
                )

        # 处理 solar_term.get_current 结果
        elif result.tool_name == "solar_term.get_current":
            farming_wisdom = result.result.get("farming_wisdom", [])
            for item in farming_wisdom:
                evidences.append(
                    EvidenceItem(
                        id=item.get("id", str(uuid4())),
                        title=item.get("title", result.result.get("term", "")),
                        content_snippet=item.get("content", "")[:500],
                        source=item.get("source", "节气知识库"),
                        credibility_score=item.get("credibility_score", 0.9),
                        verified=item.get("verified", True),
                        knowledge_type="solar_term",
                    )
                )

        return evidences

    def _evaluate_sufficiency(
        self,
        chain: EvidenceChain,
        warnings: List[str],
    ) -> bool:
        """评估证据是否充分"""

        # 检查证据数量
        if len(chain.evidences) < self.min_evidence_count:
            warnings.append(
                f"Insufficient evidence: {len(chain.evidences)} < {self.min_evidence_count}"
            )
            return False

        # 检查可信度
        if chain.total_credibility < self.min_confidence_threshold:
            warnings.append(
                f"Low confidence: {chain.total_credibility:.2f} < {self.min_confidence_threshold}"
            )
            return False

        # 检查是否需要验证过的证据
        if self.require_verified and not chain.has_verified_evidence:
            warnings.append("No verified evidence found")
            return False

        return True

    def build_from_knowledge_results(
        self,
        knowledge_results: List[Dict[str, Any]],
        trace_id: Optional[str] = None,
    ) -> EvidenceChainResult:
        """
        直接从知识检索结果构建证据链

        Args:
            knowledge_results: 知识检索结果列表
            trace_id: 追踪 ID

        Returns:
            证据链构建结果
        """
        trace_id = trace_id or str(uuid4())
        evidences: List[EvidenceItem] = []
        warnings: List[str] = []

        for item in knowledge_results:
            evidences.append(
                EvidenceItem(
                    id=item.get("id", str(uuid4())),
                    title=item.get("title", ""),
                    content_snippet=item.get("content", "")[:500],
                    source=item.get("source"),
                    credibility_score=item.get("credibility_score", 0.8),
                    verified=item.get("verified", False),
                    knowledge_type=item.get("knowledge_type"),
                )
            )

        chain = EvidenceChain(
            trace_id=trace_id,
            evidence_ids=[e.id for e in evidences],
            evidences=evidences,
        )
        chain.compute_credibility()

        has_sufficient = self._evaluate_sufficiency(chain, warnings)

        return EvidenceChainResult(
            trace_id=trace_id,
            evidence_chain=chain,
            has_sufficient_evidence=has_sufficient,
            confidence_score=chain.total_credibility,
            warnings=warnings,
        )
