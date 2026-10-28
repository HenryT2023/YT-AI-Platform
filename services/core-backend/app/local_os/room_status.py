"""Sanitized workbook observations, independent of operational availability.

Only rs_* tables are written. An explicit source zero is an invitation to verify
inventory, never an available room, booking, payment or revenue assertion.
"""
from __future__ import annotations

import calendar
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .bridge import assert_request_scope

PREFIX = "/api/local-os/room-status"
CONTRACT = "yantian.room-status-observations.v1"
ROOM_TYPES = ("双床", "大床")
RESOLUTIONS = Literal["USER_CONFIRMED_RELATIVE_PERIOD", "SOURCE_EXPLICIT_YEAR", "UNRESOLVED"]
STATUSES = Literal["UNKNOWN_BLANK", "SOURCE_RECORDED_ZERO", "SOURCE_RESERVATION_UNCONFIRMED", "SOURCE_RESERVATION_STATUS_UNRESOLVED"]
CELL = r"^[A-Z]{1,3}[1-9][0-9]{0,6}$"
HASH = r"^[a-f0-9]{64}$"
MISSING = {
    "two-room capacity discrepancy", "room-number map", "19 blank twin-room days",
    "pink reservation business status", "source business as-of time",
    "nightly allocation and checkout convention", "maintenance/self-use and other-channel reservations",
    "order grouping and dates", "actual quote and payment evidence",
}


def _pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_pack(value).encode()).hexdigest()


def _fail(message="房态导入字段、日期、数量或状态不合法；未写入", status=422):
    raise HTTPException(status, message)


def _day(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid date")
    return date.fromisoformat(value)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def no_control_characters(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            raise ValueError("control character")
        return value


class Source(Strict):
    filename: Literal["严田庄园客房11-12月预定房态.xlsx"]
    sha256: str = Field(pattern=HASH)
    sheet: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z][A-Za-z0-9_ -]*$")
    range: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}:[A-Z]{1,3}[1-9][0-9]{0,6}$")
    provenance: Literal["user-supplied colleague workbook"]
    business_as_of: None
    extracted_on: str
    no_personal_or_organization_identifiers_exported: Literal[True]

    @field_validator("extracted_on")
    @classmethod
    def valid_date(cls, value):
        _day(value)
        return value


class PeriodResolution(Strict):
    source_year: int | None = Field(ge=1900, le=2100)
    resolved_year: int | None = Field(ge=1900, le=2100)
    state: RESOLUTIONS
    basis: str = Field(min_length=1, max_length=140)

    @field_validator("basis")
    @classmethod
    def safe_basis(cls, value):
        # This endpoint consumes a bounded sanitized contract, not arbitrary notes.
        if not re.fullmatch(r"(?:\d{4}-\d{2}-\d{2} user clarified upcoming November and December|operator confirmed year \d{4}|source explicitly specifies year|year unresolved)", value):
            raise ValueError("unrecognized sanitized period basis")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if self.state == "UNRESOLVED":
            if self.resolved_year is not None or self.source_year is not None:
                raise ValueError("unresolved year must remain null")
        elif self.resolved_year is None:
            raise ValueError("resolved year required")
        elif self.state == "SOURCE_EXPLICIT_YEAR" and self.source_year != self.resolved_year:
            raise ValueError("source year mismatch")
        elif self.state == "USER_CONFIRMED_RELATIVE_PERIOD" and self.source_year is not None:
            raise ValueError("relative period must retain unknown source year")
        return self


class Capacity(Strict):
    source_reported_total: int = Field(ge=1, le=1000)
    source_reported_twin: int = Field(ge=1, le=1000)
    source_reported_king: int = Field(ge=1, le=1000)
    owner_previously_reported_total: Literal[30]
    unreconciled_difference: int = Field(ge=-1000, le=1000)
    source_ranges: list[str] = Field(min_length=1, max_length=8)
    current_sellable_total: None

    @field_validator("source_ranges")
    @classmethod
    def ranges(cls, value):
        if any(not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}:[A-Z]{1,3}[1-9][0-9]{0,6}", item) for item in value):
            raise ValueError("invalid cell range")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if self.source_reported_total != self.source_reported_twin + self.source_reported_king:
            raise ValueError("capacity sum mismatch")
        if self.unreconciled_difference != self.owner_previously_reported_total - self.source_reported_total:
            raise ValueError("capacity difference mismatch")
        return self


