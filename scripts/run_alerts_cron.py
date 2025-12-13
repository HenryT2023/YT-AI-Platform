#!/usr/bin/env python3
"""
告警定时评估脚本

用于 cron/k8s CronJob 定时调用，每 5 分钟评估一次告警。

功能：
1. 调用 /v1/alerts/evaluate-persist API
2. 应用静默规则
3. 去重（同一告警不重复通知）
4. 写入告警事件到数据库
5. 对 critical/high 级别新告警发送 webhook

使用方式：
    # 直接运行
    python scripts/run_alerts_cron.py
    
    # 指定参数
    python scripts/run_alerts_cron.py --tenant-id yantian --site-id yantian-main --range 15m
    
    # crontab 示例（每 5 分钟）
    */5 * * * * cd /app && python scripts/run_alerts_cron.py >> /var/log/alerts_cron.log 2>&1

环境变量：
    CORE_BACKEND_URL: Core Backend 地址（默认 http://localhost:8000）
    ALERT_WEBHOOK_URL: Webhook 通知地址（可选）
    TENANT_ID: 默认租户 ID（默认 yantian）
    SITE_ID: 默认站点 ID（可选）
"""

import argparse
import asyncio
import os
import sys
import json
from datetime import datetime

import httpx


# 配置
CORE_BACKEND_URL = os.environ.get("CORE_BACKEND_URL", "http://localhost:8000")
DEFAULT_TENANT_ID = os.environ.get("TENANT_ID", "yantian")
DEFAULT_SITE_ID = os.environ.get("SITE_ID")
DEFAULT_RANGE = "15m"


def log(level: str, message: str, **kwargs):
    """简单日志输出"""
    timestamp = datetime.utcnow().isoformat()
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[{timestamp}] [{level.upper()}] {message} {extra}".strip())


async def evaluate_alerts(
    tenant_id: str,
    site_id: str | None,
    range_str: str,
    send_webhook: bool = True,
) -> dict:
    """调用告警评估 API"""
    url = f"{CORE_BACKEND_URL}/api/v1/alerts/evaluate-persist"
    params = {
        "tenant_id": tenant_id,
        "range": range_str,
        "send_webhook": str(send_webhook).lower(),
    }
    if site_id:
        params["site_id"] = site_id
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, params=params)
        response.raise_for_status()
        return response.json()


async def main():
    parser = argparse.ArgumentParser(description="告警定时评估脚本")
    parser.add_argument(
        "--tenant-id",
        default=DEFAULT_TENANT_ID,
        help=f"租户 ID（默认: {DEFAULT_TENANT_ID}）",
    )
    parser.add_argument(
        "--site-id",
        default=DEFAULT_SITE_ID,
        help="站点 ID（可选）",
    )
    parser.add_argument(
        "--range",
        default=DEFAULT_RANGE,
        help=f"评估窗口（默认: {DEFAULT_RANGE}）",
    )
    parser.add_argument(
        "--no-webhook",
        action="store_true",
        help="不发送 webhook 通知",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅评估，不持久化（使用 /evaluate 而非 /evaluate-persist）",
    )
    
    args = parser.parse_args()
    
    log("info", "alerts_cron_start", tenant_id=args.tenant_id, site_id=args.site_id or "all", range=args.range)
    
    try:
        if args.dry_run:
            # Dry run: 使用 /evaluate 接口
            url = f"{CORE_BACKEND_URL}/api/v1/alerts/evaluate"
            params = {
                "tenant_id": args.tenant_id,
                "range": args.range,
                "send_webhook": "false",
            }
            if args.site_id:
                params["site_id"] = args.site_id
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                result = response.json()
            
            log("info", "alerts_cron_dry_run_complete",
                alert_count=result["alert_count"],
                critical=result["alerts_by_severity"]["critical"],
                high=result["alerts_by_severity"]["high"],
            )
            
            if result["active_alerts"]:
                log("info", "active_alerts:")
                for alert in result["active_alerts"]:
                    log("info", f"  - [{alert['severity']}] {alert['code']}: {alert['current_value']} {alert.get('unit', '')}")
        else:
            # 正常运行: 使用 /evaluate-persist 接口
            result = await evaluate_alerts(
                tenant_id=args.tenant_id,
                site_id=args.site_id,
                range_str=args.range,
                send_webhook=not args.no_webhook,
            )
            
            log("info", "alerts_cron_complete",
                total_alerts=result["total_alerts"],
                new_alerts=result["new_alerts"],
                updated_alerts=result["updated_alerts"],
                resolved_alerts=result["resolved_alerts"],
                silenced_alerts=result["silenced_alerts"],
                webhook_sent=result["webhook_sent"],
            )
            
            # 输出上下文信息
            context = result.get("context", {})
            if context.get("active_release_id"):
                log("info", "context",
                    active_release=context.get("active_release_name"),
                    active_experiment=context.get("active_experiment_name"),
                )
            
            # 如果有新的 critical/high 告警，输出详情
            if result["new_alerts"] > 0:
                log("warning", f"new_alerts_detected: {result['new_alerts']}")
        
        return 0
    
    except httpx.HTTPStatusError as e:
        log("error", "http_error", status=e.response.status_code, detail=e.response.text[:200])
        return 1
    except httpx.RequestError as e:
        log("error", "request_error", error=str(e))
        return 1
    except Exception as e:
        log("error", "unexpected_error", error=str(e))
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
