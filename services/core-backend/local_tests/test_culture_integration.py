"""Run directly with unittest. Never import the destructive legacy conftest.

LOCAL_OS_MODE=true PYTHONPATH=<supplemental-deps> .venv/bin/python -m unittest
local_tests.test_culture_integration -v
"""
import os
os.environ["LOCAL_OS_MODE"] = "true"

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

from app.local_os.bridge import culture_service_type, assert_scope
from app.local_os.integration import install_local_os


HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


class BombDB:
    def __getattr__(self, key):
        raise AssertionError("Legacy database must not be used by canonical handlers: " + key)


class CultureIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "canonical.sqlite3"
        self.service = culture_service_type()(self.path)
        self.app = FastAPI()
        install_local_os(self.app, service=self.service)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def send(self, method, path, payload=None, headers=None):
        return await self.client.request(method, path, json=payload, headers=HEADERS if headers is None else headers)

    def knowledge(self, **updates):
        return {"title": "合成青竹纹理知识", "content": "合成青竹纹理测试条目，不是传统纹样。",
                "source_id": "src-ihchina-three-carvings", "locator": "合成测试定位", "region_scope": "徽州区域",
                "domain": "craft", "kind": "interpretation", "review_status": "approved", "rights_scope": "internal", **updates}

    async def add_knowledge(self, **updates):
        response = await self.send("POST", "/api/v1/knowledge", self.knowledge(**updates))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def draft(self, ids):
        return {"title": "整合合成稿", "purpose": "decorative", "label": "整合测试", "width_mm": 120,
                "height_mm": 80, "motif": "geometric", "mirror_choice": "no", "knowledge_ids": ids, "note": "本地合成"}

    async def test_single_service_mount_shared_counts_and_root_path_origin(self):
        self.assertIs(install_local_os(self.app, service=self.service), self.service)
        self.assertIs(self.app.state.culture_service, self.service)
        status = (await self.send("GET", "/api/local-os/status")).json()
        self.assertEqual(status["mode"], "local")
        self.assertEqual(status["canonical_knowledge"]["storage"], "single_sqlite")
        self.assertFalse(status["machines"]["enabled"])
        self.assertEqual((await self.send("GET", "/studio/api/status")).json()["counts"], status["counts"])
        preview = await self.send("POST", "/studio/api/designs/preview", self.draft([]))
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertFalse(preview.json()["persisted"])
        created = await self.add_knowledge()
        canonical = (await self.send("GET", "/studio/api/knowledge")).json()
        self.assertIn(created["id"], {item["id"] for item in canonical})
        self.assertEqual((await self.send("GET", "/api/local-os/status")).json()["counts"]["knowledge"], 4)

    async def test_scope_and_origin_fail_closed_without_pg(self):
        self.assertEqual((await self.send("GET", "/api/v1/knowledge?tenant_id=other")).status_code, 403)
        self.assertEqual((await self.send("GET", "/studio/api/knowledge", headers={"X-Site-ID": "other"})).status_code, 403)
        self.assertEqual((await self.send("POST", "/api/local-os/ask", {"question": "徽州三雕"}, headers={})).status_code, 403)
        self.assertEqual((await self.send("POST", "/api/local-os/ask", {"question": "徽州三雕"}, headers={"X-Yantian-Local": "1", "Origin": "https://foreign.invalid"})).status_code, 403)
        self.assertEqual((await self.send("POST", "/api/v1/knowledge", self.knowledge(tenant_id="other"))).status_code, 403)
        self.assertEqual((await self.send("POST", "/api/v1/knowledge", self.knowledge(site_id="other"))).status_code, 403)
        self.assertEqual((await self.send("POST", "/api/v1/knowledge", self.knowledge(metadata={"tenant_id": "other"}))).status_code, 403)
        self.assertEqual((await self.send("POST", "/studio/api/designs/preview", self.draft([]), headers={"X-Yantian-Local": "1", "Origin": "https://foreign.invalid", "X-Forwarded-Host": "foreign.invalid"})).status_code, 403)
        proxy_headers = {"X-Yantian-Local": "1", "Origin": "http://127.0.0.1:8795", "X-Forwarded-Host": "127.0.0.1:8795"}
        self.assertEqual((await self.send("POST", "/studio/api/designs/preview", self.draft([]), headers=proxy_headers)).status_code, 200)

    async def test_legacy_changes_invalidate_studio_review_and_stale_version(self):
        item = await self.add_knowledge()
        self.assertEqual(item["version"], 1)
        self.assertEqual(item["tenant_id"], "yantian")
        draft = (await self.send("POST", "/studio/api/designs", self.draft([item["id"]]))).json()
        review = {"version": 1, "reviewer_role": "合成本地审阅", "decision": "approve", "comment": "仅合成测试",
                  "confirmations": {"culture": True, "rights": True, "craft": True}}
        approved = await self.send("POST", f"/studio/api/designs/{draft['id']}/reviews", review)
        self.assertEqual(approved.json()["design"]["status"], "approved")
        changed = await self.send("PATCH", f"/api/v1/knowledge/{item['id']}", {"content": "合成青竹纹理修订二版。", "base_version": 1})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["version"], 2)
        current = (await self.send("GET", f"/studio/api/designs/{draft['id']}")).json()
        self.assertEqual(current["status"], "source_changed")
        self.assertEqual((await self.send("PATCH", f"/api/v1/knowledge/{item['id']}", {"base_version": 1, "content": "旧版本"})).status_code, 409)
        self.assertEqual((await self.send("POST", f"/studio/api/designs/{draft['id']}/reviews", review)).status_code, 409)

    async def test_legacy_verify_is_versioned_and_not_publication_checked_boolean(self):
        seeded = (await self.send("GET", "/api/v1/knowledge/kn-three-carvings")).json()
        self.assertFalse(seeded["verified"])
        item = await self.add_knowledge(review_status="draft")
        route = f"/api/v1/knowledge/{item['id']}/verify"
        self.assertEqual((await self.send("POST", route, {"verified": True})).status_code, 422)
        response = await self.send("POST", route, {"verified": True, "base_version": 1, "notes": "合成本地核对声明"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(response.json()["review_note"], "合成本地核对声明")
        self.assertEqual((await self.send("POST", route, {"verified": True, "base_version": 1})).status_code, 409)
        invalid_fact = self.knowledge(kind="fact", domain="humanities", region_scope="严田村", content="严田木刻起源于某朝代。")
        self.assertEqual((await self.send("POST", "/api/v1/knowledge", invalid_fact)).status_code, 422)

    async def test_ask_and_readonly_tools_share_same_gates_no_external_call(self):
        item = await self.add_knowledge()
        answer = (await self.send("POST", "/api/local-os/ask", {"question": "合成青竹纹理"})).json()
        self.assertIn(item["id"], {citation["knowledge_id"] for citation in answer["citations"]})
        unknown = (await self.send("POST", "/api/local-os/ask", {"question": "严田木刻起源哪个朝代"})).json()
        self.assertEqual(unknown["status"], "insufficient_evidence")
        self.assertEqual(await self.service.search("严田木刻有哪些传承人"), [])
        from app.tools.executor import ToolExecutor as EvidenceExecutor
        from app.tools.schemas import RetrieveEvidenceInput, ToolContext
        from app.services.tool_executor import ToolExecutor as LegacyExecutor
        context = ToolContext(tenant_id="yantian", site_id="yantian-main", trace_id="synthetic-trace")
        evidence = await EvidenceExecutor(BombDB())._handle_retrieve_evidence(RetrieveEvidenceInput(query="合成青竹纹理", min_score=0), context)
        self.assertEqual(evidence.strategy_used, "local_canonical")
        match = next(row for row in evidence.items if row.id == item["id"])
        self.assertEqual(match.knowledge_version, 1)
        self.assertEqual(match.locator, "合成测试定位")
        self.assertEqual(match.rights_scope, "internal")
        result = await LegacyExecutor(BombDB(), SimpleNamespace(tenant_id="yantian", site_id="yantian-main"))._tool_knowledge_search({"query": "合成青竹纹理"})
        self.assertIn(item["id"], {row["id"] for row in result["results"]})
        self.assertEqual(result["mode"], "local_canonical")
        with self.assertRaises(HTTPException):
            assert_scope("another", "yantian-main")
        count = len((await self.send("GET", "/studio/api/export")).json()["qa_history"])
        await self.service.search("合成青竹纹理")
        self.assertEqual(count, len((await self.send("GET", "/studio/api/export")).json()["qa_history"]))

    async def test_npc_does_not_touch_db_or_network_or_claim_identity(self):
        from app.services.npc_service import NPCService
        async def forbidden(*args, **kwargs):
            raise AssertionError("network must not be called")
        with patch("httpx.AsyncClient.post", forbidden):
            answer = await NPCService(BombDB()).chat_with_npc(uuid4(), "徽州三雕是什么", "synthetic-session")
        self.assertEqual(answer["mode"], "extractive")
        self.assertFalse(answer["model_connected"])
        self.assertTrue(answer["citations"])
        greeting = await NPCService(BombDB()).get_greeting(uuid4())
        self.assertIn("演示角色", greeting)
        self.assertNotIn("七十", greeting)

    async def test_real_legacy_chat_http_preserves_citations_auth_and_all_scope_inputs(self):
        # Include the actual legacy HTTP router, retaining its real auth and DB
        # dependency graph. Only the authenticated test principal is simulated.
        from app.api.v1.chat import router, get_db, get_current_user
        self.app.include_router(router, prefix="/api/v1/chat")

        async def isolated_db():
            yield BombDB()

        async def signed_in_test_principal():
            return "synthetic-authenticated-user"

        self.app.dependency_overrides[get_db] = isolated_db
        payload = {"npc_id": str(uuid4()), "message": "徽州三雕是什么", "session_id": "synthetic-http-chat"}
        unauthenticated = await self.send("POST", "/api/v1/chat", payload)
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        self.app.dependency_overrides[get_current_user] = signed_in_test_principal
        answered = await self.send("POST", "/api/v1/chat", payload)
        self.assertEqual(answered.status_code, 200, answered.text)
        data = answered.json()
        self.assertEqual(data["status"], "answered")
        self.assertEqual(data["mode"], "extractive")
        self.assertFalse(data["model_connected"])
        self.assertTrue(data["qa_id"])
        self.assertTrue(data["limitations"])
        self.assertTrue(data["citations"])
        self.assertTrue(all(item["knowledge_version"] == 1 and item["locator"] for item in data["citations"]))
        self.assertTrue(all(item["excerpt"] in data["content"] for item in data["citations"]))
        unknown = await self.send("POST", "/api/v1/chat", {**payload, "message": "严田木刻起源于哪个朝代"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.json()["status"], "insufficient_evidence")
        self.assertEqual(unknown.json()["citations"], [])

        for headers, route, body in [
            ({**HEADERS, "X-Tenant-ID": "other"}, "/api/v1/chat", payload),
            ({**HEADERS, "X-Site-ID": "other"}, "/api/v1/chat", payload),
            (HEADERS, "/api/v1/chat?tenant_id=other", payload),
            (HEADERS, "/api/v1/chat?site_id=other", payload),
            (HEADERS, "/api/v1/chat", {**payload, "tenant_id": "other"}),
            (HEADERS, "/api/v1/chat", {**payload, "site_id": "other"}),
            (HEADERS, "/api/v1/chat", {**payload, "context": {"tenant_id": "other"}}),
            (HEADERS, "/api/v1/chat", {**payload, "context": {"site_id": "other"}}),
            (HEADERS, "/api/v1/chat/greeting", {"npc_id": payload["npc_id"], "context": {"site_id": "other"}}),
        ]:
            response = await self.send("POST", route, body, headers=headers)
            self.assertEqual(response.status_code, 403, (route, response.text))
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual((await self.send("POST", "/api/v1/chat", payload)).status_code, 401)

    async def test_unknown_rights_gate_and_machine_never_queue(self):
        item = await self.add_knowledge(rights_scope="unknown")
        self.assertEqual(await self.service.search("合成青竹纹理"), [])
        for path in ["/api/v1/iot-devices/not-a-uuid/command", "/studio/api/machines/jobs", "/api/v1/search/semantic", "/api/v1/search/health"]:
            result = await self.send("POST" if "command" in path or "jobs" in path or "semantic" in path else "GET", path, {"execute": True})
            self.assertEqual(result.status_code, 423, (path, result.text))
        output = (await self.send("GET", "/studio/api/export")).json()
        self.assertEqual(len(output["designs"]), 0)
        self.assertNotIn("queue", output)
        from app.services.embedding import EmbeddingService
        from app.services.vector_store import VectorStore
        with self.assertRaises(RuntimeError):
            await EmbeddingService()._call_embedding_api(["合成"])
        with self.assertRaises(RuntimeError):
            VectorStore().client

    async def test_restart_uses_same_versions_reviews_qa_and_seed_once(self):
        item = await self.add_knowledge()
        await self.send("PATCH", f"/api/v1/knowledge/{item['id']}", {"base_version": 1, "content": "合成青竹纹理二版。"})
        answer = (await self.send("POST", "/api/local-os/ask", {"question": "合成青竹纹理"})).json()
        draft = (await self.send("POST", "/studio/api/designs", self.draft([item["id"]]))).json()
        await self.send("POST", f"/studio/api/designs/{draft['id']}/reviews", {"version": 1, "reviewer_role": "合成角色", "decision": "revise", "comment": "合成保留意见", "confirmations": {"culture": False, "rights": False, "craft": False}})
        reopened = culture_service_type()(self.path)
        status = await reopened.status()
        self.assertEqual(status["counts"], {"sources": 2, "knowledge": 4, "designs": 1, "reviews": 1})
        exported = await reopened._request("GET", "/api/export")
        self.assertEqual([k["version"] for k in exported["knowledge_versions"] if k["id"] == item["id"]], [1, 2])
        self.assertTrue(any(q["id"] == answer["id"] for q in exported["qa_history"]))
        self.assertEqual(exported["learning_candidates"][0]["state"], "pending_review")
        self.assertNotIn(str(self.path), str(exported))


if __name__ == "__main__":
    unittest.main(verbosity=2)