class Coverage(Strict):
    year: int | None = Field(ge=1900, le=2100)
    month: Literal[11, 12]
    from_day: int = Field(ge=1, le=31)
    through_day: int = Field(ge=1, le=31)
    days: int = Field(ge=1, le=31)

    @model_validator(mode="after")
    def consistent(self):
        if self.through_day > calendar.monthrange(self.year or 2000, self.month)[1] or self.from_day > self.through_day or self.days != self.through_day-self.from_day+1:
            raise ValueError("invalid coverage range")
        return self


class Summary(Strict):
    room_type_day_cells: int = Field(ge=0)
    blank_unknown_cells: int = Field(ge=0)
    explicit_zero_cells: int = Field(ge=0)
    positive_cells: int = Field(ge=0)
    source_daily_quantity_sum: int = Field(ge=0)
    by_month_daily_quantity_sum: dict[str, int]
    pink_daily_quantity_sum: int = Field(ge=0)
    yellow_unconfirmed_daily_quantity_sum: int = Field(ge=0)
    confirmed_room_nights: None
    occupancy_rate: None
    revenue_cents: None


class Interpretation(Strict):
    pink_legend: Literal["source prebooking annotation, business status unresolved; identifying text omitted"]
    yellow_legend: Literal["预定（未确认）, identifying text omitted"]
    zero: Literal["source explicitly records zero; not evidence of cleared sellable inventory"]
    blank: Literal["unknown, never automatically zero or available"]
    daily_sum: Literal["sum of reported room quantities across date columns; nightly allocation basis unconfirmed"]


class Actions(Strict):
    source_workbook_edited: Literal[False]
    operations_db_written: Literal[False]
    rooms_created: Literal[0]
    orders_created: Literal[0]
    payments_created: Literal[0]
    published: Literal[False]


class Observation(Strict):
    observation_key: str = Field(min_length=1, max_length=180)
    source_sha256: str = Field(pattern=HASH)
    source_sheet: str = Field(min_length=1, max_length=60)
    source_cell: str = Field(pattern=CELL)
    source_day_cell: str = Field(pattern=CELL)
    source_capacity_cell: str = Field(pattern=CELL)
    source_legend_cell: str | None = Field(pattern=CELL)
    source_year: int | None = Field(ge=1900, le=2100)
    year: int | None = Field(ge=1900, le=2100)
    month: Literal[11, 12]
    day: int = Field(ge=1, le=31)
    date: str | None
    room_type: Literal["双床", "大床"]
    reported_type_capacity: int = Field(ge=1, le=1000)
    source_reported_reservation_quantity: int | None = Field(ge=0, le=1000)
    observed_status: STATUSES
    date_resolution: RESOLUTIONS
    source_color: Literal["pink", "yellow"] | None
    authoritative_available_quantity: None
    room_ids: None
    order_id: None
    amount_cents: None
    payment_status: None
    night_basis: Literal["UNCONFIRMED"]

    @model_validator(mode="after")
    def consistent(self):
        quantity = self.source_reported_reservation_quantity
        if quantity is not None and quantity > self.reported_type_capacity:
            raise ValueError("quantity exceeds room type capacity")
        if self.day > calendar.monthrange(self.year or 2000, self.month)[1]:
            raise ValueError("day invalid")
        if self.date != (date(self.year, self.month, self.day).isoformat() if self.year is not None else None):
            raise ValueError("date components mismatch")
        expected = {"UNKNOWN_BLANK": (None, None), "SOURCE_RECORDED_ZERO": (0, None)}
        if self.observed_status in expected:
            if (quantity, self.source_color) != expected[self.observed_status]:
                raise ValueError("blank or zero state mismatch")
        elif quantity is None or quantity <= 0 or self.source_color != ("yellow" if self.observed_status == "SOURCE_RESERVATION_UNCONFIRMED" else "pink"):
            raise ValueError("reservation state mismatch")
        return self


def _summary(observations):
    def quantity(row):
        return row["source_reported_reservation_quantity"] or 0
    return {
        "room_type_day_cells": len(observations),
        "blank_unknown_cells": sum(row["observed_status"] == "UNKNOWN_BLANK" for row in observations),
        "explicit_zero_cells": sum(row["observed_status"] == "SOURCE_RECORDED_ZERO" for row in observations),
        "positive_cells": sum((row["source_reported_reservation_quantity"] or 0) > 0 for row in observations),
        "source_daily_quantity_sum": sum(quantity(row) for row in observations),
        "by_month_daily_quantity_sum": {str(month): sum(quantity(row) for row in observations if row["month"] == month) for month in sorted({row["month"] for row in observations})},
        "pink_daily_quantity_sum": sum(quantity(row) for row in observations if row["source_color"] == "pink"),
        "yellow_unconfirmed_daily_quantity_sum": sum(quantity(row) for row in observations if row["source_color"] == "yellow"),
        "confirmed_room_nights": None, "occupancy_rate": None, "revenue_cents": None,
    }


