"""Room observations use fictional sanitized fixtures and temporary SQLite only."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi import FastAPI
import httpx

from app.local_os.bridge import culture_service_type
from app.local_os.integration import install_local_os
from app.local_os.room_status import read_room_status_snapshot

BASE = "/api/local-os/room-status"
HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


def summary_for(rows):
    """Build fixture metadata; acceptance expectations below are explicit."""
    quantities = [row["source_reported_reservation_quantity"] for row in rows]
    return {
        "room_type_day_cells": len(rows), "blank_unknown_cells": quantities.count(None),
        "explicit_zero_cells": quantities.count(0), "positive_cells": sum(value is not None and value > 0 for value in quantities),
        "source_daily_quantity_sum": sum(value for value in quantities if value is not None),
        "by_month_daily_quantity_sum": {str(month): sum(row["source_reported_reservation_quantity"] or 0 for row in rows if row["month"] == month) for month in (11, 12)},
        "pink_daily_quantity_sum": sum(row["source_reported_reservation_quantity"] or 0 for row in rows if row["source_color"] == "pink"),
        "yellow_unconfirmed_daily_quantity_sum": sum(row["source_reported_reservation_quantity"] or 0 for row in rows if row["source_color"] == "yellow"),
        "confirmed_room_nights": None, "occupancy_rate": None, "revenue_cents": None,
    }


def fixture():
    """Synthetic 92-cell matrix, no workbook, people or organization records."""
    source_hash, sheet = "a"*64, "Sheet1"
    rows = []
    for month, first, last, twin_row, king_row, header_row in [(11, 8, 30, 4, 5, 3), (12, 1, 23, 7, 8, 6)]:
        for day in range(first, last+1):
            column = chr(68+day-first)
            for room_type, row_number, capacity in [("双床", twin_row, 18), ("大床", king_row, 10)]:
                quantity, status, color, legend = 0, "SOURCE_RECORDED_ZERO", None, None
                if room_type == "双床":
                    if month == 12 and day >= 5:
                        quantity, status = None, "UNKNOWN_BLANK"
                    elif month == 12 or day not in {14, 21, 26, 27, 28}:
                        quantity, status, color, legend = 15, "SOURCE_RESERVATION_STATUS_UNRESOLVED", "pink", "A10"
                        if month == 11 and 15 <= day <= 18:
                            quantity, status, color, legend = 10, "SOURCE_RESERVATION_UNCONFIRMED", "yellow", "A11"
                cell = column+str(row_number)
                rows.append({
                    "observation_key": f"{source_hash}:{sheet}:{cell}", "source_sha256": source_hash,
                    "source_sheet": sheet, "source_cell": cell, "source_day_cell": column+str(header_row),
                    "source_capacity_cell": "C"+str(row_number), "source_legend_cell": legend,
                    "source_year": None, "year": 2026, "month": month, "day": day,
                    "date": date(2026, month, day).isoformat(), "room_type": room_type,
                    "reported_type_capacity": capacity, "source_reported_reservation_quantity": quantity,
                    "observed_status": status, "date_resolution": "USER_CONFIRMED_RELATIVE_PERIOD",
                    "source_color": color, "authoritative_available_quantity": None, "room_ids": None,
                    "order_id": None, "amount_cents": None, "payment_status": None, "night_basis": "UNCONFIRMED",
                })
    return {
        "contract": "yantian.room-status-observations.v1", "state": "STAGED_REQUIRES_RECONCILIATION",
        "source": {"filename": "严田庄园客房11-12月预定房态.xlsx", "sha256": source_hash,
                   "sheet": sheet, "range": "A1:Z11", "provenance": "user-supplied colleague workbook",
                   "business_as_of": None, "extracted_on": "2026-10-19", "no_personal_or_organization_identifiers_exported": True},
        "period_resolution": {"source_year": None, "resolved_year": 2026, "state": "USER_CONFIRMED_RELATIVE_PERIOD", "basis": "2026-10-19 user clarified upcoming November and December"},
        "room_capacity": {"source_reported_total": 28, "source_reported_twin": 18, "source_reported_king": 10,
                          "owner_previously_reported_total": 30, "unreconciled_difference": 2,
                          "source_ranges": ["B4:C5", "B7:C8"], "current_sellable_total": None},
        "coverage": [{"year": 2026, "month": 11, "from_day": 8, "through_day": 30, "days": 23},
                     {"year": 2026, "month": 12, "from_day": 1, "through_day": 23, "days": 23}],
        "summary": summary_for(rows),
        "interpretation": {
            "pink_legend": "source prebooking annotation, business status unresolved; identifying text omitted",
            "yellow_legend": "预定（未确认）, identifying text omitted",
            "zero": "source explicitly records zero; not evidence of cleared sellable inventory",
            "blank": "unknown, never automatically zero or available",
            "daily_sum": "sum of reported room quantities across date columns; nightly allocation basis unconfirmed",
        },
        "missing": ["two-room capacity discrepancy", "room-number map", "19 blank twin-room days", "pink reservation business status", "source business as-of time", "nightly allocation and checkout convention", "maintenance/self-use and other-channel reservations", "order grouping and dates", "actual quote and payment evidence"],
        "actions_applied": {"source_workbook_edited": False, "operations_db_written": False, "rooms_created": 0, "orders_created": 0, "payments_created": 0, "published": False},
        "observations": rows,
    }


class RoomStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"operations.sqlite3"
        app = FastAPI()
        service = culture_service_type()(Path(self.temp.name)/"culture.sqlite3")
        install_local_os(app, service=service, operations_db_path=self.db)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        # A pre-existing operational row must survive import byte-for-byte.
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO op_rooms VALUES (?,?)", ("synthetic-sentinel", json.dumps({"id": "synthetic-sentinel", "code": "SYNTHETIC-KEEP", "enabled": False})))

    def operational_bytes(self):
        with sqlite3.connect(self.db) as conn:
            return {table: conn.execute("SELECT id,data FROM "+table+" ORDER BY id").fetchall()
                    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'op_%'")
                    if table != "op_idempotency"}

    async def import_ok(self, payload=None):
        response = await self.client.post(BASE+"/imports", json=payload or fixture(), headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_exact_source_observations_and_expected_windows(self):
        before = self.operational_bytes()
        result = await self.import_ok()
        snapshot = result["active_snapshot"]
        self.assertTrue(result["created"])
        self.assertEqual(snapshot["summary"]["blank_unknown_cells"], 19)
        self.assertEqual(snapshot["summary"]["explicit_zero_cells"], 51)
        self.assertEqual(snapshot["summary"]["source_daily_quantity_sum"], 310)
        self.assertEqual(snapshot["summary"]["by_month_daily_quantity_sum"], {"11": 250, "12": 60})
        self.assertIsNone(snapshot["summary"]["confirmed_room_nights"])
        self.assertIsNone(snapshot["room_capacity"]["current_sellable_total"])
        self.assertEqual({row["observation_key"]: row for row in snapshot["observations"]}, {row["observation_key"]: row for row in fixture()["observations"]})
        windows = [(item["kind"], item["start_date"], item["end_date"], item["days"]) for item in snapshot["opportunities"]]
        self.assertEqual(windows, [
            ("ALL_TYPES_ZERO", "2026-11-14", "2026-11-14", 1),
            ("ALL_TYPES_ZERO", "2026-11-21", "2026-11-21", 1),
            ("ALL_TYPES_ZERO", "2026-11-26", "2026-11-28", 3),
            ("KING_ZERO", "2026-11-08", "2026-11-30", 23),
            ("KING_ZERO", "2026-12-01", "2026-12-23", 23),
        ])
        self.assertTrue(all(item["verification_required"] and item["source_cells"] for item in snapshot["opportunities"]))
        self.assertEqual(snapshot["missing_coverage"], [{"start_date": "2026-11-01", "end_date": "2026-11-07", "days": 7}, {"start_date": "2026-12-24", "end_date": "2026-12-31", "days": 8}])
        self.assertTrue({"CAPACITY_DISCREPANCY", "UNKNOWN_BLANKS", "YELLOW_UNCONFIRMED", "PINK_STATUS_UNRESOLVED", "ROOM_NUMBER_MAP_MISSING", "QUOTE_AND_PAYMENT_UNKNOWN"}.issubset({issue["code"] for issue in snapshot["issues"]}))
        self.assertEqual(before, self.operational_bytes())

    async def test_reimport_is_no_change_and_does_not_create_more_rows(self):
        first = await self.import_ok()
        payload = fixture()
        payload["observations"].reverse()
        second = await self.import_ok(payload)
        self.assertEqual(second["state"], "NO_CHANGE")
        self.assertFalse(second["created"])
        self.assertEqual(first["active_snapshot"], second["active_snapshot"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rs_snapshots").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rs_observations").fetchone()[0], 92)

    async def test_changed_resolution_keeps_history_and_replay_does_not_reactivate_old(self):
        first = (await self.import_ok())["active_snapshot"]
        revised = fixture()
        revised["period_resolution"].update(resolved_year=2027, basis="operator confirmed year 2027")
        for coverage in revised["coverage"]:
            coverage["year"] = 2027
        for row in revised["observations"]:
            row.update(year=2027, date=date(2027, row["month"], row["day"]).isoformat())
        second = (await self.import_ok(revised))["active_snapshot"]
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["parent_snapshot_id"], first["id"])
        self.assertEqual(read_room_status_snapshot(self.db, first["id"]), first)
        replay = await self.import_ok()
        self.assertEqual(replay["active_snapshot"]["id"], second["id"])
        self.assertEqual(replay["imported_snapshot_id"], first["id"])
        self.assertEqual(sum(item["active"] for item in replay["snapshots"]), 1)
        self.assertEqual(len(replay["snapshots"]), 2)

    async def test_unknown_unconfirmed_and_unresolved_year_do_not_create_zero_windows(self):
        for state in ["UNKNOWN_BLANK", "SOURCE_RESERVATION_UNCONFIRMED"]:
            payload = fixture()
            for row in payload["observations"]:
                row.update(observed_status=state, source_reported_reservation_quantity=None if state == "UNKNOWN_BLANK" else 1,
                           source_color=None if state == "UNKNOWN_BLANK" else "yellow", source_legend_cell=None if state == "UNKNOWN_BLANK" else "A11")
            payload["summary"] = summary_for(payload["observations"])
            result = await self.import_ok(payload)
            self.assertEqual(result["active_snapshot"]["opportunities"], [])
        unresolved = fixture()
        unresolved["period_resolution"].update(resolved_year=None, state="UNRESOLVED", basis="year unresolved")
        for coverage in unresolved["coverage"]:
            coverage["year"] = None
        for row in unresolved["observations"]:
            row.update(year=None, date=None, date_resolution="UNRESOLVED")
        snapshot = (await self.import_ok(unresolved))["active_snapshot"]
        self.assertEqual(snapshot["opportunities"], [])
        self.assertIn("YEAR_UNRESOLVED", {issue["code"] for issue in snapshot["issues"]})

    async def test_invalid_quantities_dates_states_and_conflicting_summary_rejected(self):
        cases = []
        for field, value in [("source_reported_reservation_quantity", 19), ("source_reported_reservation_quantity", -1), ("source_reported_reservation_quantity", True), ("date", "2026-11-31"), ("day", 9), ("observed_status", "SOURCE_RECORDED_ZERO"), ("observed_status", "CONFIRMED"), ("reported_type_capacity", 17)]:
            payload = fixture()
            payload["observations"][0][field] = value
            cases.append(payload)
        payload = fixture()
        payload["summary"]["blank_unknown_cells"] = 0
        cases.append(payload)
        payload = fixture()
        payload["room_capacity"]["source_reported_total"] = 30
        cases.append(payload)
        payload = fixture()
        payload["observations"].pop()
        cases.append(payload)
        for payload in cases:
            response = await self.client.post(BASE+"/imports", json=payload, headers=HEADERS)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(read_room_status_snapshot(self.db))

    async def test_raw_private_fields_and_path_imports_are_not_accepted(self):
        cases = []
        for location, key, value in [("root", "file_path", "/private/no-read.xlsx"), ("source", "raw_legend", "SYNTHETIC_PRIVATE_MARKER"), ("row", "group_name", "SYNTHETIC_PRIVATE_MARKER"), ("row", "guest_name", "SYNTHETIC_PRIVATE_MARKER"), ("row", "room_ids", ["invented-room"]), ("row", "amount_cents", 38000), ("row", "payment_status", "paid"), ("source", "filename", "../private.xlsx")]:
            payload = fixture()
            target = payload if location == "root" else payload["source"] if location == "source" else payload["observations"][0]
            target[key] = value
            cases.append(payload)
        for payload in cases:
            response = await self.client.post(BASE+"/imports", json=payload, headers=HEADERS)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", response.text)
        self.assertIsNone(read_room_status_snapshot(self.db))

    async def test_real_os_scope_and_same_origin_boundary_applies(self):
        payload = fixture()
        for headers in [{}, {**HEADERS, "Origin": "https://foreign.invalid"}, {**HEADERS, "X-Tenant-ID": "other"}]:
            response = await self.client.post(BASE+"/imports", json=payload, headers=headers)
            self.assertEqual(response.status_code, 403, response.text)
        for key in ["tenant_id", "site_id"]:
            response = await self.client.post(BASE+"/imports", json={**payload, key: "other"}, headers=HEADERS)
            self.assertEqual(response.status_code, 403, response.text)
        response = await self.client.get(BASE+"?site_id=other")
        self.assertEqual(response.status_code, 403)
        self.assertEqual((await self.client.get(BASE)).json(), {"active_snapshot": None, "snapshots": []})


class ReadOnlyHelperTests(unittest.TestCase):
    def test_missing_or_unrelated_database_does_not_create_observation_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"missing.sqlite3"
            self.assertIsNone(read_room_status_snapshot(path))
            self.assertFalse(path.exists())
            with sqlite3.connect(path) as conn:
                conn.execute("CREATE TABLE unrelated(id INTEGER)")
            self.assertIsNone(read_room_status_snapshot(path))
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("unrelated",)])


if __name__ == "__main__":
    unittest.main()
