"""
MCP 工具注册表

管理所有可用的 MCP 工具定义
工具必须 schema 化、可审计、可回放
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel
import json


@dataclass
class MCPToolDefinition:
    """MCP 工具定义"""

    name: str
    description: str
    version: str = "1.0.0"

    # JSON Schema 格式的输入输出定义
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    # 工具分类
    category: str = "general"
    tags: List[str] = field(default_factory=list)

    # 权限要求
    required_permissions: List[str] = field(default_factory=list)

    # 是否需要证据链
    requires_evidence: bool = False

    # 执行超时（秒）
    timeout_seconds: int = 30

    # 是否可被 AI 直接调用
    ai_callable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 API 响应）"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "category": self.category,
            "tags": self.tags,
            "required_permissions": self.required_permissions,
            "requires_evidence": self.requires_evidence,
            "timeout_seconds": self.timeout_seconds,
            "ai_callable": self.ai_callable,
        }


class MCPToolRegistry:
    """MCP 工具注册表单例"""

    _instance: Optional["MCPToolRegistry"] = None
    _tools: Dict[str, MCPToolDefinition] = {}
    _handlers: Dict[str, Callable] = {}

    def __new__(cls) -> "MCPToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._handlers = {}
            cls._instance._register_builtin_tools()
        return cls._instance

    def _register_builtin_tools(self) -> None:
        """注册内置工具"""

        # 知识检索工具
        self.register(
            MCPToolDefinition(
                name="knowledge.search",
                description="在知识库中搜索相关内容，返回匹配的知识条目作为证据",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询文本",
                        },
                        "domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "限定搜索的知识领域",
                        },
                        "top_k": {
                            "type": "integer",
                            "default": 5,
                            "description": "返回结果数量",
                        },
                        "min_score": {
                            "type": "number",
                            "default": 0.7,
                            "description": "最低相似度阈值",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "content": {"type": "string"},
                                    "score": {"type": "number"},
                                    "source": {"type": "string"},
                                    "verified": {"type": "boolean"},
                                },
                            },
                        },
                        "total_count": {"type": "integer"},
                    },
                },
                category="knowledge",
                tags=["rag", "search", "evidence"],
                requires_evidence=True,
                ai_callable=True,
            )
        )

        # NPC 信息查询工具
        self.register(
            MCPToolDefinition(
                name="npc.get_persona",
                description="获取 NPC 的人设配置信息",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["npc_id"],
                    "properties": {
                        "npc_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "NPC ID",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "persona": {"type": "object"},
                        "knowledge_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                category="npc",
                tags=["npc", "persona"],
                ai_callable=True,
            )
        )

        # 场景信息查询工具
        self.register(
            MCPToolDefinition(
                name="scene.get_info",
                description="获取场景信息，包括位置、POI、当前状态等",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["scene_id"],
                    "properties": {
                        "scene_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "场景 ID",
                        },
                        "include_pois": {
                            "type": "boolean",
                            "default": True,
                            "description": "是否包含 POI 列表",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "pois": {"type": "array"},
                    },
                },
                category="scene",
                tags=["scene", "location"],
                ai_callable=True,
            )
        )

        # 游客档案查询工具
        self.register(
            MCPToolDefinition(
                name="visitor.get_profile",
                description="获取游客档案信息，包括历史访问、任务进度等",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "required": ["visitor_id"],
                    "properties": {
                        "visitor_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "游客 ID",
                        },
                        "include_quest_progress": {
                            "type": "boolean",
                            "default": False,
                            "description": "是否包含任务进度",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "nickname": {"type": "string"},
                        "visit_count": {"type": "integer"},
                        "quest_progress": {"type": "array"},
                    },
                },
                category="visitor",
                tags=["visitor", "profile"],
                required_permissions=["visitor:read"],
                ai_callable=True,
            )
        )

        # 节气查询工具
        self.register(
            MCPToolDefinition(
                name="solar_term.get_current",
                description="获取当前节气信息及相关农耕智慧",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "format": "date",
                            "description": "查询日期，默认为今天",
                        },
                        "include_wisdom": {
                            "type": "boolean",
                            "default": True,
                            "description": "是否包含农耕智慧",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "term_pinyin": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                        "description": {"type": "string"},
                        "farming_wisdom": {"type": "array"},
                    },
                },
                category="farming",
                tags=["solar_term", "farming", "wisdom"],
                requires_evidence=True,
                ai_callable=True,
            )
        )

        # 研学任务查询工具
        self.register(
            MCPToolDefinition(
                name="quest.get_available",
                description="获取当前可用的研学任务列表",
                version="1.0.0",
                input_schema={
                    "type": "object",
                    "properties": {
                        "visitor_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "游客 ID（用于过滤已完成任务）",
                        },
                        "scene_id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "限定场景",
                        },
                        "category": {
                            "type": "string",
                            "description": "任务类别",
                        },
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "quests": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "difficulty": {"type": "string"},
                                    "estimated_duration": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
                category="quest",
                tags=["quest", "learning"],
                ai_callable=True,
            )
        )

    def register(
        self,
        definition: MCPToolDefinition,
        handler: Optional[Callable] = None,
    ) -> None:
        """注册工具"""
        self._tools[definition.name] = definition
        if handler:
            self._handlers[definition.name] = handler

    def get(self, name: str) -> Optional[MCPToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)

    def get_handler(self, name: str) -> Optional[Callable]:
        """获取工具处理函数"""
        return self._handlers.get(name)

    def list_tools(
        self,
        category: Optional[str] = None,
        ai_callable_only: bool = False,
    ) -> List[MCPToolDefinition]:
        """列出所有工具"""
        tools = list(self._tools.values())

        if category:
            tools = [t for t in tools if t.category == category]

        if ai_callable_only:
            tools = [t for t in tools if t.ai_callable]

        return tools

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """转换为 OpenAI function calling 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
            if tool.ai_callable
        ]


# 全局注册表实例
mcp_registry = MCPToolRegistry()


def get_mcp_registry() -> MCPToolRegistry:
    """获取 MCP 工具注册表"""
    return mcp_registry
