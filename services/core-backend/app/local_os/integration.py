"""Mount the existing canonical app and adapt legacy local knowledge endpoints."""
from __future__ import annotations

import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .bridge import (SITE, TENANT, assert_request_scope, culture_service_type,
                     legacy_dto, set_service)

CANONICAL_FIELDS = {"title", "content", "source_id", "locator", "region_scope", "domain", "kind", "review_status", "rights_scope", "review_note", "evidence_type", "issue_ids", "aliases"}


async def body_dict(request):
    try:
        value = await request.json()
    except ValueError:
        raise HTTPException(422, "请输入合法 JSON 对象") from None
    if not isinstance(value, dict):
        raise HTTPException(422, "请输入 JSON 对象")
    assert_request_scope(request, value)
    return value


def knowledge_payload(data, current=None):
    if current and current.get("evidence_type") == "document_statement":
        raise HTTPException(409, "文档摘录不可通过旧知识编辑或核验升格；请修订原件校验导入包并追加版本")
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(422, "metadata 必须是对象")
    payload = {key: current[key] for key in CANONICAL_FIELDS if current and key in current}
    payload.update({key: metadata[key] for key in CANONICAL_FIELDS if key in metadata})
    payload.update({key: data[key] for key in CANONICAL_FIELDS if key in data})
    if not current:
        payload.setdefault("domain", data.get("knowledge_type") if data.get("knowledge_type") in {"humanities", "nature", "craft", "project"} else "humanities")
        payload.setdefault("kind", "fact")
        payload.setdefault("review_status", "draft")
        payload.setdefault("rights_scope", "unknown")
    if data.get("status") in {"retired", "deleted", "inactive"}:
        payload["review_status"] = "retired"
    base = data.get("base_version", data.get("version", metadata.get("base_version", metadata.get("version"))))
    if current and base is None:
        raise HTTPException(422, "本地知识修改/核验须携带 base_version；请先读取当前版本")
    if base is not None:
        payload["base_version"] = base
    if not payload.get("source_id") or not payload.get("locator") or not payload.get("region_scope"):
        raise HTTPException(422, "请提供已登记 source_id、locator、region_scope，保留完整权利和范围；可在工作室登记来源")
    return payload


