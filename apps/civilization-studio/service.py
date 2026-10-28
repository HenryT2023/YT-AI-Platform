"""Explicit canonical culture service; internal ASGI calls never use a network.

Core creates exactly one instance and mounts ``service.app``. This adapter keeps
all existing SQLite transaction and immutable version logic in the Studio app;
it never calls route.endpoint, creates a second app, or mirrors the repository.
"""
from __future__ import annotations

from pathlib import Path
import httpx
from fastapi import HTTPException

try:
    from .server import create_app, same_local_origin
    from .domain import AskInput, KnowledgeInput, select_evidence
except ImportError:
    from server import create_app, same_local_origin
    from domain import AskInput, KnowledgeInput, select_evidence


class CultureService:
    def __init__(self, db_path, seed=True):
        self.db_path = Path(db_path).resolve()
        self.app = create_app(self.db_path, seed=seed)

    @staticmethod
    def origin_allowed(request):
        return same_local_origin(request)

    async def _request(self, method, path, payload=None):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.request(method, path, json=payload,
                headers={"X-Yantian-Local": "1", "Origin": "http://127.0.0.1"})
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "本地知识服务拒绝请求")
            except ValueError:
                detail = "本地知识服务未完成请求"
            raise HTTPException(response.status_code, detail)
        return response.json()

    async def status(self):
        return await self._request("GET", "/api/status")

    async def ask(self, question):
        validated = AskInput(question=question)
        return await self._request("POST", "/api/ask", validated.model_dump())

    async def list_sources(self):
        return await self._request("GET", "/api/sources")

    async def list_knowledge(self):
        return await self._request("GET", "/api/knowledge")

    async def get_knowledge(self, knowledge_id):
        for item in await self.list_knowledge():
            if item["id"] == knowledge_id:
                return item
        raise HTTPException(404, "知识条目不存在")

    async def create_knowledge(self, payload):
        validated = KnowledgeInput.model_validate(payload)
        return await self._request("POST", "/api/knowledge", validated.model_dump())

    async def update_knowledge(self, knowledge_id, payload):
        validated = KnowledgeInput.model_validate(payload)
        return await self._request("PUT", "/api/knowledge/" + knowledge_id, validated.model_dump())

    async def search(self, query, domains=None, limit=5, min_score=0):
        query = AskInput(question=query).question
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            raise HTTPException(422, "检索数量须为1..50的整数")
        if not isinstance(min_score, (int, float)) or not 0 <= min_score <= 1:
            raise HTTPException(422, "检索门槛须在0..1范围内")
        items = await self.list_knowledge()
        sources = {item["id"]: item for item in await self.list_sources()}
        ranked, blocked = select_evidence(query, items, sources, domains)
        return [{**item, "source": source, "retrieval_score": score,
                 "knowledge_version": item["version"], "retrieval_method": "local_canonical",
                 "limitations": blocked} for score, item, source in ranked if score >= min_score][:limit]
