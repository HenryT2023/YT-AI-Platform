"""Local manual accommodation/experience records. No channel or payment I/O.

The business SQLite is independent of the canonical culture repository. Every
inventory or money mutation is serialized with BEGIN IMMEDIATE. Amounts are
integer CNY cents; a reference price never becomes a quotation or revenue.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .bridge import assert_request_scope

SETTINGS = {"property_name": "严田庄园", "room_capacity": 30, "reference_price_cents": 38000,
            "season": "淡季", "provenance": "用户陈述，尚待房表/账单核对",
            "reference_price_note": "参考价不是报价，不用于自动计算订单或收入"}
CHANNELS = [
    {"id": "direct", "name": "直接咨询", "status": "not_connected", "note": "仅本地人工登记，未接预订或支付接口"},
    {"id": "xiaohongshu", "name": "小红书", "status": "not_opened", "note": "用户陈述尚未开通；不自动发布"},
    {"id": "douyin", "name": "抖音", "status": "not_opened", "note": "用户陈述尚未开通；不自动发布"},
    {"id": "other", "name": "其他来源", "status": "not_connected", "note": "仅手工标注来源，不代表平台已接通"},
]
TABLES = ("rooms", "blocks", "products", "sessions", "leads", "content_drafts", "orders", "payments", "refunds")
ACTIVE = {"hold", "confirmed"}
INVENTORY_STATES = {"hold", "confirmed", "fulfilled"}
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")
CHANNEL = Literal["direct", "xiaohongshu", "douyin", "other"]
ID = str


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value=None):
    return (value or utcnow()).isoformat()


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fail(message, status=422):
    raise HTTPException(status, message)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def strings_and_dates(cls, value, info):
        if isinstance(value, str):
            if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
                raise ValueError("不允许控制字符")
            value = value.strip()
            if info.field_name in {"start_date", "end_date"} and value:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("日期格式须为YYYY-MM-DD")
                date.fromisoformat(value)
            if info.field_name == "starts_at":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})", value):
                    raise ValueError("场次时间须带ISO8601时区")
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError("时间缺少时区")
        return value


class RoomInput(StrictInput):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    room_type: str = Field(min_length=1, max_length=80)


class RoomPatch(StrictInput):
    enabled: bool


class BlockInput(StrictInput):
    room_id: ID = Field(min_length=1, max_length=120)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_date <= self.start_date:
            raise ValueError("结束日必须晚于开始日，结束日不占用")
        return self


class ProductInput(StrictInput):
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["stay", "experience", "bundle"]
    price_cents: int | None = Field(default=None, ge=0, le=100000000)
    status: Literal["draft", "active"] = "draft"
    description: str = Field(default="", max_length=6000)
    delivery_confirmed: bool = False
    facilitator: str = Field(default="", max_length=120)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)

    @model_validator(mode="after")
    def active_experience_requires_delivery(self):
        if self.status == "active" and self.kind in {"experience", "bundle"}:
            if not self.delivery_confirmed or not self.facilitator or self.duration_minutes is None:
                raise ValueError("体验/套餐启用须人工确认交付、负责人和时长；木刻软件不是交付证明")
        return self


class SessionInput(StrictInput):
    product_id: ID = Field(min_length=1, max_length=120)
    starts_at: str = Field(min_length=16, max_length=40)
    capacity: int = Field(ge=1, le=1000)
    delivery_confirmed: bool = False


class LeadInput(StrictInput):
    label: str = Field(min_length=1, max_length=120)
    channel_id: CHANNEL
    source_code: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=4000)
    start_date: str | None = Field(default=None, min_length=10, max_length=10)
    end_date: str | None = Field(default=None, min_length=10, max_length=10)
    people: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("结束日须晚于开始日")
        return self


class InquiryInput(LeadInput):
    channel_id: Literal["direct"] = "direct"


class LeadPatch(StrictInput):
    status: Literal["new", "contacted", "quoted", "booked", "lost"]
    notes: str | None = Field(default=None, max_length=4000)


class ContentInput(StrictInput):
    title: str = Field(min_length=1, max_length=160)
    channel_id: CHANNEL
    body: str = Field(min_length=1, max_length=12000)
    source_code: str = Field(min_length=1, max_length=120)
    product_id: ID | None = Field(default=None, min_length=1, max_length=120)


class OrderInput(StrictInput):
    label: str = Field(min_length=1, max_length=120)
    product_id: ID = Field(min_length=1, max_length=120)
    room_ids: list[str] = Field(default_factory=list, max_length=30)
    start_date: str | None = Field(default=None, min_length=10, max_length=10)
    end_date: str | None = Field(default=None, min_length=10, max_length=10)
    session_id: ID | None = Field(default=None, min_length=1, max_length=120)
    seats: int = Field(default=0, ge=0, le=1000)
    amount_cents: int = Field(ge=0, le=100000000)
    channel_id: CHANNEL
    source_code: str = Field(min_length=1, max_length=120)
    lead_id: ID | None = Field(default=None, min_length=1, max_length=120)
    hold_minutes: int = Field(default=30, ge=1, le=1440)
    idempotency_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("room_ids")
    @classmethod
    def room_ids_valid(cls, values):
        if len(set(values)) != len(values) or any(not value or len(value) > 120 for value in values):
            raise ValueError("房间编号重复或不合法")
        return values


class MoneyInput(StrictInput):
    amount_cents: int = Field(ge=1, le=100000000)
    receipt_ref: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")


async def validated_body(request, model=None):
    try:
        raw = await request.json()
    except ValueError:
        # Action endpoints have no required business input, but still validate
        # any body supplied by the caller for fixed scope.
        if model is None and not await request.body():
            raw = {}
        else:
            fail("请求须为合法JSON对象")
    if not isinstance(raw, dict):
        fail("请求须为JSON对象")
    assert_request_scope(request, raw)
    clean = {key: value for key, value in raw.items() if key not in {"tenant", "tenant_id", "site", "site_id"}}
    if model is None:
        if clean:
            fail("此操作不接受额外参数")
        return None
    try:
        return model.model_validate(clean)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, item["loc"])) or "字段组合" for item in exc.errors()[:5])
        fail("输入校验失败，请核对长度、整数金额、日期/时区和交付确认：" + fields)


def create_operations_router(db_path: str) -> APIRouter:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        for table in TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS op_{table} (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS op_idempotency (namespace TEXT NOT NULL, key TEXT NOT NULL, payload_hash TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(namespace,key))")
        conn.execute("CREATE TABLE IF NOT EXISTS op_settings (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO op_settings VALUES ('settings',?)", (pack(SETTINGS),))
        conn.execute("INSERT OR IGNORE INTO op_settings VALUES ('channels',?)", (pack(CHANNELS),))
        conn.commit()
    finally:
        conn.close()

    def rows(conn, table):
        assert table in TABLES
        return [json.loads(row[0]) for row in conn.execute(f"SELECT data FROM op_{table} ORDER BY rowid")]

    def get(conn, table, record_id):
        assert table in TABLES
        row = conn.execute(f"SELECT data FROM op_{table} WHERE id=?", (record_id,)).fetchone()
        if not row:
            fail("指定" + table + "记录不存在")
        return json.loads(row[0])

    def insert(conn, table, value):
        assert table in TABLES
        conn.execute(f"INSERT INTO op_{table}(id,data) VALUES (?,?)", (value["id"], pack(value)))
        return value

    def save(conn, table, value):
        assert table in TABLES
        conn.execute(f"UPDATE op_{table} SET data=? WHERE id=?", (pack(value), value["id"]))
        return value

    def money_totals(conn, order_id):
        received = sum(item["amount_cents"] for item in rows(conn, "payments") if item["order_id"] == order_id)
        refunded = sum(item["amount_cents"] for item in rows(conn, "refunds") if item["order_id"] == order_id)
        return received, refunded

    def order_dto(conn, order):
        received, refunded = money_totals(conn, order["id"])
        if refunded:
            payment_state = "refunded" if refunded == received else "partially_refunded"
        else:
            payment_state = "paid" if received-refunded >= order["amount_cents"] and (received > 0 or order["amount_cents"] == 0) else "partial" if received-refunded > 0 else "unpaid"
        return {**order, "payment_status": payment_state, "received_cents": received, "refunded_cents": refunded,
                "net_received_cents": received-refunded, "manual_receipt_recorded": received > 0,
                "money_note": "仅人工收款/退款登记；未接支付接口，未独立核验银行或渠道到账"}

    def expire(conn):
        current_time = utcnow()
        for order in rows(conn, "orders"):
            if order["status"] == "hold" and datetime.fromisoformat(order["expires_at"]) <= current_time:
                received, refunded = money_totals(conn, order["id"])
                if received-refunded == 0:
                    order.update(status="expired", updated_at=timestamp(current_time))
                    save(conn, "orders", order)

    @contextmanager
    def transaction():
        conn = sqlite3.connect(path, timeout=15)
        try:
            conn.execute("BEGIN IMMEDIATE")
            expire(conn)
            yield conn
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            conn.rollback()
            fail("记录冲突或正在处理，请刷新后重试", 409)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def overlap(start, end, other_start, other_end):
        return start < other_end and other_start < end

    def room_conflicts(conn, room, start, end):
        conflicts = []
        if not room["enabled"]:
            conflicts.append({"kind": "disabled", "id": room["id"], "reason": "房间已停用", "start_date": None, "end_date": None})
        for block in rows(conn, "blocks"):
            if block["status"] == "active" and block["room_id"] == room["id"] and overlap(start, end, block["start_date"], block["end_date"]):
                conflicts.append({"kind": "block", "id": block["id"], "reason": block["reason"], "start_date": block["start_date"], "end_date": block["end_date"]})
        for order in rows(conn, "orders"):
            if order["status"] in INVENTORY_STATES and room["id"] in order["room_ids"] and overlap(start, end, order["start_date"], order["end_date"]):
                conflicts.append({"kind": "order", "id": order["id"], "reason": "订单占用（" + order["status"] + "）", "start_date": order["start_date"], "end_date": order["end_date"]})
        return conflicts

    def session_dto(conn, session):
        booked = sum(order["seats"] for order in rows(conn, "orders") if order["status"] in INVENTORY_STATES and order["session_id"] == session["id"])
        product = get(conn, "products", session["product_id"])
        remaining = session["capacity"]-booked
        return {**session, "booked_seats": booked, "remaining_capacity": remaining,
                "available": bool(session["delivery_confirmed"] and product["status"] == "active" and product["delivery_confirmed"] and remaining > 0 and datetime.fromisoformat(session["starts_at"].replace("Z", "+00:00")) > utcnow())}

    def replay(conn, namespace, key, payload):
        payload_hash = hashlib.sha256(pack(payload).encode()).hexdigest()
        old = conn.execute("SELECT payload_hash,record_id FROM op_idempotency WHERE namespace=? AND key=?", (namespace, key)).fetchone()
        if old and old[0] != payload_hash:
            fail("幂等键已用于不同内容，请勿重复提交不同交易", 409)
        return (old[1] if old else None), payload_hash

    def remember(conn, namespace, key, payload_hash, record_id):
        conn.execute("INSERT INTO op_idempotency VALUES (?,?,?,?)", (namespace, key, payload_hash, record_id))

    def settings(conn, name):
        return json.loads(conn.execute("SELECT data FROM op_settings WHERE id=?", (name,)).fetchone()[0])

    def snapshot(conn):
        data = {table: rows(conn, table) for table in TABLES}
        data["orders"] = [order_dto(conn, order) for order in data["orders"]]
        data["sessions"] = [session_dto(conn, session) for session in data["sessions"]]
        data["settings"], data["channels"] = settings(conn, "settings"), settings(conn, "channels")
        orders = data["orders"]
        has_orders = bool(orders)
        received = sum(item["amount_cents"] for item in data["payments"]) if has_orders else None
        refunded = sum(item["amount_cents"] for item in data["refunds"]) if has_orders else None
        data["summary"] = {
            "rooms_registered": len(data["rooms"]), "rooms_enabled": sum(room["enabled"] for room in data["rooms"]),
            "unregistered_rooms": 30-len(data["rooms"]), "orders_count": len(orders),
            "active_orders": sum(order["status"] in ACTIVE for order in orders),
            **{key+"_orders": sum(order["status"] == state for order in orders) for key, state in [("hold", "hold"), ("confirmed", "confirmed"), ("fulfilled", "fulfilled"), ("cancelled", "cancelled"), ("expired", "expired")]},
            "payments_count": len(data["payments"]), "refunds_count": len(data["refunds"]),
            "quoted_total_cents": sum(order["amount_cents"] for order in orders) if has_orders else None,
            "received_cents": received, "refunded_cents": refunded, "net_received_cents": received-refunded if has_orders else None,
            "manual_recorded_payments_cents": received, "manual_recorded_refunds_cents": refunded,
            "manual_recorded_net_cash_cents": received-refunded if has_orders else None,
            "cash_record_state": "MANUALLY_RECORDED" if data["payments"] else "NO_RECEIPTS_RECORDED" if has_orders else "MISSING",
            "revenue_cents": None, "revenue_state": "NOT_RECOGNIZED",
            "note": "仅汇总本地人工登记流水；报价、380元参考价及收款登记均不等于已确认营业收入，未独立核验渠道/银行到账。"}
        return data

    router = APIRouter(prefix="/api/local-os/operations", tags=["本地住宿与体验运营"])

    @router.get("")
    async def get_snapshot(request: Request):
        assert_request_scope(request)
        with transaction() as conn:
            return snapshot(conn)

    @router.post("/rooms")
    async def create_room(request: Request):
        data = await validated_body(request, RoomInput)
        with transaction() as conn:
            existing = rows(conn, "rooms")
            if len(existing) >= 30:
                fail("已达到用户陈述的30间容量；请先核实房表，不能自动扩容", 409)
            if any(room["code"].casefold() == data.code.casefold() for room in existing):
                fail("房间代码已存在", 409)
            return insert(conn, "rooms", {**data.model_dump(), "id": new_id("room"), "enabled": True, "created_at": timestamp()})

    @router.patch("/rooms/{room_id}")
    async def change_room(room_id: str, request: Request):
        data = await validated_body(request, RoomPatch)
        with transaction() as conn:
            room = get(conn, "rooms", room_id)
            if not data.enabled and any(order["status"] in ACTIVE and room_id in order["room_ids"] for order in rows(conn, "orders")):
                fail("房间仍有未终结订单，不能停用", 409)
            room["enabled"] = data.enabled
            return save(conn, "rooms", room)

    @router.post("/blocks")
    async def create_block(request: Request):
        data = await validated_body(request, BlockInput)
        with transaction() as conn:
            get(conn, "rooms", data.room_id)
            if any(order["status"] in INVENTORY_STATES and data.room_id in order["room_ids"] and overlap(data.start_date, data.end_date, order["start_date"], order["end_date"]) for order in rows(conn, "orders")):
                fail("停房日期与现有订单冲突", 409)
            return insert(conn, "blocks", {**data.model_dump(), "id": new_id("block"), "status": "active", "created_at": timestamp(), "released_at": None})

    @router.post("/blocks/{block_id}/release")
    async def release_block(block_id: str, request: Request):
        await validated_body(request)
        with transaction() as conn:
            block = get(conn, "blocks", block_id)
            if block["status"] != "released":
                block.update(status="released", released_at=timestamp())
                save(conn, "blocks", block)
            return block

    @router.post("/products")
    async def create_product(request: Request):
        data = await validated_body(request, ProductInput)
        with transaction() as conn:
            return insert(conn, "products", {**data.model_dump(), "id": new_id("product"), "created_at": timestamp(), "updated_at": timestamp()})

    @router.put("/products/{product_id}")
    async def update_product(product_id: str, request: Request):
        data = await validated_body(request, ProductInput)
        with transaction() as conn:
            old = get(conn, "products", product_id)
            if old["kind"] != data.kind and (any(session["product_id"] == product_id for session in rows(conn, "sessions")) or any(order["product_id"] == product_id for order in rows(conn, "orders"))):
                fail("该产品已有场次或历史订单，不能修改kind；请新建产品保留原语义", 409)
            return save(conn, "products", {**data.model_dump(), "id": product_id, "created_at": old["created_at"], "updated_at": timestamp()})

    @router.post("/sessions")
    async def create_session(request: Request):
        data = await validated_body(request, SessionInput)
        with transaction() as conn:
            product = get(conn, "products", data.product_id)
            if product["kind"] not in {"experience", "bundle"} or product["status"] != "active":
                fail("只有含体验的active产品可创建场次")
            session = insert(conn, "sessions", {**data.model_dump(), "id": new_id("session"), "created_at": timestamp(), "product_snapshot": product})
            return session_dto(conn, session)

    def insert_lead(conn, data):
        return insert(conn, "leads", {**data.model_dump(), "id": new_id("lead"), "status": "new", "created_at": timestamp(), "updated_at": timestamp()})

    @router.post("/leads")
    async def create_lead(request: Request):
        data = await validated_body(request, LeadInput)
        with transaction() as conn:
            return insert_lead(conn, data)

    @router.post("/inquiries")
    async def create_inquiry(request: Request):
        data = await validated_body(request, InquiryInput)
        with transaction() as conn:
            return insert_lead(conn, data)

    @router.patch("/leads/{lead_id}")
    async def change_lead(lead_id: str, request: Request):
        data = await validated_body(request, LeadPatch)
        with transaction() as conn:
            lead = get(conn, "leads", lead_id)
            lead.update(status=data.status, updated_at=timestamp())
            if data.notes is not None:
                lead["notes"] = data.notes
            return save(conn, "leads", lead)

    @router.post("/content-drafts")
    async def create_content(request: Request):
        data = await validated_body(request, ContentInput)
        with transaction() as conn:
            if data.product_id:
                get(conn, "products", data.product_id)
            return insert(conn, "content_drafts", {**data.model_dump(), "id": new_id("content"), "status": "internal_draft", "published": False, "created_at": timestamp()})

    @router.post("/orders")
    async def create_order(request: Request):
        data = await validated_body(request, OrderInput)
        payload = data.model_dump()
        with transaction() as conn:
            old_id, payload_hash = replay(conn, "orders", data.idempotency_key, payload)
            if old_id:
                return order_dto(conn, get(conn, "orders", old_id))
            product = get(conn, "products", data.product_id)
            if product["status"] != "active":
                fail("产品未启用，不能创建订单", 409)
            kind = product["kind"]
            if data.lead_id:
                get(conn, "leads", data.lead_id)
            if kind in {"stay", "bundle"}:
                if not data.room_ids or not data.start_date or not data.end_date or data.end_date <= data.start_date:
                    fail("住宿/套餐订单须选择已建档房间，且入住日早于退房日（至少一晚）")
                for room_id in data.room_ids:
                    room = get(conn, "rooms", room_id)
                    if room_conflicts(conn, room, data.start_date, data.end_date):
                        fail("房间不可售：停用、停房或其他订单占用", 409)
            elif data.room_ids or data.start_date or data.end_date:
                fail("纯体验订单不接受住宿房间/日期")
            if kind in {"experience", "bundle"}:
                if not product["delivery_confirmed"] or not data.session_id or data.seats < 1:
                    fail("体验/套餐须明确已确认交付的场次和人数")
                session = get(conn, "sessions", data.session_id)
                if session["product_id"] != product["id"] or not session["delivery_confirmed"]:
                    fail("场次必须属于本产品且经人工确认交付", 409)
                starts_at = datetime.fromisoformat(session["starts_at"].replace("Z", "+00:00"))
                if starts_at <= utcnow():
                    fail("已开始或已过去的场次不能新增预订", 409)
                if kind == "bundle":
                    session_day = starts_at.astimezone(BUSINESS_TIMEZONE).date().isoformat()
                    if not data.start_date <= session_day <= data.end_date:
                        fail("套餐场次须落在住宿行程内（按上海日历，允许退房日体验）", 409)
                if session_dto(conn, session)["remaining_capacity"] < data.seats:
                    fail("场次余量不足", 409)
            elif data.session_id or data.seats:
                fail("纯住宿订单不接受体验场次/人数占位")
            current = utcnow()
            order = {**payload, "id": new_id("order"), "kind": kind, "product_snapshot": product,
                     "status": "hold", "expires_at": timestamp(current+timedelta(minutes=data.hold_minutes)),
                     "created_at": timestamp(current), "updated_at": timestamp(current), "confirmed_at": None,
                     "fulfilled_at": None, "cancelled_at": None, "currency": "CNY",
                     "quotation_note": "人工报价快照，不由参考价自动计算，不代表已收款或已确认收入"}
            insert(conn, "orders", order)
            remember(conn, "orders", data.idempotency_key, payload_hash, order["id"])
            return order_dto(conn, order)

    @router.post("/orders/{order_id}/payments")
    async def add_payment(order_id: str, request: Request):
        data = await validated_body(request, MoneyInput)
        with transaction() as conn:
            payload = {**data.model_dump(), "order_id": order_id}
            old_id, payload_hash = replay(conn, "payments", data.idempotency_key, payload)
            order = get(conn, "orders", order_id)
            if old_id:
                return {"payment": get(conn, "payments", old_id), "order": order_dto(conn, order)}
            if order["status"] not in ACTIVE:
                fail("订单已终结或过期，不能新增收款登记", 409)
            received, refunded = money_totals(conn, order_id)
            if received+data.amount_cents > order["amount_cents"]:
                fail("累计收款登记不能超过人工报价", 409)
            payment = insert(conn, "payments", {**payload, "id": new_id("payment"), "created_at": timestamp(),
                       "record_kind": "manual_receipt_registration", "independently_verified": False})
            remember(conn, "payments", data.idempotency_key, payload_hash, payment["id"])
            order["updated_at"] = timestamp()
            if order["status"] == "hold" and received-refunded+data.amount_cents >= order["amount_cents"]:
                order.update(status="confirmed", confirmed_at=timestamp())
            save(conn, "orders", order)
            return {"payment": payment, "order": order_dto(conn, order)}

    @router.post("/orders/{order_id}/confirm")
    async def confirm_order(order_id: str, request: Request):
        await validated_body(request)
        with transaction() as conn:
            order = get(conn, "orders", order_id)
            if order["status"] == "confirmed":
                return order_dto(conn, order)
            received, refunded = money_totals(conn, order_id)
            if order["status"] != "hold" or received-refunded < order["amount_cents"]:
                fail("只有未过期且全额收款登记的hold订单可确认", 409)
            order.update(status="confirmed", confirmed_at=timestamp(), updated_at=timestamp())
            return order_dto(conn, save(conn, "orders", order))

    @router.post("/orders/{order_id}/fulfill")
    async def fulfill_order(order_id: str, request: Request):
        await validated_body(request)
        with transaction() as conn:
            order = get(conn, "orders", order_id)
            if order["status"] == "fulfilled":
                return order_dto(conn, order)
            if order["status"] != "confirmed":
                fail("只有confirmed订单可人工登记已履约", 409)
            current_time = utcnow()
            if order["kind"] in {"stay", "bundle"} and current_time.astimezone(BUSINESS_TIMEZONE).date().isoformat() < order["end_date"]:
                fail("尚未到住宿退房日，不能提前登记已履约", 409)
            if order["kind"] in {"experience", "bundle"}:
                session = get(conn, "sessions", order["session_id"])
                starts_at = datetime.fromisoformat(session["starts_at"].replace("Z", "+00:00"))
                ends_at = starts_at+timedelta(minutes=order["product_snapshot"]["duration_minutes"])
                if current_time < ends_at:
                    fail("体验尚未结束，不能提前登记已履约", 409)
            order.update(status="fulfilled", fulfilled_at=timestamp(), updated_at=timestamp())
            return order_dto(conn, save(conn, "orders", order))

    @router.post("/orders/{order_id}/cancel")
    async def cancel_order(order_id: str, request: Request):
        await validated_body(request)
        with transaction() as conn:
            order = get(conn, "orders", order_id)
            if order["status"] == "cancelled":
                return order_dto(conn, order)
            if order["status"] not in ACTIVE:
                fail("仅hold/confirmed订单可取消；过期或已履约记录保留原状态", 409)
            order.update(status="cancelled", cancelled_at=timestamp(), updated_at=timestamp())
            return order_dto(conn, save(conn, "orders", order))

    @router.post("/orders/{order_id}/refunds")
    async def add_refund(order_id: str, request: Request):
        data = await validated_body(request, MoneyInput)
        with transaction() as conn:
            payload = {**data.model_dump(), "order_id": order_id}
            old_id, payload_hash = replay(conn, "refunds", data.idempotency_key, payload)
            order = get(conn, "orders", order_id)
            if old_id:
                return {"refund": get(conn, "refunds", old_id), "order": order_dto(conn, order)}
            received, refunded = money_totals(conn, order_id)
            if refunded+data.amount_cents > received:
                fail("累计退款登记不能超过已登记实收余额", 409)
            refund = insert(conn, "refunds", {**payload, "id": new_id("refund"), "created_at": timestamp(),
                      "record_kind": "manual_refund_registration", "independently_verified": False})
            remember(conn, "refunds", data.idempotency_key, payload_hash, refund["id"])
            order.update(updated_at=timestamp())
            if order["status"] == "hold" and received-refunded-data.amount_cents == 0 and datetime.fromisoformat(order["expires_at"]) <= utcnow():
                order["status"] = "expired"
            save(conn, "orders", order)
            return {"refund": refund, "order": order_dto(conn, order)}

    @router.get("/availability")
    async def availability(request: Request, start_date: str, end_date: str):
        assert_request_scope(request)
        try:
            check = BlockInput(room_id="query", start_date=start_date, end_date=end_date, reason="query")
        except ValidationError:
            fail("查询须提供有效日期，且开始日早于结束日")
        with transaction() as conn:
            rooms = rows(conn, "rooms")
            results = []
            for room in rooms:
                conflicts = room_conflicts(conn, room, check.start_date, check.end_date)
                results.append({**room, "available": not conflicts, "conflicts": conflicts})
            return {"start_date": start_date, "end_date": end_date, "rooms": results,
                    "available_rooms": sum(item["available"] for item in results), "registered_rooms": len(rooms),
                    "unregistered_rooms": 30-len(rooms), "declared_room_capacity": 30}

    @router.get("/catalog")
    async def catalog(request: Request):
        assert_request_scope(request)
        with transaction() as conn:
            products = [product for product in rows(conn, "products") if product["status"] == "active"]
            ids = {product["id"] for product in products}
            sessions = [session_dto(conn, session) for session in rows(conn, "sessions") if session["product_id"] in ids and session["delivery_confirmed"] and datetime.fromisoformat(session["starts_at"].replace("Z", "+00:00")) > utcnow()]
            return {"settings": settings(conn, "settings"),
                    "products": [{key: product[key] for key in ["id", "title", "kind", "price_cents", "description", "duration_minutes", "delivery_confirmed"]} for product in products],
                    "sessions": [{key: session[key] for key in ["id", "product_id", "starts_at", "capacity", "booked_seats", "remaining_capacity", "available", "delivery_confirmed"]} for session in sessions],
                    "mode": "local_inquiry_preview", "booking_enabled": False, "payment_enabled": False,
                    "note": "仅本地咨询意向，不锁房、不收款、不承诺未确认体验；参考价不是正式报价。"}

    @router.get("/export")
    async def export(request: Request):
        assert_request_scope(request)
        with transaction() as conn:
            data = {"mode": "local_manual_operations", "exported_at": timestamp(), **snapshot(conn)}
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="yantian-local-operations.json"', "X-Content-Type-Options": "nosniff"})

    return router
