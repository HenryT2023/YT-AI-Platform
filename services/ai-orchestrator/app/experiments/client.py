"""
实验分桶客户端

调用 core-backend 的实验 API：
- GET /v1/experiments/active - 获取活跃实验
- GET /v1/experiments/assign - 分桶分配
"""

import structlog
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = structlog.get_logger(__name__)

# 默认配置
DEFAULT_TIMEOUT = 2.0  # 2 秒超时
DEFAULT_RETRIES = 1


@dataclass
class ExperimentAssignment:
    """实验分桶结果"""
    experiment_id: str
    experiment_name: str
    variant: str
    bucket_hash: int
    strategy_overrides: Dict[str, Any] = field(default_factory=dict)
    is_new_assignment: bool = False
    error: Optional[str] = None
    
    @classmethod
    def default_control(cls, error: Optional[str] = None) -> "ExperimentAssignment":
        """返回默认 control 分桶（降级）"""
        return cls(
            experiment_id="",
            experiment_name="",
            variant="control",
            bucket_hash=0,
            strategy_overrides={},
            is_new_assignment=False,
            error=error,
        )


@dataclass
class ActiveExperiment:
    """活跃实验"""
    id: str
    name: str
    status: str
    config: Dict[str, Any]


class ExperimentClient:
    """
    实验分桶客户端
    
    调用 core-backend 的实验 API
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ):
        self.base_url = base_url or settings.CORE_BACKEND_URL
        self.timeout = timeout
        self.retries = retries
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def get_active_experiments(
        self,
        tenant_id: str,
        site_id: str,
    ) -> List[ActiveExperiment]:
        """
        获取活跃实验列表
        
        Args:
            tenant_id: 租户 ID
            site_id: 站点 ID
            
        Returns:
            活跃实验列表
        """
        log = logger.bind(tenant_id=tenant_id, site_id=site_id)
        
        try:
            client = await self._get_client()
            resp = await client.get(
                "/v1/experiments/active",
                params={
                    "tenant_id": tenant_id,
                    "site_id": site_id,
                },
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return [
                    ActiveExperiment(
                        id=exp["id"],
                        name=exp["name"],
                        status=exp["status"],
                        config=exp.get("config", {}),
                    )
                    for exp in data
                ]
            else:
                log.warning("get_active_experiments_failed", status=resp.status_code)
                return []
                
        except Exception as e:
            log.error("get_active_experiments_error", error=str(e))
            return []
    
    async def assign(
        self,
        experiment_id: str,
        tenant_id: str,
        site_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ExperimentAssignment:
        """
        获取实验分桶分配
        
        稳定分桶：同一 subject_key 在同一实验中永远返回相同 variant
        
        Args:
            experiment_id: 实验 ID
            tenant_id: 租户 ID
            site_id: 站点 ID
            session_id: 会话 ID（优先）
            user_id: 用户 ID
            
        Returns:
            ExperimentAssignment
        """
        log = logger.bind(
            experiment_id=experiment_id,
            tenant_id=tenant_id,
            session_id=session_id,
        )
        
        # 必须有 session_id 或 user_id
        if not session_id and not user_id:
            log.warning("assign_missing_subject_key")
            return ExperimentAssignment.default_control("missing_subject_key")
        
        for attempt in range(self.retries + 1):
            try:
                client = await self._get_client()
                resp = await client.get(
                    "/v1/experiments/assign",
                    params={
                        "experiment_id": experiment_id,
                        "tenant_id": tenant_id,
                        "site_id": site_id,
                        "session_id": session_id,
                        "user_id": user_id,
                    },
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    log.info(
                        "experiment_assigned",
                        variant=data["variant"],
                        bucket_hash=data["bucket_hash"],
                    )
                    return ExperimentAssignment(
                        experiment_id=data["experiment_id"],
                        experiment_name=data["experiment_name"],
                        variant=data["variant"],
                        bucket_hash=data["bucket_hash"],
                        strategy_overrides=data.get("strategy_overrides", {}),
                        is_new_assignment=data.get("is_new_assignment", False),
                    )
                elif resp.status_code == 400:
                    # 实验未激活或参数错误
                    error_detail = resp.json().get("detail", "bad_request")
                    log.warning("assign_bad_request", detail=error_detail)
                    return ExperimentAssignment.default_control(error_detail)
                elif resp.status_code == 404:
                    log.warning("assign_experiment_not_found")
                    return ExperimentAssignment.default_control("experiment_not_found")
                else:
                    log.warning("assign_failed", status=resp.status_code)
                    
            except httpx.TimeoutException:
                log.warning("assign_timeout", attempt=attempt)
            except Exception as e:
                log.error("assign_error", error=str(e), attempt=attempt)
        
        # 所有重试失败，返回默认 control
        return ExperimentAssignment.default_control("api_unavailable")
    
    async def assign_first_active(
        self,
        tenant_id: str,
        site_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ExperimentAssignment:
        """
        获取第一个活跃实验的分桶分配
        
        便捷方法：自动获取活跃实验并分配
        
        Args:
            tenant_id: 租户 ID
            site_id: 站点 ID
            session_id: 会话 ID（优先）
            user_id: 用户 ID
            
        Returns:
            ExperimentAssignment
        """
        # 获取活跃实验
        active_experiments = await self.get_active_experiments(tenant_id, site_id)
        
        if not active_experiments:
            return ExperimentAssignment.default_control("no_active_experiment")
        
        # 使用第一个活跃实验
        experiment = active_experiments[0]
        
        return await self.assign(
            experiment_id=experiment.id,
            tenant_id=tenant_id,
            site_id=site_id,
            session_id=session_id,
            user_id=user_id,
        )


# 单例
_experiment_client: Optional[ExperimentClient] = None


def get_experiment_client() -> ExperimentClient:
    """获取实验客户端单例"""
    global _experiment_client
    if _experiment_client is None:
        _experiment_client = ExperimentClient()
    return _experiment_client
