"""
MCP 工具执行器

负责执行 MCP 工具调用，记录审计日志
"""

import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestContext
from app.core.permissions import Permission, has_permission
from app.domain.tool_call_log import ToolCallLog, ToolCallStatus
from app.services.mcp_registry import MCPToolRegistry, get_mcp_registry


class ToolExecutionError(Exception):
    """工具执行错误"""

    def __init__(self, message: str, error_code: str = "EXECUTION_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class ToolExecutor:
    """MCP 工具执行器"""

    def __init__(
        self,
        db: AsyncSession,
        ctx: RequestContext,
        registry: Optional[MCPToolRegistry] = None,
    ):
        self.db = db
        self.ctx = ctx
        self.registry = registry or get_mcp_registry()

    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        caller_service: str = "ai-orchestrator",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行 MCP 工具调用

        Args:
            tool_name: 工具名称
            params: 输入参数
            caller_service: 调用方服务名
            session_id: 会话 ID

        Returns:
            工具执行结果

        Raises:
            ToolExecutionError: 执行失败时抛出
        """
        # 1. 获取工具定义
        tool_def = self.registry.get(tool_name)
        if not tool_def:
            raise ToolExecutionError(
                f"Tool '{tool_name}' not found",
                error_code="TOOL_NOT_FOUND",
            )

        # 2. 权限检查
        for perm_str in tool_def.required_permissions:
            try:
                perm = Permission(perm_str)
                if not has_permission(self.ctx.user, perm):
                    raise ToolExecutionError(
                        f"Missing permission: {perm_str}",
                        error_code="PERMISSION_DENIED",
                    )
            except ValueError:
                pass  # 未知权限，跳过

        # 3. 创建审计日志
        span_id = str(uuid.uuid4())[:16]
        log = ToolCallLog(
            trace_id=self.ctx.trace_id,
            span_id=span_id,
            tenant_id=self.ctx.tenant_id,
            site_id=self.ctx.site_id,
            caller_service=caller_service,
            caller_session_id=session_id,
            caller_user_id=self.ctx.user.id,
            tool_name=tool_name,
            tool_version=tool_def.version,
            input_params=params,
            status=ToolCallStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.db.add(log)
        await self.db.flush()

        # 4. 执行工具
        start_time = time.time()
        try:
            handler = self.registry.get_handler(tool_name)
            if handler:
                result = await handler(
                    params=params,
                    ctx=self.ctx,
                    db=self.db,
                )
            else:
                # 使用内置处理器
                result = await self._execute_builtin(tool_name, params)

            duration_ms = int((time.time() - start_time) * 1000)

            # 5. 记录成功
            log.mark_success(result, duration_ms)
            await self.db.flush()

            return {
                "success": True,
                "tool_name": tool_name,
                "result": result,
                "trace_id": self.ctx.trace_id,
                "span_id": span_id,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            # 6. 记录失败
            error_code = getattr(e, "error_code", "UNKNOWN_ERROR")
            log.mark_failed(str(e), error_code)
            await self.db.flush()

            raise ToolExecutionError(str(e), error_code)

    async def _execute_builtin(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行内置工具"""

        if tool_name == "knowledge.search":
            return await self._tool_knowledge_search(params)
        elif tool_name == "npc.get_persona":
            return await self._tool_npc_get_persona(params)
        elif tool_name == "scene.get_info":
            return await self._tool_scene_get_info(params)
        elif tool_name == "visitor.get_profile":
            return await self._tool_visitor_get_profile(params)
        elif tool_name == "solar_term.get_current":
            return await self._tool_solar_term_get_current(params)
        elif tool_name == "quest.get_available":
            return await self._tool_quest_get_available(params)
        else:
            raise ToolExecutionError(
                f"No handler for tool '{tool_name}'",
                error_code="NO_HANDLER",
            )

    async def _tool_knowledge_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """知识检索工具实现"""
        from sqlalchemy import select, func
        from app.domain.knowledge import KnowledgeEntry

        query_text = params.get("query", "")
        domains = params.get("domains", [])
        top_k = params.get("top_k", 5)

        # 构建查询
        stmt = select(KnowledgeEntry).where(
            KnowledgeEntry.tenant_id == self.ctx.tenant_id,
            KnowledgeEntry.site_id == self.ctx.site_id,
            KnowledgeEntry.status == "active",
        )

        if domains:
            stmt = stmt.where(KnowledgeEntry.domains.overlap(domains))

        # 简单的文本匹配（生产环境应使用向量检索）
        stmt = stmt.where(
            KnowledgeEntry.content.ilike(f"%{query_text}%")
            | KnowledgeEntry.title.ilike(f"%{query_text}%")
        )

        stmt = stmt.limit(top_k)

        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        return {
            "results": [
                {
                    "id": str(entry.id),
                    "title": entry.title,
                    "content": entry.content[:500] if entry.content else "",
                    "score": 0.8,  # 占位，实际应从向量检索获取
                    "source": entry.source,
                    "verified": entry.verified,
                    "knowledge_type": entry.knowledge_type,
                }
                for entry in entries
            ],
            "total_count": len(entries),
        }

    async def _tool_npc_get_persona(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """NPC 人设查询工具实现"""
        from sqlalchemy import select
        from app.domain.npc import NPC

        npc_id = params.get("npc_id")

        result = await self.db.execute(
            select(NPC).where(
                NPC.id == npc_id,
                NPC.site_id == self.ctx.site_id,
                NPC.deleted_at.is_(None),
            )
        )
        npc = result.scalar_one_or_none()

        if not npc:
            raise ToolExecutionError(
                f"NPC '{npc_id}' not found",
                error_code="NPC_NOT_FOUND",
            )

        return {
            "id": str(npc.id),
            "name": npc.name,
            "display_name": npc.display_name,
            "npc_type": npc.npc_type,
            "persona": npc.persona,
            "knowledge_domains": npc.knowledge_domains,
            "greeting_templates": npc.greeting_templates,
            "fallback_responses": npc.fallback_responses,
        }

    async def _tool_scene_get_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """场景信息查询工具实现"""
        from sqlalchemy import select
        from app.domain.scene import Scene
        from app.domain.poi import POI

        scene_id = params.get("scene_id")
        include_pois = params.get("include_pois", True)

        result = await self.db.execute(
            select(Scene).where(
                Scene.id == scene_id,
                Scene.site_id == self.ctx.site_id,
                Scene.deleted_at.is_(None),
            )
        )
        scene = result.scalar_one_or_none()

        if not scene:
            raise ToolExecutionError(
                f"Scene '{scene_id}' not found",
                error_code="SCENE_NOT_FOUND",
            )

        response = {
            "id": str(scene.id),
            "name": scene.name,
            "display_name": scene.display_name,
            "description": scene.description,
            "scene_type": scene.scene_type,
        }

        if include_pois:
            poi_result = await self.db.execute(
                select(POI).where(
                    POI.scene_id == scene_id,
                    POI.deleted_at.is_(None),
                )
            )
            pois = poi_result.scalars().all()
            response["pois"] = [
                {
                    "id": str(poi.id),
                    "name": poi.name,
                    "poi_type": poi.poi_type,
                }
                for poi in pois
            ]

        return response

    async def _tool_visitor_get_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """游客档案查询工具实现"""
        from sqlalchemy import select
        from app.domain.visitor import Visitor, VisitorQuest

        visitor_id = params.get("visitor_id")
        include_quest_progress = params.get("include_quest_progress", False)

        result = await self.db.execute(
            select(Visitor).where(Visitor.id == visitor_id)
        )
        visitor = result.scalar_one_or_none()

        if not visitor:
            raise ToolExecutionError(
                f"Visitor '{visitor_id}' not found",
                error_code="VISITOR_NOT_FOUND",
            )

        response = {
            "id": str(visitor.id),
            "nickname": visitor.nickname,
            "profile": visitor.profile,
            "stats": visitor.stats,
            "last_visit_at": visitor.last_visit_at.isoformat() if visitor.last_visit_at else None,
        }

        if include_quest_progress:
            quest_result = await self.db.execute(
                select(VisitorQuest).where(VisitorQuest.visitor_id == visitor_id)
            )
            quests = quest_result.scalars().all()
            response["quest_progress"] = [
                {
                    "quest_id": str(q.quest_id),
                    "status": q.status,
                    "current_step": q.current_step,
                    "score": q.score,
                }
                for q in quests
            ]

        return response

    async def _tool_solar_term_get_current(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """节气查询工具实现"""
        from datetime import date

        query_date = params.get("date")
        if query_date:
            query_date = date.fromisoformat(query_date)
        else:
            query_date = date.today()

        # 简化的节气计算（生产环境应使用精确算法）
        solar_terms = [
            ("立春", "lichun", (2, 4)),
            ("雨水", "yushui", (2, 19)),
            ("惊蛰", "jingzhe", (3, 6)),
            ("春分", "chunfen", (3, 21)),
            ("清明", "qingming", (4, 5)),
            ("谷雨", "guyu", (4, 20)),
            ("立夏", "lixia", (5, 6)),
            ("小满", "xiaoman", (5, 21)),
            ("芒种", "mangzhong", (6, 6)),
            ("夏至", "xiazhi", (6, 21)),
            ("小暑", "xiaoshu", (7, 7)),
            ("大暑", "dashu", (7, 23)),
            ("立秋", "liqiu", (8, 8)),
            ("处暑", "chushu", (8, 23)),
            ("白露", "bailu", (9, 8)),
            ("秋分", "qiufen", (9, 23)),
            ("寒露", "hanlu", (10, 8)),
            ("霜降", "shuangjiang", (10, 24)),
            ("立冬", "lidong", (11, 8)),
            ("小雪", "xiaoxue", (11, 22)),
            ("大雪", "daxue", (12, 7)),
            ("冬至", "dongzhi", (12, 22)),
            ("小寒", "xiaohan", (1, 6)),
            ("大寒", "dahan", (1, 20)),
        ]

        current_term = None
        for i, (name, pinyin, (month, day)) in enumerate(solar_terms):
            term_date = date(query_date.year, month, day)
            next_idx = (i + 1) % len(solar_terms)
            next_month, next_day = solar_terms[next_idx][2]
            next_year = query_date.year if next_month >= month else query_date.year + 1
            next_date = date(next_year, next_month, next_day)

            if term_date <= query_date < next_date:
                current_term = {
                    "term": name,
                    "term_pinyin": pinyin,
                    "start_date": term_date.isoformat(),
                    "end_date": next_date.isoformat(),
                }
                break

        if not current_term:
            current_term = {
                "term": "大寒",
                "term_pinyin": "dahan",
                "start_date": date(query_date.year, 1, 20).isoformat(),
                "end_date": date(query_date.year, 2, 4).isoformat(),
            }

        if params.get("include_wisdom", True):
            # 从知识库查询节气相关智慧
            wisdom_result = await self._tool_knowledge_search({
                "query": current_term["term"],
                "domains": ["solar_term", "farming_wisdom"],
                "top_k": 3,
            })
            current_term["farming_wisdom"] = wisdom_result.get("results", [])

        return current_term

    async def _tool_quest_get_available(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """研学任务查询工具实现"""
        from sqlalchemy import select
        from app.domain.quest import Quest

        visitor_id = params.get("visitor_id")
        scene_id = params.get("scene_id")
        category = params.get("category")

        stmt = select(Quest).where(
            Quest.site_id == self.ctx.site_id,
            Quest.status == "active",
            Quest.deleted_at.is_(None),
        )

        if scene_id:
            stmt = stmt.where(Quest.scene_ids.contains([scene_id]))

        if category:
            stmt = stmt.where(Quest.category == category)

        result = await self.db.execute(stmt)
        quests = result.scalars().all()

        return {
            "quests": [
                {
                    "id": str(q.id),
                    "name": q.name,
                    "display_name": q.display_name,
                    "description": q.description,
                    "difficulty": q.difficulty,
                    "estimated_duration": q.estimated_duration_minutes,
                    "category": q.category,
                }
                for q in quests
            ],
        }
