"""Layer-one HTTP acceptance: fictional inputs and temporary databases only."""
from copy import deepcopy
import base64
import io
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import tempfile
import unittest
import zipfile
import zlib

from fastapi import FastAPI
import httpx

from app.local_os.bridge import culture_service_type
from app.local_os.integration import install_local_os
from app.local_os.workspace import read_workspace_plan
from local_tests.test_room_status import fixture, summary_for


BASE = "/api/local-os/workspace"
HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


def photo():
    def chunk(kind, data):
        return struct.pack("!I", len(data))+kind+data+struct.pack("!I", zlib.crc32(kind+data)&0xffffffff)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack("!2I5B", 2, 2, 8, 2, 0, 0, 0))+chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\x00\xff\x00"*2))+chunk(b"IEND", b"")


def ooxml(extension, extra=None):
    if extension == "docx":
        main, content_type = "word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        content = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>木刻 2026-11-14 PRIVATE_SYNTHETIC_RECORD 13900000000</w:t></w:r></w:p></w:body></w:document>'
        parts = {main: content}
    else:
        main, content_type = "xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
        parts = {main: '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
                 "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>纸伞 11月21日 PRIVATE_SYNTHETIC_RECORD</t></is></c><c><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'}
    parts["[Content_Types].xml"] = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/'+main+'" ContentType="'+content_type+'"/></Types>'
    parts["_rels/.rels"] = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    parts.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return stream.getvalue()


def pdf():
    content = b"BT /F1 12 Tf 20 100 Td (2026-11-14 PRIVATE_SYNTHETIC_RECORD) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length "+str(len(content)).encode()+b" >>\nstream\n"+content+b"\nendstream"]
    output = b"%PDF-1.4\n"
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output += str(index).encode()+b" 0 obj\n"+value+b"\nendobj\n"
    start = len(output)
    output += b"xref\n0 6\n0000000000 65535 f \n"+b"".join(f"{value:010d} 00000 n \n".encode() for value in offsets[1:])
    return output+b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"+str(start).encode()+b"\n%%EOF\n"


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"operations.sqlite3"
        self.context_path = self.db.parent/"yantian-growth-context.json"
        self.context = {"version": 1, "checked_at": "2099-01-01", "products": [
            {"id": key, "title": title, "summary": title+"合成目录候选", "status": "LOCAL_IMPLEMENTED_CATALOG",
             "conditions": ["时长、人员、材料和接待条件待核"], "model_price": 999999,
             "source_refs": [{"title": "合成目录", "locator": "data.js routes["+key+"]", "evidence_status": "local_config_reference"}]}
            for key, title in [("R01", "自然花园观察"), ("R02", "农场任务"), ("R03", "徽派木刻"), ("R04", "纸伞与陶瓷"), ("R05", "雨天婺剧")]],
            "materials": [], "facts": [], "missing": []}
        self.context_path.write_text(json.dumps(self.context, ensure_ascii=False))
        self.app = self.make_app()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)

    def make_app(self):
        app = FastAPI()
        service = culture_service_type()(self.db.parent/"culture.sqlite3")
        install_local_os(app, service=service, operations_db_path=self.db)
        return app

    async def post(self, path, value):
        return await self.client.post(BASE+path, json=value, headers=HEADERS)

    async def plan(self, brief="推广严田住宿与文化体验", **kwargs):
        response = await self.post("/plans", {"brief": brief, "attachment_ids": [], **kwargs})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def upload(self, name, data, mime):
        return await self.client.post(BASE+"/attachments", files={"file": (name, data, mime)}, headers=HEADERS)

    async def import_rooms(self, value=None):
        response = await self.client.post("/api/local-os/room-status/imports", json=value or fixture(), headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["active_snapshot"]

    def rows(self, prefix):
        with sqlite3.connect(self.db) as conn:
            return {name: conn.execute("SELECT * FROM "+name+" ORDER BY rowid").fetchall()
                    for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (prefix+"_%",))}

    async def test_empty_contract_readonly_helper_and_source_boundaries(self):
        missing = self.db.parent/"does-not-exist.sqlite3"
        self.assertIsNone(read_workspace_plan(missing, "x"))
        self.assertFalse(missing.exists())
        response = await self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()
        self.assertEqual(snapshot["plans"], [])
        self.assertEqual(snapshot["attachments"], [])
        self.assertIsNone(snapshot["reference_summary"]["room_status"])
        self.assertEqual(len(snapshot["reference_summary"]["create_routes"]), 5)
        self.assertEqual((await self.post("/plans", {"brief": "", "attachment_ids": []})).status_code, 422)
        plan = await self.plan()
        self.assertEqual([item["id"] for item in plan["plan"]["offering"]["experience_candidates"]], ["R01", "R03"])
        self.assertEqual(plan["request"]["room_status_ref"], None)
        self.assertEqual(plan["generation_mode"], "local_rules")
        self.assertFalse(plan["confirmation_valid"])
        self.assertNotIn("999999", json.dumps(plan))

    async def test_distinct_input_has_relevant_audiences_routes_and_channels(self):
        family = await self.plan("亲子家庭推广住宿和木刻，主要放小红书")
        couple = await self.plan("情侣二人住宿和纸伞陶瓷，先做抖音")
        first, second = family["plan"], couple["plan"]
        self.assertNotEqual(first["title"], second["title"])
        self.assertIn("亲子", first["objective"])
        self.assertIn("情侣", second["objective"])
        self.assertEqual([item["id"] for item in first["offering"]["experience_candidates"]], ["R03"])
        self.assertEqual([item["id"] for item in second["offering"]["experience_candidates"]], ["R04"])
        self.assertEqual(first["channels"][0]["id"], "xiaohongshu")
        self.assertEqual(second["channels"][0]["id"], "douyin")
        self.assertNotEqual(first["actions"][1]["description"], second["actions"][1]["description"])
        self.assertTrue(all(item["state"] == "hypothesis" for item in first["audiences"]+second["audiences"]))
        for plan in [family, couple]:
            self.assertEqual(plan["status"], "draft")
            self.assertNotIn("storyboard", json.dumps(plan))
            self.assertTrue(all(item["status"] == "LOCAL_IMPLEMENTED_CATALOG" and item["checklist"] for item in plan["plan"]["offering"]["experience_candidates"]))

    async def test_confirmation_dedupe_revision_and_no_business_or_video_writes(self):
        before = self.rows("op"), self.rows("gr")
        plan = await self.plan()
        self.assertEqual((await self.plan())["id"], plan["id"])
        self.assertEqual((await self.plan(base_plan_id=plan["id"]))["id"], plan["id"])
        self.assertEqual((await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": "0"*64})).status_code, 409)
        self.assertEqual((await self.post("/plans/"+plan["id"]+"/video-handoffs", {"plan_hash": plan["hash"]})).status_code, 409)
        response = await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["confirmation_valid"])
        self.assertFalse(response.json()["confirmation"]["identity_verified"])
        self.assertEqual(before, (self.rows("op"), self.rows("gr")))
        changed = await self.plan("朋友住宿与纸伞", base_plan_id=plan["id"])
        self.assertEqual(changed["version"], 2)
        self.assertEqual(changed["parent_plan_id"], plan["id"])
        self.assertEqual(changed["status"], "draft")
        self.assertFalse(read_workspace_plan(self.db, plan["id"])["confirmation_valid"])
        self.assertEqual((await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})).status_code, 409)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.make_app()), base_url="http://testserver") as other:
            snapshot = (await other.get(BASE)).json()
        self.assertEqual(len(snapshot["plans"]), 2)
        self.assertEqual(next(item for item in snapshot["plans"] if item["id"] == plan["id"])["hash"], plan["hash"])

    async def test_context_change_invalidates_exact_confirmation_and_regeneration(self):
        plan = await self.plan()
        await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})
        self.context["version"] = 2
        self.context_path.write_text(json.dumps(self.context))
        self.assertTrue(read_workspace_plan(self.db, plan["id"])["source_stale"])
        self.assertFalse(read_workspace_plan(self.db, plan["id"])["confirmation_valid"])
        self.assertEqual((await self.post("/plans/"+plan["id"]+"/video-handoffs", {"plan_hash": plan["hash"]})).status_code, 409)
        fresh = await self.plan()
        self.assertNotEqual(fresh["hash"], plan["hash"])
        self.assertFalse(fresh["source_stale"])

    async def test_dates_preserved_actual_window_cells_and_explicit_request_reference(self):
        before = self.rows("op")
        room = await self.import_rooms()
        plan = await self.plan("亲子住宿木刻，目标日期2026-11-14，小红书")
        self.assertIn("2026-11-14", plan["request"]["brief"])
        self.assertIn("2026-11-14", plan["plan"]["date_focus"])
        self.assertEqual(plan["room_status_ref"]["snapshot_id"], room["id"])
        source = next(item for item in plan["plan"]["sources"] if item["kind"] == "room_window")
        self.assertIn("Sheet1!J4", source["locator"])
        self.assertIn("Sheet1!J5", source["locator"])
        self.assertIsNone(plan["request"]["room_status_ref"])
        explicit = await self.plan("核对2026-11-26至2026-11-28住宿", room_status_ref={"snapshot_id": room["id"], "opportunity_id": room["opportunities"][2]["id"]})
        self.assertEqual(explicit["request"]["room_status_ref"], explicit["room_status_ref"])
        self.assertIn("2026-11-26至2026-11-28", explicit["request"]["brief"])
        self.assertIsNone(room["room_capacity"]["current_sellable_total"])
        self.assertEqual(before, self.rows("op"))
        await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})
        revised = fixture()
        revised["period_resolution"]["basis"] = "operator confirmed year 2026"
        await self.import_rooms(revised)
        self.assertTrue(read_workspace_plan(self.db, plan["id"])["source_stale"])
        self.assertFalse(read_workspace_plan(self.db, plan["id"])["confirmation_valid"])

    async def test_unknown_unconfirmed_and_uncovered_target_never_become_available(self):
        room = await self.import_rooms()
        for brief in ["2026-12-05亲子住宿", "11月16日朋友住宿", "2026-11-02住宿"]:
            plan = await self.plan(brief)
            self.assertIsNone(plan["room_status_ref"])
            self.assertIn("未匹配", plan["plan"]["date_focus"])
            self.assertIn("不推断空房", plan["plan"]["date_focus"])
        all_unknown = fixture()
        for row in all_unknown["observations"]:
            row.update(observed_status="UNKNOWN_BLANK", source_reported_reservation_quantity=None, source_color=None, source_legend_cell=None)
        all_unknown["summary"] = summary_for(all_unknown["observations"])
        unknown = await self.import_rooms(all_unknown)
        self.assertEqual(unknown["opportunities"], [])
        self.assertIsNone((await self.plan("2026-11-14亲子住宿"))["room_status_ref"])
        response = await self.post("/plans", {"brief": "住宿", "room_status_ref": {"snapshot_id": unknown["id"], "opportunity_id": room["opportunities"][0]["id"]}})
        self.assertEqual(response.status_code, 422)

    async def test_text_attachment_private_body_omitted_topics_dates_used_and_file_private(self):
        await self.import_rooms()
        private = "木刻 11月21日\n姓名：PRIVATE_SYNTHETIC_RECORD\n电话：13900000000\nprivate@example.invalid".encode()
        for extension, mime in [("txt", "text/plain"), ("md", "text/markdown"), ("csv", "text/csv")]:
            # Distinct bytes avoid dedup being tested instead of each parser.
            response = await self.upload("private-name."+extension, private+extension.encode(), mime)
            self.assertEqual(response.status_code, 200, response.text)
            item = response.json()
            self.assertEqual(item["read_status"], "text_extracted")
            self.assertIn("木刻", item["topics"])
            self.assertEqual(item["date_hints"], ["11月21日"])
            plan = await self.plan("", attachment_ids=[item["id"]])
            self.assertIn("2026-11-21", plan["plan"]["date_focus"])
            self.assertEqual(plan["plan"]["offering"]["experience_candidates"][0]["id"], "R03")
            packed = json.dumps(item)+json.dumps(plan)
            for secret in ["PRIVATE_SYNTHETIC_RECORD", "13900000000", "private@example.invalid", "private-name"]:
                self.assertNotIn(secret, packed)
        with sqlite3.connect(self.db) as conn:
            content = " ".join(row[0] for table in ["ws_attachments", "ws_plans"] for row in conn.execute("SELECT data FROM "+table))
        self.assertNotIn("PRIVATE_SYNTHETIC_RECORD", content)
        files = list((self.db.parent/"workspace-attachments").iterdir())
        self.assertEqual(len(files), 3)
        self.assertTrue(all((file.stat().st_mode & 0o777) == 0o600 for file in files))

    async def test_docx_xlsx_pdf_real_parsers_keep_only_safe_clues(self):
        for name, blob, mime, topic in [
            ("test.docx", ooxml("docx"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "木刻"),
            ("test.xlsx", ooxml("xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "油纸伞"),
            ("test.pdf", pdf(), "application/pdf", None),
        ]:
            response = await self.upload(name, blob, mime)
            self.assertEqual(response.status_code, 200, response.text)
            item = response.json()
            self.assertEqual(item["read_status"], "text_extracted", item)
            if topic:
                self.assertIn(topic, item["topics"])
            self.assertTrue(item["date_hints"])
            plan = await self.plan("", attachment_ids=[item["id"]])
            self.assertNotIn("PRIVATE_SYNTHETIC_RECORD", json.dumps(item)+json.dumps(plan))
            self.assertNotIn("13900000000", json.dumps(item)+json.dumps(plan))

    async def test_real_photo_decode_dedup_safe_preview_and_no_visual_claim(self):
        data = photo()
        variants = [("test.png", data, "image/png"),
                    ("test.webp", base64.b64decode("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA"), "image/webp")]
        for extension, codec, mime in [("jpg", "mjpeg", "image/jpeg")]:
            converted = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-frames:v", "1", "-f", "image2pipe", "-c:v", codec, "pipe:1"], input=data, capture_output=True, timeout=10)
            self.assertEqual(converted.returncode, 0)
            variants.append(("test."+extension, converted.stdout, mime))
        for name, blob, mime in variants:
            response = await self.upload(name, blob, mime)
            self.assertEqual(response.status_code, 200, response.text)
            item = response.json()
            self.assertEqual(item["kind"], "photo")
            self.assertEqual(item["read_status"], "visual_reference")
            self.assertEqual((await self.upload(name, blob, mime)).json()["id"], item["id"])
            self.assertEqual((await self.client.get(item["preview_url"])).content, blob)
            self.assertEqual((await self.client.get(item["preview_url"], headers={"Origin": "https://other.invalid"})).status_code, 403)
            self.assertEqual((await self.client.get(item["preview_url"], headers={"Sec-Fetch-Site": "cross-site"})).status_code, 403)
            plan = await self.plan("", attachment_ids=[item["id"]])
            self.assertTrue(any("没有完成视觉理解" in item for item in plan["plan"]["checks"]))
            await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})
            with sqlite3.connect(self.db) as conn:
                storage = json.loads(conn.execute("SELECT data FROM ws_attachments WHERE id=?", (item["id"],)).fetchone()[0])["storage_name"]
            (self.db.parent/"workspace-attachments"/storage).write_bytes(b"changed")
            self.assertEqual((await self.client.get(item["preview_url"])).status_code, 409)
            self.assertFalse(read_workspace_plan(self.db, plan["id"])["confirmation_valid"])
            self.assertEqual((await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})).status_code, 409)

    async def test_unsafe_files_and_zip_limits_rejected_without_metadata_or_orphans(self):
        before = self.rows("ws")
        cases = [("test.svg", b"<svg/>", "image/svg+xml"), ("test.html", b"<html/>", "text/html"),
                 ("test.pdf", b"%PDF-fake", "application/pdf"),
                 ("test.png", b"\x89PNG\r\n\x1a\nfake", "image/png"), ("../outside.txt", b"x", "text/plain"),
                 ("test.jpg", photo(), "image/jpeg"), ("test.txt", b"<!DOCTYPE x><x/>", "text/plain"),
                 ("test.docx", ooxml("docx", {"../escape.xml": "<x/>"}), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                 ("test.docx", ooxml("docx", {"word/vbaProject.bin": b"macro"}), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                 ("test.docx", ooxml("docx", {"word/unsafe.xml": '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'}), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                 ("test.docx", ooxml("docx", {f"x{n}.xml": "<x/>" for n in range(129)}), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                 ("test.xlsx", ooxml("xlsx", {"large.xml": "x"*(4*1024*1024+1)}), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        for name, blob, mime in cases:
            response = await self.upload(name, blob, mime)
            self.assertEqual(response.status_code, 422, (name, response.text))
            self.assertNotIn("file:///etc", response.text)
        self.assertEqual((await self.upload("large.txt", b"a"*(10*1024*1024+1), "text/plain")).status_code, 413)
        self.assertEqual(before, self.rows("ws"))
        self.assertEqual(list((self.db.parent/"workspace-attachments").iterdir()), [])

    async def test_same_origin_scope_and_raw_fields_gate_real_routes(self):
        for headers in [{}, {"X-Yantian-Local": "1", "Origin": "https://other.invalid"}, {**HEADERS, "X-Tenant-ID": "other"}]:
            response = await self.client.post(BASE+"/plans", json={"brief": "住宿"}, headers=headers)
            self.assertEqual(response.status_code, 403, response.text)
        for body in [{"brief": "住宿", "tenant_id": "other"}, {"brief": "住宿", "site_id": "other"}]:
            self.assertEqual((await self.post("/plans", body)).status_code, 403)
        for query in ["?site_id=other", "?tenant_id=other"]:
            self.assertEqual((await self.client.get(BASE+query)).status_code, 403)
        self.assertEqual((await self.post("/plans", {"brief": "住宿", "raw_records": ["private"]})).status_code, 422)
        self.assertEqual((await self.post("/plans", {"brief": "住宿", "attachment_ids": ["not-uploaded"]})).status_code, 409)
        result = await self.client.post(BASE+"/attachments", files={"file": ("ok.txt", b"safe", "text/plain")}, data={"raw_note": "private"}, headers=HEADERS)
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.rows("ws")["ws_plans"], [])

    async def test_handoff_explicit_separate_idempotent_task_and_no_scripts_or_operations(self):
        before = self.rows("op")
        plan = await self.plan("亲子住宿木刻")
        await self.post("/plans/"+plan["id"]+"/confirm", {"plan_hash": plan["hash"]})
        first = await self.post("/plans/"+plan["id"]+"/video-handoffs", {"plan_hash": plan["hash"]})
        self.assertEqual(first.status_code, 200, first.text)
        second = await self.post("/plans/"+plan["id"]+"/video-handoffs", {"plan_hash": plan["hash"]})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["campaign_id"], second.json()["campaign_id"])
        self.assertTrue(first.json()["url"].startswith("/growth?"))
        self.assertFalse(first.json()["scripts_generated"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["provider_calls"], [])
        self.assertEqual(first.json()["external_side_effects"], [])
        rows = self.rows("gr")
        self.assertEqual(len(rows["gr_campaigns"]), 1)
        self.assertEqual(rows["gr_packages"], [])
        self.assertEqual(before, self.rows("op"))
        self.assertEqual(len(self.rows("ws")["ws_video_handoffs"]), 1)


if __name__ == "__main__":
    unittest.main()