def _coordinates(cell):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", cell)
    if not match:
        raise ValueError("invalid cell")
    column = 0
    for char in match[1]:
        column = column*26 + ord(char)-64
    if column > 16384 or int(match[2]) > 1048576:
        raise ValueError("cell outside worksheet")
    return column, int(match[2])


class ImportPayload(Strict):
    contract: Literal["yantian.room-status-observations.v1"]
    state: Literal["STAGED_REQUIRES_RECONCILIATION"]
    source: Source
    period_resolution: PeriodResolution
    room_capacity: Capacity
    coverage: list[Coverage] = Field(min_length=2, max_length=2)
    summary: Summary
    interpretation: Interpretation
    missing: list[str] = Field(max_length=20)
    actions_applied: Actions
    observations: list[Observation] = Field(min_length=1, max_length=124)

    @model_validator(mode="after")
    def consistent(self):
        if any(value not in MISSING for value in self.missing):
            raise ValueError("unrecognized sanitized issue")
        lower, upper = [_coordinates(value) for value in self.source.range.split(":")]
        if any(lower[index] > upper[index] for index in (0, 1)):
            raise ValueError("invalid worksheet range")
        def inside(cell):
            point = _coordinates(cell)
            return all(lower[index] <= point[index] <= upper[index] for index in (0, 1))
        for source_range in self.room_capacity.source_ranges:
            if not all(inside(cell) for cell in source_range.split(":")):
                raise ValueError("capacity locator outside source range")
        periods = {}
        for item in self.coverage:
            if item.month in periods or item.year != self.period_resolution.resolved_year:
                raise ValueError("duplicate or mismatched coverage")
            periods[item.month] = item
        cells, dates = set(), set()
        for row in self.observations:
            if row.source_sha256 != self.source.sha256 or row.source_sheet != self.source.sheet or row.observation_key != f"{self.source.sha256}:{self.source.sheet}:{row.source_cell}":
                raise ValueError("source identity mismatch")
            if row.source_cell in cells:
                raise ValueError("duplicate source cell")
            cells.add(row.source_cell)
            key = (row.month, row.day, row.room_type)
            if key in dates:
                raise ValueError("duplicate room type day")
            dates.add(key)
            if any(not inside(cell) for cell in [row.source_cell, row.source_day_cell, row.source_capacity_cell, *([row.source_legend_cell] if row.source_legend_cell else [])]):
                raise ValueError("locator outside source range")
            coverage = periods.get(row.month)
            if not coverage or not coverage.from_day <= row.day <= coverage.through_day:
                raise ValueError("observation outside coverage")
            if row.year != self.period_resolution.resolved_year or row.source_year != self.period_resolution.source_year or row.date_resolution != self.period_resolution.state:
                raise ValueError("period resolution mismatch")
            capacity = self.room_capacity.source_reported_twin if row.room_type == "双床" else self.room_capacity.source_reported_king
            if row.reported_type_capacity != capacity:
                raise ValueError("room capacity mismatch")
        expected = {(item.month, day, room_type) for item in self.coverage for day in range(item.from_day, item.through_day+1) for room_type in ROOM_TYPES}
        if dates != expected:
            raise ValueError("coverage requires explicit observations, including unknown blanks")
        if self.summary.model_dump() != _summary([item.model_dump() for item in self.observations]):
            raise ValueError("source summary does not match individual observations")
        return self


def _windows(days):
    """Keep monthly source windows separate, including adjacent Nov/Dec dates."""
    windows = []
    for current in sorted(set(days)):
        if windows and current.month == windows[-1][-1].month and current == windows[-1][-1]+timedelta(days=1):
            windows[-1].append(current)
        else:
            windows.append([current])
    return windows