def install_local_os(app, db_path=None, service=None, operations_db_path=None):
    if getattr(app.state, "culture_service", None) is not None:
        return app.state.culture_service
    if service is None:
        if not db_path:
            raise RuntimeError("LOCAL_OS_MODE 必须显式配置 CIVILIZATION_DB_PATH")
        service = culture_service_type()(db_path)
    app.state.culture_service = service
    set_service(service)
    from .operations import create_operations_router
    # Business inventory and money records have one independent transaction
    # boundary; culture content remains owned by the existing CultureService.
    operations_path = Path(operations_db_path or service.db_path.with_name("operations.sqlite3")).resolve()
    if operations_path == service.db_path:
        raise RuntimeError("运营台账与文化版本库必须使用独立文件")
    app.state.operations_db_path = operations_path
    app.include_router(create_operations_router(str(operations_path)))
    from .growth import create_growth_router
    app.include_router(create_growth_router(str(operations_path), culture_service=service))
    from .room_status import create_room_status_router
    app.include_router(create_room_status_router(str(operations_path)))
    from .workspace import create_workspace_router
    app.include_router(create_workspace_router(str(operations_path), culture_service=service))
    router = APIRouter()

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        path = request.url.path
        if path == "/api/v1/search" or path.startswith("/api/v1/search/"):
            return JSONResponse({"detail": "本地模式不启用向量/embedding服务；请使用统一知识问答或知识检索。", "enabled": False}, status_code=423)
        if request.method == "POST" and re.fullmatch(r"/api/v1/iot-devices/[^/]+/command/?", path):
            return JSONResponse({"detail": "本地模式禁用设备控制；没有写入命令日志或加入队列。"}, status_code=423)
        guarded = (path.startswith("/api/local-os") or path.startswith("/api/v1/knowledge")
                   or path == "/api/v1/chat" or path.startswith("/api/v1/chat/") or path.startswith("/studio"))
        if guarded:
            try:
                assert_request_scope(request)
                if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                    if request.headers.get("x-yantian-local") != "1" or not service.origin_allowed(request):
                        raise HTTPException(403, "本地变更需要同源请求及 X-Yantian-Local: 1")
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    @router.get("/api/local-os/status")
    async def local_status(request: Request):
        assert_request_scope(request)
        status = await service.status()
        return {**status, "local_os": True, "tenant_id": TENANT, "site_id": SITE,
                "canonical_knowledge": {"owner": "core_owned_culture_service", "storage": "single_sqlite", "shared_with": ["studio", "legacy_knowledge", "npc", "tools"]},
                "studio_url": "/studio/", "operations_url": "/operations", "growth_url": "/growth", "workspace_url": "/workspace",
                "layers": {"workspace": {"status": "available", "url": "/workspace", "generation_mode": "local_rules"},
                           "video": {"status": "available", "url": "/growth#video"},
                           "village_model": {"status": "planned"}},
                "operations": {"mode": "local_manual", "platforms_connected": False, "payments_connected": False},
                "machines": {"enabled": False}}

    @router.post("/api/local-os/ask")
    async def local_ask(request: Request):
        data = await body_dict(request)
        try:
            return await service.ask(data.get("question", ""))
        except ValidationError:
            raise HTTPException(422, "问题不能为空，且最多2000字符") from None

    @router.get("/api/v1/knowledge")
    async def list_knowledge(request: Request, skip: int = 0, limit: int = 50, domain: str | None = None, knowledge_type: str | None = None, verified_only: bool = False):
        assert_request_scope(request)
        if not 0 <= skip or not 1 <= limit <= 100:
            raise HTTPException(422, "分页参数不合法")
        items = await service.list_knowledge()
        items = [item for item in items if (not domain or item["domain"] == domain) and (not knowledge_type or item["domain"] == knowledge_type) and (not verified_only or item["review_status"] == "approved")]
        return [legacy_dto(item) for item in items[skip:skip+limit]]

    @router.get("/api/v1/knowledge/search")
    async def search_knowledge(request: Request, q: str, domains: str | None = None, top_k: int = 10):
        assert_request_scope(request)
        try:
            items = await service.search(q, domains.split(",") if domains else None, top_k)
        except ValidationError:
            raise HTTPException(422, "检索问题不合法") from None
        return [{**legacy_dto(item), "content_snippet": item["content"][:300], "score": item["retrieval_score"], "retrieval_method": "local_canonical"} for item in items]

    @router.get("/api/v1/knowledge/{knowledge_id}")
    async def get_knowledge(knowledge_id: str, request: Request):
        assert_request_scope(request)
        return legacy_dto(await service.get_knowledge(knowledge_id))

    @router.post("/api/v1/knowledge", status_code=201)
    async def create_knowledge(request: Request):
        data = await body_dict(request)
        try:
            return legacy_dto(await service.create_knowledge(knowledge_payload(data)))
        except ValidationError:
            raise HTTPException(422, "知识字段不合法，请核对长度、权利、范围与审核状态") from None

    @router.patch("/api/v1/knowledge/{knowledge_id}")
    @router.put("/api/v1/knowledge/{knowledge_id}")
    async def update_knowledge(knowledge_id: str, request: Request):
        data = await body_dict(request)
        current = await service.get_knowledge(knowledge_id)
        try:
            return legacy_dto(await service.update_knowledge(knowledge_id, knowledge_payload(data, current)))
        except ValidationError:
            raise HTTPException(422, "知识字段不合法，请核对版本、权利和范围") from None

    @router.post("/api/v1/knowledge/{knowledge_id}/verify")
    async def verify_knowledge(knowledge_id: str, request: Request):
        data = await body_dict(request)
        if not isinstance(data.get("verified"), bool):
            raise HTTPException(422, "verified 必须是布尔值；核验仅代表本地审核声明")
        current = await service.get_knowledge(knowledge_id)
        data = {**data, "review_status": "approved" if data["verified"] else "draft", "review_note": data.get("notes", "")}
        try:
            return legacy_dto(await service.update_knowledge(knowledge_id, knowledge_payload(data, current)))
        except ValidationError:
            raise HTTPException(422, "核验字段不合法，请核对版本和备注") from None

    @router.delete("/api/v1/knowledge/{knowledge_id}")
    async def refuse_delete(knowledge_id: str, request: Request):
        raise HTTPException(405, "本地知识不删除历史版本；请携带 base_version 将当前条目标记 retired")

    # Registered before ordinary legacy handlers; no PG auth/database dependency
    # is invoked for these explicitly local, fixed-scope knowledge adapters.
    app.include_router(router)
    app.mount("/studio", service.app, name="civilization-studio")
    return service
