#!/usr/bin/env python3
"""
端到端对话测试脚本

连续 3 轮对话（含 session_id）并输出 trace_id

用法:
    python scripts/e2e_chat_test.py
    python scripts/e2e_chat_test.py --base-url http://localhost:8001
    python scripts/e2e_chat_test.py --npc-id ancestor_yan
"""

import argparse
import json
import sys
import time
from typing import Optional

import httpx


# ==================
# 配置
# ==================

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_TENANT_ID = "yantian"
DEFAULT_SITE_ID = "yantian-main"
DEFAULT_NPC_ID = "ancestor_yan"

# 三轮对话问题
CONVERSATION_TURNS = [
    "请问严氏家训有哪些？",
    "第一条孝悌为本是什么意思？",
    "有什么具体的故事吗？",
]


# ==================
# 测试函数
# ==================

def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(label: str, value: str, indent: int = 0):
    """打印结果"""
    prefix = "  " * indent
    print(f"{prefix}{label}: {value}")


def check_health(base_url: str) -> bool:
    """检查服务健康状态"""
    print_header("1. 健康检查")

    try:
        # 基本健康检查
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            print_result("基本健康", f"✅ {data.get('status', 'unknown')}")
        else:
            print_result("基本健康", f"❌ HTTP {resp.status_code}")
            return False

        # 深度健康检查
        resp = httpx.get(f"{base_url}/api/v1/healthz", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            print_result("深度健康", f"✅ {data.get('status', 'unknown')}")
            for comp in data.get("components", []):
                status_icon = "✅" if comp["status"] == "healthy" else "⚠️" if comp["status"] == "degraded" else "❌"
                latency = f" ({comp.get('latency_ms', '?')}ms)" if comp.get("latency_ms") else ""
                print_result(comp["name"], f"{status_icon} {comp['status']}{latency}", indent=1)
        else:
            print_result("深度健康", f"⚠️ HTTP {resp.status_code}")

        return True

    except httpx.ConnectError:
        print_result("连接", f"❌ 无法连接到 {base_url}")
        return False
    except Exception as e:
        print_result("错误", f"❌ {str(e)}")
        return False


def run_conversation(
    base_url: str,
    tenant_id: str,
    site_id: str,
    npc_id: str,
    questions: list,
) -> tuple[bool, list[str], Optional[str]]:
    """
    运行多轮对话

    Returns:
        (success, trace_ids, session_id)
    """
    print_header("2. 多轮对话测试")

    session_id = None
    trace_ids = []
    success = True

    for i, question in enumerate(questions, 1):
        print(f"\n--- 第 {i} 轮 ---")
        print_result("问题", question)

        try:
            start_time = time.time()

            payload = {
                "tenant_id": tenant_id,
                "site_id": site_id,
                "npc_id": npc_id,
                "query": question,
            }

            # 第二轮开始传入 session_id
            if session_id:
                payload["session_id"] = session_id

            resp = httpx.post(
                f"{base_url}/api/v1/npc/chat",
                json=payload,
                timeout=30.0,
            )

            latency = int((time.time() - start_time) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                trace_id = data.get("trace_id", "unknown")
                session_id = data.get("session_id", session_id)
                policy_mode = data.get("policy_mode", "unknown")
                answer = data.get("answer_text", "")[:100]

                trace_ids.append(trace_id)

                print_result("状态", f"✅ 成功 ({latency}ms)")
                print_result("trace_id", trace_id)
                print_result("session_id", session_id)
                print_result("policy_mode", policy_mode)
                print_result("回答", f"{answer}...")
            else:
                print_result("状态", f"❌ HTTP {resp.status_code}")
                print_result("错误", resp.text[:200])
                success = False

        except Exception as e:
            print_result("状态", f"❌ 异常")
            print_result("错误", str(e))
            success = False

    return success, trace_ids, session_id


def check_session(
    base_url: str,
    tenant_id: str,
    site_id: str,
    session_id: str,
) -> bool:
    """检查会话状态"""
    print_header("3. 会话状态检查")

    try:
        resp = httpx.get(
            f"{base_url}/api/v1/npc/sessions/{session_id}",
            headers={
                "X-Tenant-ID": tenant_id,
                "X-Site-ID": site_id,
            },
            timeout=10.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            print_result("状态", "✅ 成功")
            print_result("session_id", data.get("session_id", "unknown"))
            print_result("消息数", str(data.get("message_count", 0)))

            messages = data.get("recent_messages", [])
            if messages:
                print_result("最近消息", "")
                for msg in messages[-4:]:
                    role = msg.get("role", "?")
                    content = msg.get("content", "")[:50]
                    print_result(role, content, indent=1)

            return True
        else:
            print_result("状态", f"❌ HTTP {resp.status_code}")
            return False

    except Exception as e:
        print_result("状态", f"❌ {str(e)}")
        return False


def check_trace(
    base_url: str,
    tenant_id: str,
    site_id: str,
    trace_id: str,
) -> bool:
    """检查 Trace 统一视图"""
    print_header("4. Trace 统一视图")

    try:
        resp = httpx.get(
            f"{base_url}/api/v1/traces/{trace_id}/unified?include_session=true",
            headers={
                "X-Tenant-ID": tenant_id,
                "X-Site-ID": site_id,
            },
            timeout=10.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            print_result("状态", "✅ 成功")
            print_result("trace_id", data.get("trace_id", "unknown"))
            print_result("request_type", data.get("request_type", "unknown"))
            print_result("policy_mode", data.get("policy_mode", "unknown"))
            print_result("latency_ms", str(data.get("latency_ms", 0)))

            # Prompt 信息
            prompt = data.get("prompt", {})
            if prompt.get("version"):
                print_result("prompt_version", str(prompt.get("version")))
                print_result("prompt_source", prompt.get("source", "unknown"))

            # LLM 审计
            llm = data.get("llm_audit", {})
            if llm.get("provider"):
                print_result("llm_provider", llm.get("provider", "unknown"))
                print_result("llm_model", llm.get("model", "unknown"))
                print_result("tokens", f"in={llm.get('tokens_input', 0)}, out={llm.get('tokens_output', 0)}")

            # 工具调用
            tool_calls = data.get("tool_calls", [])
            if tool_calls:
                print_result("工具调用", f"{len(tool_calls)} 个")
                for tc in tool_calls[:5]:
                    status_icon = "✅" if tc["status"] == "success" else "❌"
                    print_result(tc["name"], f"{status_icon} {tc['status']}", indent=1)

            return True
        else:
            print_result("状态", f"❌ HTTP {resp.status_code}")
            return False

    except Exception as e:
        print_result("状态", f"❌ {str(e)}")
        return False


def check_metrics(base_url: str) -> bool:
    """检查指标摘要"""
    print_header("5. 指标摘要")

    try:
        resp = httpx.get(
            f"{base_url}/api/v1/metrics/summary?minutes=5",
            timeout=10.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            print_result("状态", "✅ 成功")
            print_result("总请求数", str(data.get("total_requests", 0)))
            print_result("成功率", f"{data.get('success_rate', 0) * 100:.1f}%")
            print_result("P95 延迟", f"{data.get('latency_p95_ms', 0)}ms")
            print_result("缓存命中率", f"{data.get('cache_hit_ratio', 0) * 100:.1f}%")

            policy = data.get("policy_distribution", {})
            print_result("策略分布", f"normal={policy.get('normal', 0)}, conservative={policy.get('conservative', 0)}, refuse={policy.get('refuse', 0)}")

            return True
        else:
            print_result("状态", f"❌ HTTP {resp.status_code}")
            return False

    except Exception as e:
        print_result("状态", f"❌ {str(e)}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="端到端对话测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="AI Orchestrator URL")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help="租户 ID")
    parser.add_argument("--site-id", default=DEFAULT_SITE_ID, help="站点 ID")
    parser.add_argument("--npc-id", default=DEFAULT_NPC_ID, help="NPC ID")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  严田 AI 文明引擎 - 端到端测试")
    print("=" * 60)
    print(f"  Base URL: {args.base_url}")
    print(f"  Tenant: {args.tenant_id}")
    print(f"  Site: {args.site_id}")
    print(f"  NPC: {args.npc_id}")

    # 1. 健康检查
    if not check_health(args.base_url):
        print("\n❌ 健康检查失败，请确保服务已启动")
        sys.exit(1)

    # 2. 多轮对话
    success, trace_ids, session_id = run_conversation(
        base_url=args.base_url,
        tenant_id=args.tenant_id,
        site_id=args.site_id,
        npc_id=args.npc_id,
        questions=CONVERSATION_TURNS,
    )

    if not success:
        print("\n⚠️ 对话测试部分失败")

    # 3. 会话状态检查
    if session_id:
        check_session(
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            site_id=args.site_id,
            session_id=session_id,
        )

    # 4. Trace 统一视图（检查最后一个 trace）
    if trace_ids:
        check_trace(
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            site_id=args.site_id,
            trace_id=trace_ids[-1],
        )

    # 5. 指标摘要
    check_metrics(args.base_url)

    # 输出摘要
    print_header("测试摘要")
    print_result("对话轮数", str(len(trace_ids)))
    print_result("session_id", session_id or "N/A")
    print_result("trace_ids", "")
    for tid in trace_ids:
        print(f"    - {tid}")

    if success:
        print("\n✅ 端到端测试通过")
        sys.exit(0)
    else:
        print("\n⚠️ 端到端测试部分失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