def _derived(payload, parsing_hash):
    observations = payload["observations"]
    issues = []
    def issue(code, message, count=None, cells=None):
        value = {"code": code, "severity": "warning", "message": message}
        if count is not None:
            value["count"] = count
        if cells is not None:
            value["source_cells"] = cells
        issues.append(value)
    def refs(rows):
        return [row["source_sheet"]+"!"+row["source_cell"] for row in rows]
    capacity = payload["room_capacity"]
    if capacity["unreconciled_difference"]:
        issue("CAPACITY_DISCREPANCY", f"来源房量{capacity['source_reported_total']}间，管理者此前陈述30间，相差{capacity['unreconciled_difference']}间；不能自动补造房间。", abs(capacity["unreconciled_difference"]))
    blanks = [row for row in observations if row["observed_status"] == "UNKNOWN_BLANK"]
    if blanks:
        issue("UNKNOWN_BLANKS", f"{len(blanks)}个房型日期格为空白，保持未知，不能当作0或可售。", len(blanks), refs(blanks))
    yellow = [row for row in observations if row["observed_status"] == "SOURCE_RESERVATION_UNCONFIRMED"]
    if yellow:
        issue("YELLOW_UNCONFIRMED", "黄色来源标注为预定未确认，不等于已确认订单、锁房或到账。", len(yellow), refs(yellow))
    pink = [row for row in observations if row["observed_status"] == "SOURCE_RESERVATION_STATUS_UNRESOLVED"]
    if pink:
        issue("PINK_STATUS_UNRESOLVED", "粉色来源预订标注的业务状态未核，不保留或展示团体身份标注。", len(pink), refs(pink))
    for code, message in [
        ("ROOM_NUMBER_MAP_MISSING", "来源为房型汇总，缺逐房房号与实际库存映射；未创建运营房源。"),
        ("MAINTENANCE_AND_OTHER_CHANNELS_UNKNOWN", "维修、业主自用及其他渠道占用未核，显式0不代表清空可售库存。"),
        ("QUOTE_AND_PAYMENT_UNKNOWN", "实际报价、订单分组、付款及凭据未核；不创建订单或收款记录。"),
        ("NIGHT_BASIS_UNKNOWN", "逐日数量与离店日/房晚分配口径未核，数量合计不当作已确认房晚、入住率或收入。"),
        ("BUSINESS_AS_OF_UNKNOWN", "原表业务截至时间未提供；提取时间不等于业务截至时间。"),
    ]:
        issue(code, message)
    year = payload["period_resolution"]["resolved_year"]
    missing, opportunities = [], []
    if year is None:
        issue("YEAR_UNRESOLVED", "年份未确认，仅保留月日观察，不生成日期获客窗口。")
    else:
        for covered in payload["coverage"]:
            month = covered["month"]
            absent = [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1]+1) if not covered["from_day"] <= day <= covered["through_day"]]
            for window in _windows(absent):
                missing.append({"start_date": window[0].isoformat(), "end_date": window[-1].isoformat(), "days": len(window)})
        if missing:
            issue("DATES_NOT_COVERED", "来源未覆盖："+"、".join(item["start_date"]+"至"+item["end_date"] for item in missing)+"；不能补成空房。", sum(item["days"] for item in missing))
        day_rows = {}
        for row in observations:
            day_rows.setdefault(row["date"], {})[row["room_type"]] = row
        zero = lambda row: row["observed_status"] == "SOURCE_RECORDED_ZERO" and row["source_reported_reservation_quantity"] == 0
        for kind, types in [("ALL_TYPES_ZERO", list(ROOM_TYPES)), ("KING_ZERO", ["大床"])]:
            eligible = [_day(day) for day, rows in day_rows.items() if all(room_type in rows and zero(rows[room_type]) for room_type in types)]
            for window in _windows(eligible):
                cells = refs([day_rows[day.isoformat()][room_type] for day in window for room_type in types])
                descriptor = {"start_date": window[0].isoformat(), "end_date": window[-1].isoformat(), "room_types": types, "kind": kind, "days": len(window), "verification_required": True, "source_cells": cells}
                opportunities.append({"id": "rsopp-"+_hash({"parsing_hash": parsing_hash, **descriptor})[:24], **descriptor})
    summary = _summary(observations)
    summary["missing_coverage_days"] = sum(item["days"] for item in missing)
    return {"summary": summary, "issues": issues, "opportunities": opportunities, "missing_coverage": missing}


