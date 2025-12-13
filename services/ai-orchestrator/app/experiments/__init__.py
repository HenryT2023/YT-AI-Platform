"""
实验分桶客户端

调用 core-backend 的实验 API 获取分桶分配
"""

from app.experiments.client import ExperimentClient, ExperimentAssignment, get_experiment_client

__all__ = ["ExperimentClient", "ExperimentAssignment", "get_experiment_client"]
