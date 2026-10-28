"""Direct unittest + temporary SQLite; never load the destructive conftest."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app.local_os.operations import create_operations_router


PREFIX = "/api/local-os/operations"
HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


class OperationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "operations.sqlite3"
        self.app = FastAPI()
        self.app.include_router(create_operations_router(str(self.path)))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver", headers=HEADERS)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def send(self, method, suffix="", body=None):
        return await self.client.request(method, PREFIX + suffix, json=body)

    async def snapshot(self):
        response = await self.send("GET")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def room(self, code="SYN-A"):
        response = await self.send("POST", "/rooms", {"code": code, "name": "合成房间", "room_type": "合成房型"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def product(self, kind="stay", **updates):
        data = {"title": "合成产品", "kind": kind, "price_cents": 38000, "status": "active", "description": "仅用于本地合成测试",
                "delivery_confirmed": kind != "stay", "facilitator": "合成负责人" if kind != "stay" else "", "duration_minutes": 60 if kind != "stay" else None, **updates}
        response = await self.send("POST", "/products", data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def session(self, product, capacity=2, confirmed=True):
        response = await self.send("POST", "/sessions", {"product_id": product["id"], "starts_at": "2099-01-01T10:00:00+08:00", "capacity": capacity, "delivery_confirmed": confirmed})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def order_payload(self, product, rooms=(), **updates):
        return {"label": "合成订单", "product_id": product["id"], "room_ids": list(rooms),
                "start_date": "2099-01-01" if rooms else None, "end_date": "2099-01-03" if rooms else None,
                "session_id": None, "seats": 0, "amount_cents": 12345, "channel_id": "direct", "source_code": "SYN-SOURCE",
                "lead_id": None, "hold_minutes": 30, "idempotency_key": "SYN-ORDER", **updates}

    async def order(self, product, rooms=(), **updates):
        response = await self.send("POST", "/orders", self.order_payload(product, rooms, **updates))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def availability(self, start="2099-01-01", end="2099-01-03"):
        return (await self.send("GET", f"/availability?start_date={start}&end_date={end}")).json()

    async def test_initial_has_only_user_statements_and_no_invented_business(self):
        data = await self.snapshot()
        self.assertEqual(data["settings"]["room_capacity"], 30)
        self.assertEqual(data["settings"]["reference_price_cents"], 38000)
        self.assertEqual(data["settings"]["season"], "淡季")
        for table in ["rooms", "blocks", "products", "sessions", "leads", "content_drafts", "orders", "payments", "refunds"]:
            self.assertEqual(data[table], [])
        self.assertEqual(data["summary"]["cash_record_state"], "MISSING")
        self.assertIsNone(data["summary"]["received_cents"])
        self.assertIsNone(data["summary"]["revenue_cents"])
        available = await self.availability()
        self.assertEqual(available["available_rooms"], 0)
        self.assertEqual(available["unregistered_rooms"], 30)
        self.assertTrue(all(channel["status"] in {"not_opened", "not_connected"} for channel in data["channels"]))

    async def test_room_limit_disable_and_checkout_exclusive_boundaries(self):
        room = await self.room()
        product = await self.product()
        order = await self.order(product, [room["id"]])
        self.assertEqual(order["amount_cents"], 12345)
        self.assertEqual((await self.send("POST", "/orders", self.order_payload(product, [room["id"]], idempotency_key="SYN-CONFLICT", start_date="2099-01-02", end_date="2099-01-04"))).status_code, 409)
        self.assertEqual((await self.send("PATCH", "/rooms/"+room["id"], {"enabled": False})).status_code, 409)
        back_to_back = await self.order(product, [room["id"]], idempotency_key="SYN-NEXT", start_date="2099-01-03", end_date="2099-01-04")
        self.assertEqual(back_to_back["status"], "hold")
        available = await self.availability("2099-01-04", "2099-01-05")
        self.assertEqual(available["available_rooms"], 1)
        for index in range(29):
            await self.room("SYN-" + str(index))
        self.assertEqual((await self.send("POST", "/rooms", {"code": "SYN-OVER", "name": "合成", "room_type": "合成"})).status_code, 409)

    async def test_blocks_and_disabled_rooms_reasons_release_preserves_record(self):
        room = await self.room()
        product = await self.product()
        block = (await self.send("POST", "/blocks", {"room_id": room["id"], "start_date": "2099-01-01", "end_date": "2099-01-03", "reason": "合成维护"})).json()
        available = await self.availability()
        self.assertFalse(available["rooms"][0]["available"])
        self.assertEqual(available["rooms"][0]["conflicts"][0]["kind"], "block")
        self.assertEqual((await self.send("POST", "/orders", self.order_payload(product, [room["id"]]))).status_code, 409)
        released = await self.send("POST", f"/blocks/{block['id']}/release", {})
        self.assertEqual(released.json()["status"], "released")
        self.assertEqual((await self.availability())["available_rooms"], 1)
        order = await self.order(product, [room["id"]])
        self.assertEqual((await self.send("POST", "/blocks", {"room_id": room["id"], "start_date": "2099-01-02", "end_date": "2099-01-03", "reason": "冲突维护"})).status_code, 409)
        await self.send("POST", f"/orders/{order['id']}/cancel", {})
        disabled = await self.send("PATCH", f"/rooms/{room['id']}", {"enabled": False})
        self.assertFalse(disabled.json()["enabled"])
        self.assertEqual((await self.availability())["rooms"][0]["conflicts"][0]["kind"], "disabled")

    async def test_experience_confirmation_capacity_and_bundle_atomicity(self):
        product = await self.product("experience")
        provisional = await self.session(product, confirmed=False)
        payload = self.order_payload(product, session_id=provisional["id"], seats=1)
        self.assertEqual((await self.send("POST", "/orders", payload)).status_code, 409)
        session = await self.session(product, capacity=2)
        await self.order(product, session_id=session["id"], seats=2)
        self.assertEqual((await self.send("POST", "/orders", self.order_payload(product, session_id=session["id"], seats=1, idempotency_key="OVER"))).status_code, 409)
        bundle = await self.product("bundle")
        bundle_session = await self.session(bundle, capacity=1)
        first, second = await self.room("SYN-ONE"), await self.room("SYN-TWO")
        await self.order(bundle, [first["id"]], session_id=bundle_session["id"], seats=1, idempotency_key="BUNDLE-ONE")
        rejected = await self.send("POST", "/orders", self.order_payload(bundle, [second["id"]], session_id=bundle_session["id"], seats=1, idempotency_key="BUNDLE-TWO"))
        self.assertEqual(rejected.status_code, 409)
        result = await self.availability()
        self.assertTrue(next(room for room in result["rooms"] if room["id"] == second["id"])["available"])
        state = await self.snapshot()
        self.assertEqual(len(state["orders"]), 2)
        self.assertEqual(next(s for s in state["sessions"] if s["id"] == bundle_session["id"])["remaining_capacity"], 0)

    async def test_expiry_releases_unpaid_hold_but_not_any_paid_hold(self):
        room = await self.room()
        product = await self.product()
        baseline = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("app.local_os.operations.utcnow", return_value=baseline):
            order = await self.order(product, [room["id"]])
        with patch("app.local_os.operations.utcnow", return_value=baseline+timedelta(minutes=31)):
            data = await self.snapshot()
            self.assertEqual(data["orders"][0]["status"], "expired")
            self.assertEqual((await self.availability())["available_rooms"], 1)
            self.assertEqual((await self.send("POST", f"/orders/{order['id']}/payments", {"amount_cents": 1, "receipt_ref": "SYN-R", "idempotency_key": "EXPIRED-PAY"})).status_code, 409)
            paid_order = await self.order(product, [room["id"]], idempotency_key="PARTIAL-HOLD")
            response = await self.send("POST", f"/orders/{paid_order['id']}/payments", {"amount_cents": 1, "receipt_ref": "SYN-R2", "idempotency_key": "PARTIAL-PAY"})
            self.assertEqual(response.json()["order"]["payment_status"], "partial")
        with patch("app.local_os.operations.utcnow", return_value=baseline+timedelta(days=2)):
            data = await self.snapshot()
            self.assertEqual(next(o for o in data["orders"] if o["id"] == paid_order["id"])["status"], "hold")
            self.assertEqual((await self.availability())["available_rooms"], 0)

    async def test_order_payment_refund_idempotency_bounds_cancel_separation(self):
        room = await self.room()
        product = await self.product()
        payload = self.order_payload(product, [room["id"]])
        order = (await self.send("POST", "/orders", payload)).json()
        self.assertEqual((await self.send("POST", "/orders", payload)).json()["id"], order["id"])
        self.assertEqual((await self.send("POST", "/orders", {**payload, "amount_cents": 99})).status_code, 409)
        self.assertEqual((await self.send("POST", f"/orders/{order['id']}/confirm", {})).status_code, 409)
        self.assertEqual((await self.send("POST", f"/orders/{order['id']}/fulfill", {})).status_code, 409)
        payment = {"amount_cents": 12345, "receipt_ref": "SYN-RECEIPT", "idempotency_key": "SYN-PAY"}
        route = f"/orders/{order['id']}/payments"
        result = (await self.send("POST", route, payment)).json()
        self.assertEqual(result["order"]["status"], "confirmed")
        self.assertFalse(result["payment"]["independently_verified"])
        self.assertEqual((await self.send("POST", route, payment)).json()["payment"]["id"], result["payment"]["id"])
        self.assertEqual((await self.send("POST", route, {**payment, "amount_cents": 12344})).status_code, 409)
        self.assertEqual((await self.send("POST", route, {**payment, "idempotency_key": "OVER-PAY", "amount_cents": 1})).status_code, 409)
        cancelled = (await self.send("POST", f"/orders/{order['id']}/cancel", {})).json()
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["received_cents"], 12345)
        self.assertEqual(cancelled["refunded_cents"], 0)
        self.assertEqual((await self.availability())["available_rooms"], 1)
        refund = {"amount_cents": 12345, "receipt_ref": "SYN-REFUND", "idempotency_key": "SYN-REF"}
        refund_route = f"/orders/{order['id']}/refunds"
        result = (await self.send("POST", refund_route, refund)).json()
        self.assertEqual(result["order"]["payment_status"], "refunded")
        self.assertEqual((await self.send("POST", refund_route, refund)).json()["refund"]["id"], result["refund"]["id"])
        self.assertEqual((await self.send("POST", refund_route, {**refund, "amount_cents": 1, "idempotency_key": "OVER-REF"})).status_code, 409)
        self.assertEqual((await self.send("POST", refund_route, {**refund, "receipt_ref": "DIFFERENT"})).status_code, 409)
        state = await self.snapshot()
        self.assertEqual(len(state["orders"]), 1)
        self.assertEqual(len(state["payments"]), 1)
        self.assertEqual(len(state["refunds"]), 1)
        self.assertEqual(state["summary"]["net_received_cents"], 0)
        self.assertIsNone(state["summary"]["revenue_cents"])

    async def test_concurrent_orders_never_oversell_room(self):
        room, product = await self.room(), await self.product()
        async def reserve_in_own_loop(key):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver", headers=HEADERS) as client:
                response = await client.post(PREFIX+"/orders", json=self.order_payload(product, [room["id"]], idempotency_key=key))
                return response.status_code
        def worker(key):
            return asyncio.run(reserve_in_own_loop(key))
        statuses = await asyncio.gather(asyncio.to_thread(worker, "THREAD-A"), asyncio.to_thread(worker, "THREAD-B"))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(len((await self.snapshot())["orders"]), 1)

    async def test_fulfillment_time_gate_and_inventory_history_remain_reserved(self):
        room, product = await self.room(), await self.product()
        baseline = datetime(2098, 12, 31, tzinfo=timezone.utc)
        with patch("app.local_os.operations.utcnow", return_value=baseline):
            order = await self.order(product, [room["id"]])
            await self.send("POST", f"/orders/{order['id']}/payments", {"amount_cents": 12345, "receipt_ref": "SYN-PAID", "idempotency_key": "FULFILL-PAY"})
            self.assertEqual((await self.send("POST", f"/orders/{order['id']}/fulfill", {})).status_code, 409)
        with patch("app.local_os.operations.utcnow", return_value=datetime(2099, 1, 3, tzinfo=timezone.utc)):
            fulfilled = await self.send("POST", f"/orders/{order['id']}/fulfill", {})
            self.assertEqual(fulfilled.json()["status"], "fulfilled")
            self.assertEqual((await self.availability())["available_rooms"], 0)
            self.assertEqual((await self.send("POST", "/orders", self.order_payload(product, [room["id"]], idempotency_key="FULFILLED-DOUBLE"))).status_code, 409)
        experience = await self.product("experience")
        session = await self.session(experience, capacity=1)
        with patch("app.local_os.operations.utcnow", return_value=baseline):
            experience_order = await self.order(experience, session_id=session["id"], seats=1, idempotency_key="FULFILL-EXP")
            await self.send("POST", f"/orders/{experience_order['id']}/payments", {"amount_cents": 12345, "receipt_ref": "SYN-EXP-PAID", "idempotency_key": "FULFILL-EXP-PAY"})
        with patch("app.local_os.operations.utcnow", return_value=datetime(2099, 1, 1, 2, 30, tzinfo=timezone.utc)):
            self.assertEqual((await self.send("POST", f"/orders/{experience_order['id']}/fulfill", {})).status_code, 409)
        with patch("app.local_os.operations.utcnow", return_value=datetime(2099, 1, 1, 3, 0, tzinfo=timezone.utc)):
            self.assertEqual((await self.send("POST", f"/orders/{experience_order['id']}/fulfill", {})).json()["status"], "fulfilled")
            state = await self.snapshot()
            self.assertEqual(next(s for s in state["sessions"] if s["id"] == session["id"])["remaining_capacity"], 0)

    async def test_past_sessions_and_bundle_shanghai_calendar_policy(self):
        bundle = await self.product("bundle")
        room = await self.room()
        async def make_time(value):
            return (await self.send("POST", "/sessions", {"product_id": bundle["id"], "starts_at": value, "capacity": 2, "delivery_confirmed": True})).json()
        checkout_day = await make_time("2099-01-02T18:00:00Z")  # Shanghai Jan 3.
        outside = await make_time("2099-01-03T18:00:00Z")  # Shanghai Jan 4.
        with patch("app.local_os.operations.utcnow", return_value=datetime(2098, 1, 1, tzinfo=timezone.utc)):
            rejected = await self.send("POST", "/orders", self.order_payload(bundle, [room["id"]], session_id=outside["id"], seats=1, idempotency_key="OUTSIDE"))
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual((await self.availability())["available_rooms"], 1)
            accepted = await self.send("POST", "/orders", self.order_payload(bundle, [room["id"]], session_id=checkout_day["id"], seats=1, idempotency_key="CHECKOUT-DAY"))
            self.assertEqual(accepted.status_code, 200, accepted.text)
        experience = await self.product("experience")
        session = await self.session(experience)
        with patch("app.local_os.operations.utcnow", return_value=datetime(2099, 1, 2, tzinfo=timezone.utc)):
            rejected = await self.send("POST", "/orders", self.order_payload(experience, session_id=session["id"], seats=1, idempotency_key="PAST"))
            self.assertEqual(rejected.status_code, 409)

    async def test_net_receipts_control_confirmation_and_fully_refunded_hold_expires(self):
        room, product = await self.room(), await self.product()
        baseline = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("app.local_os.operations.utcnow", return_value=baseline):
            order = await self.order(product, [room["id"]], amount_cents=100)
            route = f"/orders/{order['id']}"
            await self.send("POST", route+"/payments", {"amount_cents": 50, "receipt_ref": "SYN-50-A", "idempotency_key": "NET-PAY-A"})
            await self.send("POST", route+"/refunds", {"amount_cents": 50, "receipt_ref": "SYN-50-REF", "idempotency_key": "NET-REF-A"})
            after = await self.send("POST", route+"/payments", {"amount_cents": 50, "receipt_ref": "SYN-50-B", "idempotency_key": "NET-PAY-B"})
            self.assertEqual(after.json()["order"]["status"], "hold")
            self.assertEqual(after.json()["order"]["net_received_cents"], 50)
            self.assertNotEqual(after.json()["order"]["payment_status"], "paid")
            self.assertEqual((await self.send("POST", route+"/confirm", {})).status_code, 409)
        with patch("app.local_os.operations.utcnow", return_value=baseline+timedelta(minutes=31)):
            self.assertEqual((await self.availability())["available_rooms"], 0)
            refunded = await self.send("POST", route+"/refunds", {"amount_cents": 50, "receipt_ref": "SYN-50-FINAL", "idempotency_key": "NET-REF-B"})
            self.assertEqual(refunded.json()["order"]["status"], "expired")
            self.assertEqual((await self.availability())["available_rooms"], 1)

    async def test_validation_and_scope_failures(self):
        product = await self.product()
        room = await self.room()
        valid = self.order_payload(product, [room["id"]])
        for updates in [{"amount_cents": 1.2}, {"amount_cents": True}, {"amount_cents": -1},
                        {"start_date": "2099-02-30"}, {"end_date": "2099-01-01"},
                        {"room_ids": [room["id"], room["id"]]}, {"hold_minutes": 0},
                        {"label": "x"*121}, {"unexpected": "value"}]:
            self.assertEqual((await self.send("POST", "/orders", {**valid, **updates})).status_code, 422)
        self.assertEqual((await self.send("POST", "/orders", {**valid, "tenant_id": "other"})).status_code, 403)
        self.assertEqual((await self.send("GET", "/availability?start_date=wrong&end_date=2099-01-04")).status_code, 422)
        self.assertEqual((await self.send("POST", "/products", {"title": "未确认体验", "kind": "experience", "status": "active", "delivery_confirmed": False})).status_code, 422)
        experience = await self.product("experience")
        self.assertEqual((await self.send("POST", "/sessions", {"product_id": experience["id"], "starts_at": "2099-01-01T10:00:00", "capacity": 2, "delivery_confirmed": True})).status_code, 422)

    async def test_catalog_inquiry_content_export_persistence_and_kind_snapshot(self):
        product = await self.product("experience")
        await self.product("stay", status="draft")
        session = await self.session(product)
        inquiry = await self.send("POST", "/inquiries", {"label": "合成本地咨询", "notes": "仅意向", "people": 2, "source_code": "SYN-SITE", "channel_id": "direct"})
        self.assertEqual(inquiry.status_code, 200, inquiry.text)
        self.assertEqual(inquiry.json()["status"], "new")
        self.assertEqual((await self.send("POST", "/inquiries", {"label": "合成", "source_code": "SYN", "channel_id": "douyin"})).status_code, 422)
        content = await self.send("POST", "/content-drafts", {"title": "合成草稿", "channel_id": "xiaohongshu", "body": "本地未发布", "source_code": "SYN-CONTENT", "product_id": product["id"]})
        self.assertFalse(content.json()["published"])
        catalog = (await self.send("GET", "/catalog")).json()
        self.assertEqual(len(catalog["products"]), 1)
        self.assertEqual(catalog["sessions"][0]["remaining_capacity"], 2)
        for forbidden in ["leads", "orders", "payments", "refunds"]:
            self.assertNotIn(forbidden, catalog)
        self.assertFalse(catalog["booking_enabled"])
        self.assertEqual((await self.snapshot())["orders"], [])
        old_kind = {key: product[key] for key in ["title", "kind", "price_cents", "status", "description", "delivery_confirmed", "facilitator", "duration_minutes"]}
        self.assertEqual((await self.send("PUT", f"/products/{product['id']}", {**old_kind, "kind": "bundle"})).status_code, 409)
        export = await self.send("GET", "/export")
        self.assertEqual(len(export.json()["leads"]), 1)
        self.assertNotIn(str(self.path), export.text)
        reopened = FastAPI()
        reopened.include_router(create_operations_router(str(self.path)))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reopened), base_url="http://testserver") as client:
            state = (await client.get(PREFIX)).json()
        self.assertEqual(len(state["leads"]), 1)
        self.assertEqual(len(state["products"]), 2)
        self.assertEqual(state["sessions"][0]["product_snapshot"]["kind"], "experience")


if __name__ == "__main__":
    unittest.main(verbosity=2)