def read_room_status_snapshot(db_path, snapshot_id=None):
    """Read an immutable observation snapshot without schema creation or writes."""
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(path.as_uri()+"?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rs_snapshots'").fetchone()
            if not exists:
                return None
            if snapshot_id is None:
                row = conn.execute("SELECT id,data FROM rs_snapshots ORDER BY rowid DESC LIMIT 1").fetchone()
            else:
                row = conn.execute("SELECT id,data FROM rs_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if not row:
                return None
            result = json.loads(row[1])
            result["observations"] = [json.loads(value[0]) for value in conn.execute("SELECT data FROM rs_observations WHERE snapshot_id=? ORDER BY rowid", (row[0],))]
            return result
    except (sqlite3.Error, ValueError, OSError):
        return None


def create_room_status_router(db_path):
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS rs_snapshots(id TEXT PRIMARY KEY,source_hash TEXT NOT NULL,parsing_hash TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,UNIQUE(source_hash,parsing_hash))")
        conn.execute("CREATE TABLE IF NOT EXISTS rs_observations(snapshot_id TEXT NOT NULL,observation_key TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(snapshot_id,observation_key))")

    @contextmanager
    def transaction():
        conn = sqlite3.connect(path, timeout=15)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            _fail("房态快照保存冲突，请重试；未修改运营台账", 409)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def response():
        active = read_room_status_snapshot(path)
        with sqlite3.connect(path.as_uri()+"?mode=ro", uri=True) as conn:
            snapshots = []
            for row in conn.execute("SELECT data FROM rs_snapshots ORDER BY rowid DESC"):
                item = json.loads(row[0])
                snapshots.append({key: item[key] for key in ["id", "version", "parent_snapshot_id", "imported_at", "source", "period_resolution", "summary"]} | {"active": bool(active and active["id"] == item["id"])})
        return {"active_snapshot": active, "snapshots": snapshots}

    router = APIRouter(prefix=PREFIX, tags=["本地脱敏房态观察"])

    @router.get("")
    async def get_status(request: Request):
        assert_request_scope(request)
        return response()

    @router.post("/imports")
    async def import_observations(request: Request):
        raw_bytes = await request.body()
        if len(raw_bytes) > 1024*1024:
            _fail("脱敏房态摘要超过1MiB限制", 413)
        try:
            raw = json.loads(raw_bytes)
            if not isinstance(raw, dict):
                raise ValueError
            assert_request_scope(request, raw)
            raw = {key: value for key, value in raw.items() if key not in {"tenant", "tenant_id", "site", "site_id"}}
            payload = ImportPayload.model_validate(raw).model_dump()
        except (ValueError, UnicodeError, ValidationError):
            _fail()
        observations = sorted(payload["observations"], key=lambda row: (row["month"], row["day"], ROOM_TYPES.index(row["room_type"])))
        payload["observations"] = observations
        payload["coverage"].sort(key=lambda value: value["month"])
        parsing_hash = _hash({"source_sheet": payload["source"]["sheet"], "source_range": payload["source"]["range"],
                              **{key: payload[key] for key in ["period_resolution", "room_capacity", "coverage", "observations"]}})
        source_hash = payload["source"]["sha256"]
        created = False
        with transaction() as conn:
            old = conn.execute("SELECT id FROM rs_snapshots WHERE source_hash=? AND parsing_hash=?", (source_hash, parsing_hash)).fetchone()
            if old:
                snapshot_id = old[0]
            else:
                previous = conn.execute("SELECT id,version FROM rs_snapshots WHERE source_hash=? ORDER BY version DESC LIMIT 1", (source_hash,)).fetchone()
                snapshot_id = "rss-"+uuid.uuid4().hex
                item = {"id": snapshot_id, "version": previous[1]+1 if previous else 1,
                        "parent_snapshot_id": previous[0] if previous else None,
                        "imported_at": datetime.now(timezone.utc).isoformat(), "source": payload["source"],
                        "room_capacity": payload["room_capacity"], "period_resolution": payload["period_resolution"],
                        "coverage": payload["coverage"], "parsing_hash": parsing_hash,
                        "state": "OBSERVATION_ONLY_REQUIRES_VERIFICATION", **_derived(payload, parsing_hash)}
                conn.execute("INSERT INTO rs_snapshots VALUES (?,?,?,?,?)", (snapshot_id, source_hash, parsing_hash, item["version"], _pack(item)))
                conn.executemany("INSERT INTO rs_observations VALUES (?,?,?)", [(snapshot_id, row["observation_key"], _pack(row)) for row in observations])
                created = True
        return {**response(), "state": "IMPORTED" if created else "NO_CHANGE", "created": created, "imported_snapshot_id": snapshot_id}

    return router
