"""Operations must inherit the real OS boundary, using temporary files only."""
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.local_os.bridge import culture_service_type
from app.local_os.integration import install_local_os

HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


class OperationsBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.culture = culture_service_type()(root / "culture.sqlite3")
        self.app = FastAPI()
        install_local_os(self.app, service=self.culture, operations_db_path=root / "operations.sqlite3")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)

    async def test_scope_and_origin_apply_to_ledger_and_site_inquiry(self):
        route = "/api/local-os/operations"
        for suffix in ["", "/catalog", "/export"]:
            response = await self.client.get(route + suffix, headers={"X-Tenant-ID": "other"})
            self.assertEqual(response.status_code, 403, response.text)
        body = {"label": "隔离测试意向", "notes": "合成测试", "people": 2, "channel_id": "direct", "source_code": "test"}
        for headers in [{}, {**HEADERS, "Origin": "https://foreign.invalid"}]:
            response = await self.client.post(route + "/inquiries", json=body, headers=headers)
            self.assertEqual(response.status_code, 403, response.text)
        response = await self.client.post(route + "/inquiries", json={**body, "site_id": "other"}, headers=HEADERS)
        self.assertEqual(response.status_code, 403, response.text)
        accepted = await self.client.post(route + "/inquiries", json=body, headers=HEADERS)
        self.assertIn(accepted.status_code, [200, 201], accepted.text)
        self.assertEqual(len((await self.client.get(route)).json()["leads"]), 1)

    async def test_public_preview_does_not_export_ledger_and_culture_is_unchanged(self):
        before = (await self.client.get("/studio/api/export")).json()
        await self.client.post("/api/local-os/operations/leads", headers=HEADERS,
                               json={"label": "隔离合成咨询", "channel_id": "direct", "notes": "私有台账标记", "source_code": "test"})
        catalog = (await self.client.get("/api/local-os/operations/catalog")).json()
        self.assertEqual(catalog["products"], [])
        for key in ["leads", "orders", "payments", "refunds", "content_drafts"]:
            self.assertNotIn(key, catalog)
        self.assertNotIn("私有台账标记", str(catalog))
        after = (await self.client.get("/studio/api/export")).json()
        self.assertEqual({key: value for key, value in before.items() if isinstance(value, list)},
                         {key: value for key, value in after.items() if isinstance(value, list)})
        status = (await self.client.get("/api/local-os/status")).json()
        self.assertEqual(status["operations_url"], "/operations")
        self.assertFalse(status["machines"]["enabled"])
        self.assertFalse(status["operations"]["payments_connected"])

    async def test_one_file_cannot_be_both_knowledge_and_operations(self):
        with self.assertRaises(RuntimeError):
            install_local_os(FastAPI(), service=self.culture, operations_db_path=self.culture.db_path)


if __name__ == "__main__":
    unittest.main()
