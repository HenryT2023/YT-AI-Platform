"""
工具注册表

管理所有可用工具的元数据和实现
"""

from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel

from app.tools.schemas import (
    ToolMetadata,
    GetNPCProfileInput,
    GetNPCProfileOutput,
    SearchContentInput,
    SearchContentOutput,
    GetSiteMapInput,
    GetSiteMapOutput,
    CreateDraftContentInput,
    CreateDraftContentOutput,
    LogUserEventInput,
    LogUserEventOutput,
    GetPromptActiveInput,
    GetPromptActiveOutput,
    RetrieveEvidenceInput,
    RetrieveEvidenceOutput,
)


class ToolDefinition:
    """工具定义"""

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        category: str,
        input_schema: Type[BaseModel],
        output_schema: Type[BaseModel],
        handler: Optional[Callable] = None,
        requires_auth: bool = True,
        ai_callable: bool = True,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.category = category
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.handler = handler
        self.requires_auth = requires_auth
        self.ai_callable = ai_callable

    def to_metadata(self) -> ToolMetadata:
        """转换为元数据"""
        return ToolMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            category=self.category,
            input_schema=self.input_schema.model_json_schema(),
            output_schema=self.output_schema.model_json_schema(),
            requires_auth=self.requires_auth,
            ai_callable=self.ai_callable,
        )


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """注册内置工具"""
        # 1. get_npc_profile
        self.register(ToolDefinition(
            name="get_npc_profile",
            version="1.0.0",
            description="获取 NPC 人设配置，包括身份、性格、知识领域等",
            category="npc",
            input_schema=GetNPCProfileInput,
            output_schema=GetNPCProfileOutput,
        ))

        # 2. search_content
        self.register(ToolDefinition(
            name="search_content",
            version="1.0.0",
            description="搜索内容/知识库，支持关键词、类型、标签过滤",
            category="content",
            input_schema=SearchContentInput,
            output_schema=SearchContentOutput,
        ))

        # 3. get_site_map
        self.register(ToolDefinition(
            name="get_site_map",
            version="1.0.0",
            description="获取站点地图，包括兴趣点和路线",
            category="site",
            input_schema=GetSiteMapInput,
            output_schema=GetSiteMapOutput,
        ))

        # 4. create_draft_content
        self.register(ToolDefinition(
            name="create_draft_content",
            version="1.0.0",
            description="创建草稿内容，返回 content_id",
            category="content",
            input_schema=CreateDraftContentInput,
            output_schema=CreateDraftContentOutput,
        ))

        # 5. log_user_event
        self.register(ToolDefinition(
            name="log_user_event",
            version="1.0.0",
            description="记录用户事件到分析表",
            category="analytics",
            input_schema=LogUserEventInput,
            output_schema=LogUserEventOutput,
        ))

        # 6. get_prompt_active
        self.register(ToolDefinition(
            name="get_prompt_active",
            version="1.0.0",
            description="获取 NPC 当前激活的 Prompt 配置（为 P8 预留）",
            category="prompt",
            input_schema=GetPromptActiveInput,
            output_schema=GetPromptActiveOutput,
        ))

        # 7. retrieve_evidence
        self.register(ToolDefinition(
            name="retrieve_evidence",
            version="1.0.0",
            description="检索证据，用于 AI 回答时引用，支持知识领域过滤",
            category="evidence",
            input_schema=RetrieveEvidenceInput,
            output_schema=RetrieveEvidenceOutput,
        ))

    def register(self, tool: ToolDefinition) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_all(self) -> List[ToolDefinition]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_metadata(self) -> List[ToolMetadata]:
        """列出所有工具元数据"""
        return [tool.to_metadata() for tool in self._tools.values()]


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    return ToolRegistry()
