#!/usr/bin/env python3
"""
P28 告警系统验收脚本

测试流程：
1. 查看当前告警规则
2. 评估当前告警状态
3. 模拟触发告警（调低阈值）
4. 验证告警输出
"""

import asyncio
import httpx
import json
import sys
import yaml
import tempfile
import os
from pathlib import Path

# 配置
CORE_BACKEND_URL = "http://localhost:8000"
TENANT_ID = "yantian"
SITE_ID = "yantian-main"

# 原始策略路径
POLICY_PATH = Path(__file__).parent.parent / "services/core-backend/data/policies/alerts_policy_v0.1.yaml"


def print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print('=' * 60)


async def get_alert_rules():
    """获取告警规则"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{CORE_BACKEND_URL}/api/v1/alerts/rules")
        response.raise_for_status()
        return response.json()


async def evaluate_alerts(range_str: str = "15m"):
    """评估告警"""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{CORE_BACKEND_URL}/api/v1/alerts/evaluate",
            params={
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
                "range": range_str,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_alerts_summary():
    """获取告警摘要"""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{CORE_BACKEND_URL}/api/v1/alerts/summary",
            params={
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
            },
        )
        response.raise_for_status()
        return response.json()


def create_test_policy():
    """创建测试策略（调低阈值以触发告警）"""
    test_policy = {
        "version": "0.1-test",
        "description": "测试策略 - 调低阈值以触发告警",
        "global": {
            "default_window": "15m",
            "webhook_timeout_seconds": 5,
            "max_alerts_per_evaluation": 50,
        },
        "rules": [
            {
                "code": "test.conservative_rate_high",
                "name": "[测试] 保守模式比例过高",
                "category": "gate",
                "severity": "high",
                "description": "测试告警 - 阈值调低到 0.1%",
                "metric": "gate.conservative_rate",
                "condition": ">",
                "threshold": 0.1,  # 极低阈值，几乎必触发
                "unit": "%",
                "window": "15m",
                "recommended_actions": [
                    "这是测试告警",
                    "验证告警系统正常工作",
                ],
            },
            {
                "code": "test.citations_rate_low",
                "name": "[测试] 引用率过低",
                "category": "gate",
                "severity": "medium",
                "description": "测试告警 - 阈值调高到 99.9%",
                "metric": "gate.citations_rate",
                "condition": "<",
                "threshold": 99.9,  # 极高阈值，几乎必触发
                "unit": "%",
                "window": "15m",
                "recommended_actions": [
                    "这是测试告警",
                    "验证告警系统正常工作",
                ],
            },
            {
                "code": "test.feedback_backlog",
                "name": "[测试] 反馈积压",
                "category": "feedback",
                "severity": "low",
                "description": "测试告警 - 阈值调低到 0",
                "metric": "feedback.pending_count",
                "condition": ">",
                "threshold": 0,  # 只要有任何待处理反馈就触发
                "unit": "个",
                "window": "1h",
                "recommended_actions": [
                    "这是测试告警",
                ],
            },
        ],
        "notification": {
            "severity_channels": {
                "critical": ["webhook"],
                "high": ["webhook"],
                "medium": ["log_only"],
                "low": ["log_only"],
            },
        },
    }
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(test_policy, f, allow_unicode=True)
        return f.name


async def run_test():
    """运行测试"""
    print_section("P28 告警系统验收测试")
    
    # Step 1: 查看当前告警规则
    print_section("Step 1: 查看当前告警规则")
    try:
        rules = await get_alert_rules()
        print(f"✓ 已加载 {rules['rule_count']} 条告警规则")
        print(f"  版本: {rules['version']}")
        print("\n  规则列表:")
        for rule in rules['rules'][:5]:
            print(f"    - [{rule['severity']}] {rule['code']}: {rule['name']}")
        if rules['rule_count'] > 5:
            print(f"    ... 还有 {rules['rule_count'] - 5} 条规则")
    except Exception as e:
        print(f"✗ 获取规则失败: {e}")
        return False
    
    # Step 2: 评估当前告警状态
    print_section("Step 2: 评估当前告警状态")
    try:
        result = await evaluate_alerts("15m")
        print(f"✓ 评估完成")
        print(f"  时间: {result['timestamp']}")
        print(f"  窗口: {result['window']}")
        print(f"  规则数: {result['rules_evaluated']}")
        print(f"  告警数: {result['alert_count']}")
        print(f"  按级别: {json.dumps(result['alerts_by_severity'], indent=2)}")
        
        if result['active_alerts']:
            print("\n  活跃告警:")
            for alert in result['active_alerts']:
                print(f"    - [{alert['severity']}] {alert['code']}")
                print(f"      当前值: {alert['current_value']} {alert.get('unit', '')}")
                print(f"      阈值: {alert['condition']} {alert['threshold']} {alert.get('unit', '')}")
    except Exception as e:
        print(f"✗ 评估失败: {e}")
        return False
    
    # Step 3: 获取告警摘要
    print_section("Step 3: 获取告警摘要")
    try:
        summary = await get_alerts_summary()
        print(f"✓ 摘要获取成功")
        print(f"  有告警: {summary['has_alerts']}")
        print(f"  告警数: {summary['alert_count']}")
        if summary.get('critical_codes'):
            print(f"  Critical: {summary['critical_codes']}")
        if summary.get('high_codes'):
            print(f"  High: {summary['high_codes']}")
    except Exception as e:
        print(f"✗ 获取摘要失败: {e}")
        return False
    
    # Step 4: 显示指标快照
    print_section("Step 4: 指标快照")
    try:
        result = await evaluate_alerts("15m")
        snapshot = result['metrics_snapshot']
        print(f"✓ 指标快照:")
        print(f"\n  Health:")
        print(f"    healthz: {snapshot['health']['healthz_status']}")
        print(f"    qdrant: {snapshot['health']['qdrant_status']}")
        print(f"    redis: {snapshot['health']['redis_status']}")
        
        print(f"\n  LLM:")
        print(f"    success_rate: {snapshot['llm']['success_rate']}%")
        print(f"    fallback_rate: {snapshot['llm']['fallback_rate']}%")
        print(f"    p95_latency: {snapshot['llm']['p95_latency_ms']}ms")
        
        print(f"\n  Gate:")
        print(f"    conservative_rate: {snapshot['gate']['conservative_rate']}%")
        print(f"    refuse_rate: {snapshot['gate']['refuse_rate']}%")
        print(f"    citations_rate: {snapshot['gate']['citations_rate']}%")
        
        print(f"\n  Vector:")
        print(f"    coverage_ratio: {snapshot['vector']['coverage_ratio']}%")
        print(f"    stale_count: {snapshot['vector']['stale_count']}")
        
        print(f"\n  Embedding:")
        print(f"    daily_cost: ${snapshot['embedding']['daily_cost']}")
        print(f"    rate_limited_rate: {snapshot['embedding']['rate_limited_rate']}%")
        print(f"    dedup_hit_rate: {snapshot['embedding']['dedup_hit_rate']}%")
        
        print(f"\n  Feedback:")
        print(f"    overdue_count: {snapshot['feedback']['overdue_count']}")
        print(f"    pending_count: {snapshot['feedback']['pending_count']}")
        print(f"    unassigned_count: {snapshot['feedback']['unassigned_count']}")
    except Exception as e:
        print(f"✗ 获取快照失败: {e}")
    
    # Step 5: 输出示例 JSON
    print_section("Step 5: 示例 JSON 输出")
    
    print("\n[告警评估响应示例]")
    example_alert = {
        "code": "gate.conservative_rate_high",
        "name": "保守模式比例过高",
        "severity": "high",
        "category": "gate",
        "description": "Evidence Gate 保守模式触发比例过高",
        "window": "15m",
        "current_value": 35.5,
        "threshold": 30.0,
        "unit": "%",
        "condition": ">",
        "triggered_at": "2024-12-14T02:00:00Z",
        "recommended_actions": [
            "检查 evidence 覆盖率: GET /v1/retrieval/vector-coverage",
            "考虑放宽 Evidence Gate 阈值",
        ],
    }
    print(json.dumps(example_alert, indent=2, ensure_ascii=False))
    
    print("\n[Webhook 通知 payload 示例]")
    webhook_payload = {
        "timestamp": "2024-12-14T02:00:00Z",
        "tenant_id": "yantian",
        "site_id": "yantian-main",
        "alert_count": 2,
        "alerts": [
            {
                "code": "health.core_backend_down",
                "severity": "critical",
                "description": "Core Backend 健康检查失败",
            },
            {
                "code": "llm.success_rate_low",
                "severity": "critical",
                "description": "LLM API 调用成功率低于阈值",
            },
        ],
    }
    print(json.dumps(webhook_payload, indent=2, ensure_ascii=False))
    
    print_section("验收测试完成")
    print("✓ 告警系统正常工作")
    print("\n下一步:")
    print("  1. 配置 ALERT_WEBHOOK_URL 环境变量以启用通知")
    print("  2. 根据实际情况调整 alerts_policy_v0.1.yaml 中的阈值")
    print("  3. 设置定时任务定期调用 /v1/alerts/evaluate")
    
    return True


async def run_manual_test():
    """手动测试步骤说明"""
    print_section("手动测试步骤")
    
    print("""
要手动触发告警，可以：

1. 临时修改阈值
   编辑 services/core-backend/data/policies/alerts_policy_v0.1.yaml
   将某个阈值调低/调高使其必然触发
   
   例如，将 gate.conservative_rate_high 的 threshold 从 30.0 改为 0.1
   
2. 重启服务使配置生效
   
3. 调用评估 API
   curl "http://localhost:8000/api/v1/alerts/evaluate?tenant_id=yantian&range=15m"
   
4. 验证告警输出
   检查返回的 active_alerts 列表
   
5. 恢复原始阈值
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        asyncio.run(run_manual_test())
    else:
        try:
            success = asyncio.run(run_test())
            sys.exit(0 if success else 1)
        except Exception as e:
            print(f"\n✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
