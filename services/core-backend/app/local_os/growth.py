"""Deterministic local growth material compiler. No model/publishing calls.

gr_* records share the operations SQLite; cultural evidence is read through the
canonical service and only exact citation snapshots are kept in packages.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
from typing import Literal
from urllib.parse import urlsplit
import uuid
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .bridge import assert_request_scope

BASE_URL = "/api/local-os/growth"
CHANNEL = Literal["direct", "xiaohongshu", "douyin"]
TABLES = {"campaigns", "assets", "packages", "reviews", "distributions", "metrics"}
MAX_FILE = 100*1024*1024
COMPILER_VERSION = "yantian-growth-materials-v1.4"
CAPABILITIES = {"mode": "local_material_compiler", "provider_connected": False,
                "publishing_connected": False, "finished_video_generation": True, "video_generation_mode": "local_preview_render", "contract": "yantian.growth-materials.v1", "compiler_version": COMPILER_VERSION}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix+"-"+uuid.uuid4().hex


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else pack(value).encode()).hexdigest()


def fail(message, status=422):
    raise HTTPException(status, message)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def no_controls(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 and char not in "\r\n\t" for char in value):
            raise ValueError("不允许控制字符")
        return value


class RoomStatusRef(Input):
    snapshot_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    opportunity_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$")


class WorkspacePlanRef(Input):
    plan_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CampaignInput(Input):
    title: str = Field(min_length=1, max_length=160)
    audience: str = Field(min_length=1, max_length=1000)
    product_summary: str = Field(min_length=1, max_length=2000)
    objective: str = Field(min_length=1, max_length=1000)
    primary_channel: CHANNEL
    source_code: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_\-\u3400-\u9fff]+$")
    notes: str = Field(default="", max_length=4000)
    base_version: int | None = Field(default=None, ge=1)
    room_status_ref: RoomStatusRef | None = None
    workspace_plan_ref: WorkspacePlanRef | None = None


class CompileInput(Input):
    base_version: int = Field(ge=1)
    angle: Literal["stay", "culture", "woodcut"]
    duration_seconds: Literal[15, 30, 60]
    knowledge_ids: list[str] = Field(default_factory=list, max_length=12)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=4000)

    @field_validator("knowledge_ids", "asset_ids")
    @classmethod
    def ids(cls, value):
        if len(value) != len(set(value)) or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", item) for item in value):
            raise ValueError("编号重复或无效")
        return value


class Confirmations(Input):
    facts: bool
    rights: bool
    delivery: bool


class ReviewInput(Input):
    package_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")
    decision: Literal["approve", "changes_requested"]
    note: str = Field(min_length=1, max_length=4000)
    confirmations: Confirmations


class DistributionInput(Input):
    package_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")
    channel_id: CHANNEL
    external_url: str = Field(min_length=1, max_length=2048)
    reference: str = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=4000)

    @field_validator("external_url")
    @classmethod
    def https_only(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("只接受无凭据https链接；不会访问该链接")
        if re.search(r"(?:^|&)(?:token|secret|password|api_key)=", parsed.query, re.I):
            raise ValueError("链接不得含凭据")
        return value


class MetricInput(Input):
    channel_id: CHANNEL
    views: int | None = Field(default=None, ge=0, le=1000000000000)
    likes: int | None = Field(default=None, ge=0, le=1000000000000)
    saves: int | None = Field(default=None, ge=0, le=1000000000000)
    spend_cents: int | None = Field(default=None, ge=0, le=1000000000000)
    period_start: str = Field(min_length=10, max_length=10)
    period_end: str = Field(min_length=10, max_length=10)
    note: str = Field(default="", max_length=4000)

    @field_validator("period_start", "period_end")
    @classmethod
    def calendar_date(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("日期格式错误")
        date.fromisoformat(value)
        return value


class Shot(Input):
    start_seconds: int = Field(ge=0, le=60)
    end_seconds: int = Field(ge=1, le=60)
    visual: str = Field(min_length=1, max_length=2000)
    voiceover: str = Field(default="", max_length=4000)
    asset_id: str | None = Field(default=None, max_length=120)
    capture_needed: bool


class ChannelCopy(Input):
    xiaohongshu: str = Field(max_length=6000)
    douyin: str = Field(max_length=6000)
    direct: str = Field(max_length=6000)


class Claim(Input):
    text: str = Field(max_length=4000)
    basis: str = Field(max_length=1000)
    scope: str = Field(max_length=1000)


class Materials(Input):
    title: str = Field(min_length=1, max_length=240)
    hook: str = Field(min_length=1, max_length=2000)
    voiceover: str = Field(min_length=1, max_length=20000)
    storyboard: list[Shot] = Field(min_length=1, max_length=30)
    shot_list: list[str] = Field(max_length=40)
    srt: str = Field(max_length=30000)
    cover_text: str = Field(max_length=1000)
    image_prompt: str = Field(max_length=6000)
    video_prompt: str = Field(max_length=6000)
    channel_copy: ChannelCopy
    cta: str = Field(max_length=2000)
    claims: list[Claim] = Field(max_length=30)
    missing_inputs: list[str] = Field(max_length=30)
    task_brief: dict[str, str] = Field(default_factory=dict, max_length=10)
    usage_checklist: list[str] = Field(default_factory=list, max_length=40)
    planning_references: list[dict] = Field(default_factory=list, max_length=12)


class EditInput(Input):
    base_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")
    materials: Materials


async def body(request, model):
    try:
        raw = await request.json()
    except ValueError:
        fail("请输入合法JSON对象")
    if not isinstance(raw, dict):
        fail("请输入JSON对象")
    assert_request_scope(request, raw)
    raw = {key: value for key, value in raw.items() if key not in {"tenant", "tenant_id", "site", "site_id"}}
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        fields = ",".join(".".join(map(str, item["loc"])) for item in exc.errors()[:5])
        fail("输入校验失败，请检查字段、长度、版本及数值："+fields)


def guard_claims(materials):
    text = pack(materials)
    for sentence in re.split(r"[。！？\n]", text):
        if "380" in sentence and re.search(r"套餐|组合价|打包价", sentence) and not re.search(r"不是|不能|不等于|不代表|并非|非套餐", sentence):
            fail("380元只能标为住宿参考，不能改写成套餐价")
    if re.search(r"严田.{0,30}(?:千年木刻|木刻起源|非遗传承人|祖传木刻|木刻始于)", text):
        fail("当前资料不能支持该严田局地历史/传承断言")


def resolve_room_window(db_path, reference, require_current=True):
    if not reference:
        return None
    from .room_status import read_room_status_snapshot
    reference = reference.model_dump() if isinstance(reference, RoomStatusRef) else reference
    snapshot = read_room_status_snapshot(db_path, reference['snapshot_id'])
    if not snapshot:
        fail("房态来源快照不存在，请返回最新房态重新选择", 409)
    latest = read_room_status_snapshot(db_path)
    if require_current and (not latest or latest['id'] != snapshot['id']):
        fail("房态来源版本已更新，请从最新日期重新建立任务", 409)
    window = next((item for item in snapshot['opportunities'] if item['id'] == reference['opportunity_id']), None)
    if not window:
        fail("所选日期不属于该房态来源的零预订推广窗口", 422)
    return {'snapshot_id': snapshot['id'], 'opportunity_id': window['id'],
            'snapshot_hash': digest(snapshot), 'source': snapshot['source'],
            'room_capacity': snapshot['room_capacity'], 'window': window,
            'interpretation': '原表明确填0预订的日期候选，未核实现场/其他渠道，不代表可售库存或订房承诺'}


def read_local_context(db_path):
    """One read-only configuration summary shared by planning and video layers."""
    file = Path(db_path).expanduser().resolve().parent / 'yantian-growth-context.json'
    if not file.exists():
        return {'version': 1, 'products': [], 'materials': [], 'facts': [], 'missing': ['本机已有配置及历史资料待核对后加入，未知不等于产品不存在']}
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 1024*1024:
        return {'version': 1, 'products': [], 'materials': [], 'facts': [], 'missing': ['受控本机配置摘要无法安全读取，等待本地核对']}
    try:
        value = json.loads(file.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError
        return {key: value.get(key, [] if key in {'products', 'materials', 'facts', 'missing'} else None) for key in ['version', 'checked_at', 'products', 'materials', 'facts', 'missing']}
    except (ValueError, OSError, UnicodeError):
        return {'version': 1, 'products': [], 'materials': [], 'facts': [], 'missing': ['本机配置摘要格式待核对']}


def resolve_workspace_plan(db_path, reference):
    if not reference:
        return None
    from .workspace import read_workspace_plan
    reference = reference.model_dump() if isinstance(reference, WorkspacePlanRef) else reference
    plan = read_workspace_plan(db_path, reference['plan_id'])
    if not plan or plan['hash'] != reference['plan_hash'] or not plan.get('confirmation_valid') or plan.get('source_stale'):
        fail('运营方案版本已更新、尚未确认或依据已变化，请回第一层确认当前方案', 409)
    return {'plan_id': plan['id'], 'plan_hash': plan['hash'], 'version': plan['version'],
            'plan': plan['plan'], 'confirmation_scope': '仅确认运营方案方向；房态、体验供给、价格与发布仍分别核实'}


def create_campaign_from_workspace_plan(db_path, plan_dto):
    """Explicit layer handoff creates a task only, with no script compilation."""
    path = Path(db_path).expanduser().resolve()
    reference = {'plan_id': plan_dto['id'], 'plan_hash': plan_dto['hash']}
    conn = sqlite3.connect(path, timeout=15)
    try:
        conn.execute('BEGIN IMMEDIATE')
        resolved = resolve_workspace_plan(str(path), reference)
        proposal = resolved['plan']
        source_context = plan_dto.get('source_context') or {}
        room_ref = plan_dto.get('room_status_ref') or source_context.get('room_status_ref')
        if room_ref:
            resolve_room_window(str(path), room_ref)
        source_code = 'yt-plan-'+reference['plan_hash'][:24]
        old = conn.execute('SELECT campaign_id FROM gr_source_codes WHERE code=?', (source_code,)).fetchone()
        if old:
            row = conn.execute('SELECT data FROM gr_campaigns WHERE id=?', (old[0],)).fetchone()
            campaign = json.loads(row[0]) if row else None
            if not campaign or campaign.get('workspace_plan_ref') != reference:
                fail('方案来源码已存在冲突，请保留现有任务并核对', 409)
            campaign_id, created = old[0], False
        else:
            audience = '；'.join(item['name']+'（策划假设）' for item in proposal.get('audiences', [])) or '拟来严田住宿并了解文化体验的出行者，客群待验证'
            offering = proposal.get('offering') or {}
            candidates = offering.get('experience_candidates', [])
            summary = offering.get('stay_statement', '住宿＋文化体验为持有人确认的现成产品')
            if candidates:
                summary += '\nCREATE候选：'+'、'.join(item['id']+' '+item['title'] for item in candidates)+'；目录候选不等于本次套餐已包含。'
            notes = proposal.get('one_line_strategy', '')+'\n第一层确认仅采用策划方向，待核信息保持待核。'
            channels = proposal.get('channels') or []
            primary = next((item['id'] for item in channels if item.get('id') in {'xiaohongshu','douyin','direct'}), 'xiaohongshu')
            data = CampaignInput(title=(proposal['title']+'｜视频脚本')[:160], audience=audience[:1000],
                                 product_summary=summary[:2000], objective=proposal.get('objective', '收集具体日期与人数的住宿咨询')[:1000],
                                 primary_channel=primary, source_code=source_code, notes=notes[:4000],
                                 room_status_ref=room_ref, workspace_plan_ref=reference)
            campaign = {**data.model_dump(exclude={'base_version'}), 'id':uid('campaign'),'version':1,'created_at':now(),'updated_at':now()}
            campaign_id, created = campaign['id'], True
            conn.execute('INSERT INTO gr_source_codes VALUES (?,?)',(source_code,campaign_id))
            conn.execute('INSERT INTO gr_campaigns VALUES (?,?)',(campaign_id,pack(campaign)))
            conn.execute('INSERT INTO gr_campaign_versions VALUES (?,?,?)',(campaign_id,1,pack(campaign)))
        conn.commit()
        return {'campaign_id':campaign_id,'source_code':source_code,'created':created,
                'url':'/growth?campaign='+campaign_id+'&workspace_plan='+reference['plan_id']+'#video',
                'scripts_generated':False,'provider_calls':[],'external_side_effects':[]}
    except (sqlite3.IntegrityError, sqlite3.OperationalError):
        conn.rollback()
        fail('方案交接记录冲突或服务繁忙，请刷新重试',409)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_growth_router(db_path: str, culture_service=None) -> APIRouter:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    asset_root = path.parent / "growth-assets"
    if asset_root.is_symlink():
        raise ValueError("素材目录不得是符号链接")
    asset_root.mkdir(exist_ok=True)
    asset_root = asset_root.resolve()
    conn = sqlite3.connect(path)
    try:
        for table in TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS gr_{table} (id TEXT PRIMARY KEY,data TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS gr_campaign_versions(id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(id,version))")
        conn.execute("CREATE TABLE IF NOT EXISTS gr_source_codes(code TEXT PRIMARY KEY,campaign_id TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS gr_compile_inputs(hash TEXT PRIMARY KEY,package_id TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS gr_metric_periods(key TEXT PRIMARY KEY,metric_id TEXT NOT NULL)")
        conn.commit()
    finally:
        conn.close()

    @contextmanager
    def transaction():
        connection = sqlite3.connect(path, timeout=15)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except HTTPException:
            connection.rollback()
            raise
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            connection.rollback()
            fail("记录冲突或正在处理中，请刷新后重试", 409)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rows(conn, table):
        if table not in TABLES:
            raise ValueError("invalid internal table")
        return [json.loads(row[0]) for row in conn.execute(f"SELECT data FROM gr_{table} ORDER BY rowid")]

    def get(conn, table, item_id):
        if table not in TABLES:
            raise ValueError("invalid internal table")
        row = conn.execute(f"SELECT data FROM gr_{table} WHERE id=?", (item_id,)).fetchone()
        if not row:
            fail("指定资料记录不存在")
        return json.loads(row[0])

    def insert(conn, table, item):
        conn.execute(f"INSERT INTO gr_{table} VALUES (?,?)", (item["id"], pack(item)))
        return item

    def op_rows(conn, table):
        if table not in {"leads", "orders", "payments", "refunds", "products"}:
            raise ValueError("invalid operations table")
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", ("op_"+table,)).fetchone()
        return [json.loads(row[0]) for row in conn.execute(f"SELECT data FROM op_{table}")] if exists else []

    def local_context():
        return read_local_context(str(path))

    def business_facts(context):
        from .room_status import read_room_status_snapshot
        room_snapshot = read_room_status_snapshot(str(path))
        return {"property_name": "严田庄园", "stay_capacity_rooms": 30, "stay_reference_price_cents": 38000,
                "source_reported_capacity_rooms": room_snapshot['room_capacity']['source_reported_total'] if room_snapshot else None,
                "capacity_reconciliation": "持有人声明30间，最新表列28间，差2间待核；都不等于已核可售量" if room_snapshot else "待导入房态来源核对",
                "season": "淡季", "primary_goal": "住宿获客", "product_summary": "住宿+文化体验为用户确认现成产品",
                "experience_details_state": "本机目录已整合，现行包含项与套餐价待核" if context.get("products") else "本机配置记录待核对", "bundle_price_cents": None,
                "woodcut_inclusion_confirmed": False, "configuration_references": context.get("products", []),
                "provenance": "用户当前陈述；具体配置由本机资料核对，历史计划不等于当前可售套餐",
                "note": "380元仅住宿参考，不是组合套餐价；文化/木刻为内容支线，不能自动承诺木刻为现售包含项"}

    async def evidence():
        if culture_service is None:
            return [], {}
        knowledge = await culture_service.list_knowledge()
        sources = {item["id"]: item for item in await culture_service.list_sources()}
        return knowledge, sources

    def usable_knowledge(item, sources):
        source = sources.get(item["source_id"], {})
        return item["review_status"] in {"source_checked", "approved"} and item["rights_scope"] == "internal" and source.get("rights_scope") == "internal"

    def read_asset(item):
        name = item.get("storage_name", "")
        if not re.fullmatch(r"[a-f0-9]{32}\.(?:png|jpg|webp|gif|mp4|mov|txt|pdf)", name):
            return None, "changed"
        target = asset_root / name
        if target.parent.resolve() != asset_root or target.is_symlink():
            return None, "changed"
        try:
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return None, "changed"
                data = handle.read(MAX_FILE+1)
        except (OSError, ValueError):
            return None, "missing"
        if len(data) != item["size_bytes"] or digest(data) != item["sha256"]:
            return None, "changed"
        return data, "valid"

    def asset_dto(item):
        _, state = read_asset(item)
        return {key: value for key, value in item.items() if key != "storage_name"} | {"usable": state == "valid", "integrity_state": state, "file_url": BASE_URL+"/assets/"+item["id"]+"/file"}

    def attribution(conn, campaign):
        leads = [item for item in op_rows(conn, "leads") if item.get("source_code") == campaign["source_code"]]
        orders = [item for item in op_rows(conn, "orders") if item.get("source_code") == campaign["source_code"]]
        ids = {item["id"] for item in orders}
        received = sum(item["amount_cents"] for item in op_rows(conn, "payments") if item["order_id"] in ids) if orders else None
        refunded = sum(item["amount_cents"] for item in op_rows(conn, "refunds") if item["order_id"] in ids) if orders else None
        metrics = [item for item in rows(conn, "metrics") if item["campaign_id"] == campaign["id"]]
        return {"source_code": campaign["source_code"], "leads_count": len(leads), "valid_leads_count": None,
                "orders_count": len(orders), "confirmed_orders_count": sum(item["status"] in {"confirmed", "fulfilled"} for item in orders),
                "received_cents": received, "refunded_cents": refunded, "net_cash_cents": received-refunded if orders else None,
                "cash_state": "MISSING" if not orders else "MANUALLY_RECORDED", "views": metrics[0]["views"] if len(metrics) == 1 else None,
                "views_state": "MISSING" if not metrics else "PERIOD_SPECIFIC" if len(metrics) == 1 else "MULTIPLE_PERIODS_NOT_SUMMED",
                "note": "来源码仅作本地关联；咨询不等于有效客户/成交，人工收退款是现金登记而非营业收入或独立核验到账。"}

    def knowledge_refs(ids, knowledge, sources):
        index = {item["id"]: item for item in knowledge}
        refs = []
        for item_id in ids:
            item = index.get(item_id)
            if not item or not usable_knowledge(item, sources):
                fail("选用知识不存在，或属于草稿/争议/退役/权利未知；不能用于材料事实")
            source = sources[item["source_id"]]
            refs.append({"knowledge_id": item_id, "knowledge_version": item["version"], "title": item["title"],
                         "excerpt": item["content"][:650], "source_id": item["source_id"], "source_title": source["title"],
                         "url": source.get("url", ""), "locator": item["locator"], "region_scope": item["region_scope"],
                         "review_status": item["review_status"], "rights_scope": item["rights_scope"], "domain": item["domain"], "kind": item["kind"]})
        return refs

    def blockers_for(item, conn, knowledge, sources, context):
        blockers = list(item.get("production_blockers", []))
        if any(shot.get("capture_needed") for shot in item["materials"]["storyboard"]):
            blockers.append("分镜仍有待拍镜头，资料可审阅但发布前须补齐对应现场素材")
        campaign = get(conn, "campaigns", item["campaign_id"])
        if any(other.get("parent_package_id") == item["id"] for other in rows(conn, "packages")):
            blockers.append("稿包已被编辑新版本替代，旧审阅仅供历史追溯")
        if campaign["version"] != item["campaign_version"]:
            blockers.append("活动版本已更新，旧包需按新版本重新编译/审阅")
        if item["context_hash"] != digest(context):
            blockers.append("受控本机产品配置摘要已变化，需重新编译/审阅")
        room_ref = item.get('room_status_context')
        if room_ref:
            try:
                current_room = resolve_room_window(str(path), room_ref)
                if current_room['snapshot_hash'] != room_ref['snapshot_hash']:
                    blockers.append('房态来源摘要已变化，需重新编译/审阅')
            except HTTPException:
                blockers.append('房态来源版本已更新或不可用，需重新编译/审阅')
        workspace_ref = item.get('workspace_plan_context')
        if workspace_ref:
            try:
                resolve_workspace_plan(str(path), workspace_ref)
            except HTTPException:
                blockers.append('第一层运营方案版本已更新或确认依据已变化，需重新交接/审阅')
        index = {row["id"]: row for row in knowledge}
        for ref in item["knowledge_refs"]:
            if ref.get("rights_scope") == "internal":
                blockers.append("引用知识仅限内部使用，对外使用范围未确认："+ref["knowledge_id"])
            current = index.get(ref["knowledge_id"])
            if not current or current["version"] != ref["knowledge_version"] or not usable_knowledge(current, sources):
                blockers.append("引用知识已更新、退役或权利状态变化："+ref["knowledge_id"])
        for ref in item["asset_refs"]:
            asset = get(conn, "assets", ref["id"])
            _, state = read_asset(asset)
            if state != "valid" or asset["sha256"] != ref["sha256"]:
                blockers.append("素材文件缺失或哈希已变化："+ref["id"])
            if not asset["rights_confirmed"]:
                blockers.append("素材使用权未经人工确认："+ref["id"])
        return list(dict.fromkeys(blockers))

    def approval_blockers(blockers):
        return [value for value in blockers if any(word in value for word in ["编辑新版本替代", "版本已更新", "摘要已变化", "知识已更新", "文件缺失", "哈希已变化", "使用权未经"]) ]

    def package_dto(item, conn, knowledge, sources, context):
        blockers = blockers_for(item, conn, knowledge, sources, context)
        reviews = [review for review in rows(conn, "reviews") if review["package_id"] == item["id"] and review["package_hash"] == item["hash"]]
        state = reviews[-1]["decision"] if reviews else "unreviewed"
        if state == "approve":
            state = "invalidated" if approval_blockers(blockers) else "approved"
        return {**item, "blockers": blockers, "review_status": state, "approval_valid": state == "approved",
                "distribution_ready": state == "approved" and not blockers,
                "export_url": BASE_URL+"/packages/"+item["id"]+"/export"}

    async def render_snapshot(package_id):
        """The same source readers, with a separate internal-preview rights scope."""
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            item = get(conn, "packages", package_id)
            campaign = get(conn, "campaigns", item["campaign_id"])
            latest = max(p["version"] for p in rows(conn, "packages") if p["campaign_id"] == item["campaign_id"])
            all_blockers = blockers_for(item, conn, knowledge, sources, context)
            # Unconfirmed rights and incomplete field capture remain visible on
            # the watermarked preview. Public-distribution gates remain intact.
            blockers = [value for value in approval_blockers(all_blockers) if "使用权未经" not in value]
            if item["version"] != latest:
                blockers.append("脚本分镜已有更新版本，请选择当前版本后重新确认")
            if digest({key: value for key, value in item.items() if key != "hash"}) != item["hash"]:
                blockers.append("不可变脚本分镜记录完整性检查失败")
            shots = item["materials"]["storyboard"]
            if not 2 <= len(shots) <= 20 or item["duration_seconds"] not in {15, 30, 60}:
                blockers.append("本地成片目前支持15、30或60秒及2至20个分镜")
            warnings = [value for value in all_blockers if value not in blockers]
            assets = []
            total_bytes = 0
            asset_fingerprints = []
            for ref in item["asset_refs"]:
                asset = get(conn, "assets", ref["id"])
                blob, state = read_asset(asset)
                asset_fingerprints.append({key: asset.get(key) for key in ["id", "sha256", "size_bytes", "rights_confirmed", "evidence_status", "kind", "media_type", "title", "caption"]})
                if state != "valid" or asset["sha256"] != ref["sha256"]:
                    continue
                total_bytes += len(blob)
                if asset["kind"] not in {"photo", "video"}:
                    continue
                if not asset["rights_confirmed"]:
                    warnings.append("素材权利未确认，仅供标识清楚的本地待审预览："+asset["id"])
                if asset.get("evidence_status") != "site_photo":
                    warnings.append("历史、概念或未知素材不代替当期现场："+asset["id"])
                assets.append({key: asset.get(key) for key in ["id", "sha256", "size_bytes", "kind", "media_type", "evidence_status", "rights_confirmed", "title", "caption"]} | {"bytes": blob, "extension": asset["storage_name"].split(".")[-1]})
            if len(item["asset_refs"]) > 20 or total_bytes > 200*1024*1024:
                blockers.append("本地成片最多20份素材、总计200MiB，请减少后重新保存脚本")
            if any(shot.get("capture_needed") for shot in shots):
                warnings.append("待拍镜头使用明确标注的原创图形/文字预览，不作为现场证明")
            current_knowledge = {row["id"]: row for row in knowledge}
            knowledge_fingerprints = [{"knowledge": current_knowledge.get(ref["knowledge_id"]), "source": sources.get(ref["source_id"])} for ref in item["knowledge_refs"]]
            fingerprint = digest({"package_hash": item["hash"], "campaign": campaign,
                                  "latest_package_version": latest, "current_context_hash": digest(context),
                                  "room_status_context": item.get("room_status_context"),
                                  "workspace_plan_context": item.get("workspace_plan_context"),
                                  "knowledge": knowledge_fingerprints, "assets": asset_fingerprints})
            input_fingerprints = {"assets": asset_fingerprints,
                                  "context_hash": digest(context), "campaign_version": campaign["version"],
                                  "room_status": {key: item.get("room_status_context", {}).get(key) for key in ["snapshot_id", "opportunity_id", "snapshot_hash"]} if item.get("room_status_context") else None,
                                  "workspace_plan": {key: item.get("workspace_plan_context", {}).get(key) for key in ["plan_id", "plan_hash", "version"]} if item.get("workspace_plan_context") else None,
                                  "knowledge": item["knowledge_refs"]}
            return {"package": item, "fingerprint": fingerprint, "assets": assets, "input_fingerprints": input_fingerprints,
                    "blockers": list(dict.fromkeys(blockers)), "warnings": list(dict.fromkeys(warnings))}

    def generate(campaign, data, refs, assets, context, room_context=None, workspace_context=None):
        angle = {"stay": "住下来，体验文化", "culture": "住一晚，了解一段文化", "woodcut": "把木刻观察带入旅途"}[data.angle]
        hook = {"stay": "来严田住一晚，把时间留给文化体验。", "culture": "来严田住下来，让旅途多一段文化观察。", "woodcut": "住下来，留一点时间观察木刻中的线条与印痕。"}[data.angle]
        current_products = [p for p in context.get("products", []) if p.get("status") in {"user_confirmed", "current_config"} and p.get("source_refs") and all(r.get("title") and r.get("locator") and r.get("evidence_status") in {"user_confirmed", "current_config"} for r in p["source_refs"])]
        config_text = "；".join(str(p.get("summary", "")) for p in current_products)
        selected_plans = [p for p in context.get("products", []) if p.get("status") == "LOCAL_IMPLEMENTED_CATALOG" and any(str(p.get(key, "")) and str(p.get(key)) in campaign["product_summary"] for key in ["id", "title"])][:12]
        planning_refs = [{key: p.get(key) for key in ["id", "title", "summary", "experience_items", "source_refs", "status", "conditions"]} for p in selected_plans]
        reference_note = "30间、淡季住宿380元为用户提供的住宿参考；具体房型、日期及报价需确认，不代表套餐报价。"
        if room_context:
            reference_note = "住宿、文化体验项目、可订房型及组合报价，请按到店日期和人数逐项确认。"
            planning_refs.append({'kind': 'room_status_window', **room_context})
        # Campaign fields are a planning brief, never independently verified claims.
        brief = {"title": campaign["title"], "audience": campaign["audience"], "product_summary": campaign["product_summary"],
                 "objective": campaign["objective"], "campaign_notes": campaign["notes"], "compile_notes": data.notes,
                 "assumption_notice": "以上为任务策划输入；未经出处/交付核对的描述只能作待拍提纲，不能直接当经营事实。"}
        if workspace_context:
            proposal = workspace_context['plan']
            brief['operations_plan'] = pack({'plan_id':workspace_context['plan_id'], 'plan_hash':workspace_context['plan_hash'],
                                             'version':workspace_context['version'],'title':proposal['title'],
                                             'strategy':proposal.get('one_line_strategy',''),'objective':proposal.get('objective','')})
            planning_refs.append({'kind':'confirmed_operations_plan',**workspace_context})
        cta_spoken = "告诉我们日期与人数，确认房型与文化体验安排。"
        window_label = ''
        if room_context:
            window = room_context['window']
            start, end = date.fromisoformat(window['start_date']), date.fromisoformat(window['end_date'])
            window_label = f'{start.month}月{start.day}日' if start == end else (f'{start.month}月{start.day}日至{end.day}日' if start.month == end.month else f'{start.month}月{start.day}日至{end.month}月{end.day}日')
            brief['room_window'] = pack({'candidate_dates': window_label, **room_context})
        scoped_excerpt = None
        if data.angle in {"culture", "woodcut"} and refs:
            first = refs[0]
            scope = {"regional": "区域资料", "huizhou": "徽州资料", "wuyuan": "婺源资料", "yantian": "严田资料"}.get(first["region_scope"], str(first["region_scope"]))
            # Read a short source-backed statement with its scope; full locator stays in the documents.
            scoped_excerpt = scope+"提到："+re.split(r"[。！？\n]", first["excerpt"])[0][:38]+"。"
        if data.duration_seconds == 15:
            if scoped_excerpt and all(word in refs[0]["excerpt"] for word in ["砖雕", "石雕", "木雕"]):
                short_fact = "徽州三雕，包括砖雕、石雕和木雕。"
            elif scoped_excerpt:
                short_fact = "参考区域资料，观察文化细节。"
            else:
                short_fact = "把时间留给文化体验。"
            spoken = ["来严田，住下来。", short_fact, "行程慢一点。", cta_spoken]
        elif data.duration_seconds == 30:
            spoken = [hook+"从住宿行程开始，为这次出行留出从容的时间。",
                      "先看看房间与公共空间，再按日期、人数一起安排。",
                      scoped_excerpt or "住宿之外，也可以了解文化体验，挑选适合这次行程的内容。",
                      cta_spoken]
        elif data.duration_seconds == 60:
            detail = ("当次已登记的体验配置是："+config_text[:55]+"。") if config_text else "可以先了解住宿与文化体验，再一起确认这次适合的内容，把想看的、想体验的安排进自己的旅程。"
            spoken = [hook+"放慢脚步，不急着赶下一站。",
                      "从住宿开始，看看房间与公共空间，想一想这次怎样度过自己的时间。",
                      scoped_excerpt or "把时间留给观察与体验，和同行的人商量一下，哪些内容最适合这次行程。",
                      detail,
                      "先选想来的日期，说说同行人数和住宿想法，一起安排这段旅程。",
                      cta_spoken]
        if room_context:
            room_type_note = '大床住宿' if room_context['window']['kind'] == 'KING_ZERO' else '住宿'
            hook = f'想在{window_label}来严田住下来，体验一段文化行程？'
            if data.duration_seconds == 15:
                spoken = [f'{window_label}，想来严田住一晚？', '住宿加文化体验，先选到店日。', '发来日期人数，核房后确认安排。']
            elif data.duration_seconds == 30:
                spoken = [hook, f'先看看{room_type_note}的实拍，再说说这次有几位同行。',
                          '住宿加文化体验，是我们现有的产品方向。具体体验内容和安排，一起按行程核对。',
                          '发来入住日、离店日和人数，我们核房，再确认房型、体验与报价。']
            else:
                spoken = [hook, '行程从住处开始。先看看实际房间、床型和公共空间，选择适合自己的住宿方式。',
                          '住宿加文化体验，是我们现有的产品方向。先聊聊这次想了解什么，再核对能安排的体验项目和场次。',
                          '具体内容、是否包含材料、需要多长时间，都在预订前说清楚。',
                          '把入住日、离店日、同行人数和想法发来，我们先核房，再一起确认住宿和文化体验的安排与报价。',
                          '日期和人数发来，先做一份适合自己的严田行程。']
        cta = "住宿咨询：/stay?source="+campaign["source_code"]+"。本地页面仅登记咨询意向，不自动锁房或收款。"
        visual_assets = [asset for asset in assets if asset["kind"] in {"photo", "video"} and asset.get("evidence_status", "unknown") == "site_photo"]
        scene_themes = {"stay": ["庄园环境与到达动线", "房间与公共空间", "已确认文化体验", "住宿咨询入口"],
                        "culture": ["庄园环境", "住宿空间", "所选文化资料对应物件/场景", "体验安排咨询"],
                        "woodcut": ["住宿空间", "木刻观察的线条/印痕（待拍提纲）", "所选文化资料对应细节", "住宿与文化安排咨询"]}[data.angle]
        visuals = ["任务「"+campaign["title"][:60]+"」："+scene_themes[index % 4]+"实拍；先核对是否与任务产品提纲相符" for index in range(len(spoken))]
        for index, plan in enumerate(selected_plans):
            visuals[index % len(visuals)] += "；创意/待拍参考「"+str(plan.get("title", ""))+"」："+str(plan.get("summary", ""))[:120]+"；仅本机目录方案，不确认现售包含项。体验提纲："+pack(plan.get("experience_items", []))[:240]
        storyboard = []
        for index, speech in enumerate(spoken):
            start, end = data.duration_seconds*index//len(spoken), data.duration_seconds*(index+1)//len(spoken)
            asset = visual_assets[index % len(visual_assets)] if visual_assets else None
            visual = visuals[index]
            if asset:
                visual += "；选用素材「"+asset["title"]+"」"+("（历史现场，需标注拍摄时期；不能代替当前交付证明）" if asset["evidence_status"] == "historical_photo" else "（现场归类为本地人工声明，需逐镜核对）")
            storyboard.append({"start_seconds": start, "end_seconds": end, "visual": visual, "voiceover": speech,
                               "asset_id": asset["id"] if asset else None, "capture_needed": asset is None})
        # Match each shot duration to the amount of speech rather than giving
        # a long opening and a short CTA the same number of seconds.
        weights = [max(1, len(shot["voiceover"])) for shot in storyboard]
        total_weight, elapsed, cursor = sum(weights), 0, 0
        for index, shot in enumerate(storyboard):
            elapsed += weights[index]
            end = data.duration_seconds if index == len(storyboard)-1 else min(data.duration_seconds-(len(storyboard)-index-1), max(cursor+1, round(data.duration_seconds*elapsed/total_weight)))
            shot["start_seconds"], shot["end_seconds"] = cursor, end
            cursor = end
        def st(seconds):
            return f"00:{seconds//60:02d}:{seconds%60:02d},000"
        srt = "\n\n".join(f"{i+1}\n{st(shot['start_seconds'])} --> {st(shot['end_seconds'])}\n{shot['voiceover']}" for i, shot in enumerate(storyboard))+"\n"
        missing = ["具体体验明细及套餐价待从本机现有记录核对，未知不等于产品不存在"] if not current_products else []
        blockers = []
        if not visual_assets:
            blockers.append("缺少当期现场庄园照片或视频素材，资料包可生产，发布前须补拍/上传；历史/概念/未知素材仅供参考")
        if data.angle in {"culture", "woodcut"} and not refs:
            blockers.append("文化内容尚未选择可用知识出处，仅可内部策划")
        if data.angle == "culture" and not current_products:
            blockers.append("当前体验交付明细待本机资料核对，不能对外承诺具体项目")
        if room_context:
            blockers.append('房态仅为来源预订观察，发布日期售卖信息前须核房并确认体验交付及报价')
            missing += ['真实房号及其他渠道/维修/自用占用待核', '房源30间与表列28间差额待核', '日期栏是否为住宿夜、退房边界待核']
        if workspace_context:
            missing += list(workspace_context['plan'].get('checks', []))[:12]
            missing = list(dict.fromkeys(missing))[:30]
        checklist = [reference_note, "任务受众、目标和产品提纲属于策划输入，逐项核对后才可对外使用。",
                     "木刻是文化内容支线，未核实时不得承诺为现售套餐包含项。", "历史实景须标注时期，概念图不得冒充庄园/房间现状。"]
        checklist += ["知识条目摘录〔"+ref["region_scope"]+"〕："+ref["excerpt"]+"；出处："+ref["source_title"]+"；定位："+ref["locator"]+"。区域资料不能推定严田村史。" for ref in refs]
        if room_context:
            checklist += ['内部日期依据：'+window_label+'，来源 '+room_context['source']['filename']+' Sheet1 单元格 '+', '.join(room_context['window']['source_cells'])+'；SHA-256 '+room_context['source']['sha256'],
                          '年份2026来自持有人“接下来11月和12月”的补充；0预订不自动等于可售，空白和未确认日期不能当作空房推广。',
                          '不公开同事表中的团体/联系人信息；不使用未核实的剩余房数、稀缺宣传或套餐价格。']
        if workspace_context:
            checklist += ['第一层运营方案：'+workspace_context['plan']['title']+'；版本 '+str(workspace_context['version'])+'；指纹 '+workspace_context['plan_hash']+'。确认仅采用策划方向，未核项继续保留。']
        materials = {"title": campaign["title"]+"｜"+angle, "hook": hook, "voiceover": "\n".join(spoken),
                     "storyboard": storyboard, "shot_list": ["受众策划假设："+campaign["audience"], "目标："+campaign["objective"], "产品待核提纲："+campaign["product_summary"], *visuals], "srt": srt,
                     "cover_text": campaign["title"][:60]+"｜严田住宿与文化体验", "image_prompt": "依据已上传且权利确认的真实庄园照片设计住宿内容封面；任务："+campaign["title"]+"。无实景时只做排版建议，不伪造庄园现状，不添加未证实非遗身份或套餐价格。",
                     "video_prompt": "按"+str(data.duration_seconds)+"秒分镜剪辑；任务受众提纲："+campaign["audience"]+"。只使用镜头对应、已授权的真实素材，缺镜头先补拍。概念图需明确标注；本工具未生成成片。",
                     "channel_copy": {"xiaohongshu": hook+"\n"+reference_note+"\n"+cta+"\n#严田住宿 #文化体验", "douyin": hook+"\n"+cta, "direct": "严田庄园住宿与文化体验咨询。"+reference_note+"\n"+cta},
                     "cta": cta, "claims": [{"text": "住宿+文化体验是现成产品；住宿获客为主，文化/木刻内容为支线", "basis": "用户当前确认", "scope": "经营方向，不确认具体体验包含项/套餐价"},
                                             {"text": "30间、淡季住宿380元参考", "basis": "用户陈述，待房表/账单核对", "scope": "住宿参考，不代表实时可售量或套餐报价"}], "missing_inputs": missing,
                     "task_brief": brief, "usage_checklist": checklist, "planning_references": planning_refs}
        if room_context:
            materials['claims'] = [materials['claims'][0], {'text': window_label+'的选定房型在来源表填写0预订', 'basis': room_context['source']['filename']+' / '+room_context['snapshot_id'], 'scope': '内部选题日期依据，非对外可售承诺；'+room_context['interpretation']}]
            public_cta = '评论或咨询入住日、离店日和人数，房型、文化体验与报价逐项确认。'
            materials['channel_copy'] = {'xiaohongshu': hook+'\n'+reference_note+'\n'+public_cta+'\n#严田住宿 #文化体验', 'douyin': hook+'\n'+reference_note+'\n'+public_cta, 'direct': hook+'\n'+reference_note+'\n'+public_cta}
        guard_claims(materials)
        return materials, blockers

    router = APIRouter(prefix=BASE_URL, tags=["本地获客内容生产资料"])

    @router.get("")
    async def snapshot(request: Request):
        assert_request_scope(request)
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            campaigns = [{**item, "metrics": [m for m in rows(conn, "metrics") if m["campaign_id"] == item["id"]], "attribution": attribution(conn, item)} for item in rows(conn, "campaigns")]
            return {"business_facts": business_facts(context), "local_context": context, "knowledge": knowledge,
                    "campaigns": campaigns, "assets": [asset_dto(item) for item in rows(conn, "assets")],
                    "packages": [package_dto(item, conn, knowledge, sources, context) for item in rows(conn, "packages")],
                    "reviews": rows(conn, "reviews"), "distributions": rows(conn, "distributions"), "metrics": rows(conn, "metrics"), "capabilities": CAPABILITIES}

    @router.post("/campaigns")
    async def add_campaign(request: Request):
        data = await body(request, CampaignInput)
        resolve_room_window(str(path), data.room_status_ref)
        resolve_workspace_plan(str(path), data.workspace_plan_ref)
        item = {**data.model_dump(exclude={"base_version"}), "id": uid("campaign"), "version": 1, "created_at": now(), "updated_at": now()}
        with transaction() as conn:
            conn.execute("INSERT INTO gr_source_codes VALUES (?,?)", (item["source_code"], item["id"]))
            insert(conn, "campaigns", item)
            conn.execute("INSERT INTO gr_campaign_versions VALUES (?,?,?)", (item["id"], 1, pack(item)))
        return item

    @router.put("/campaigns/{campaign_id}")
    async def update_campaign(campaign_id: str, request: Request):
        data = await body(request, CampaignInput)
        resolve_room_window(str(path), data.room_status_ref)
        resolve_workspace_plan(str(path), data.workspace_plan_ref)
        with transaction() as conn:
            old = get(conn, "campaigns", campaign_id)
            if data.base_version != old["version"]:
                fail("活动版本已变化，请刷新后编辑", 409)
            if data.source_code != old["source_code"]:
                fail("来源码绑定归因历史，创建后不能修改；请另建活动", 409)
            item = {**data.model_dump(exclude={"base_version"}), "id": campaign_id, "version": old["version"]+1, "created_at": old["created_at"], "updated_at": now()}
            conn.execute("UPDATE gr_campaigns SET data=? WHERE id=?", (pack(item), campaign_id))
            conn.execute("INSERT INTO gr_campaign_versions VALUES (?,?,?)", (campaign_id, item["version"], pack(item)))
            return item

    @router.post("/assets")
    async def upload_asset(request: Request):
        try:
            form = await request.form(max_files=1, max_fields=12, max_part_size=MAX_FILE)
        except Exception:
            fail("素材上传需合法multipart文件及字段")
        file = form.get("file")
        data = await file.read(MAX_FILE+1) if hasattr(file, "read") else b""
        await form.close()
        assert_request_scope(request, dict(form))
        allowed = {"file", "title", "kind", "rights_confirmed", "caption", "source_note", "evidence_status", "tenant_id", "site_id"}
        if set(form)-allowed:
            fail("上传包含未知字段")
        file = form.get("file")
        if not hasattr(file, "read"):
            fail("必须上传实际本地文件，不能注册一个文件名或URL")
        filename = getattr(file, "filename", "") or ""
        if not filename or len(filename) > 240 or "/" in filename or "\\" in filename or filename in {".", ".."}:
            fail("文件名不能含路径")
        kind, title = form.get("kind"), str(form.get("title", "")).strip()
        rights = str(form.get("rights_confirmed", "false")).lower()
        caption, source_note = str(form.get("caption", "")), str(form.get("source_note", ""))
        evidence_status = str(form.get("evidence_status", "unknown"))
        if evidence_status not in {"site_photo", "historical_photo", "generated_concept", "unknown"}:
            fail("素材现场来源归类不合法")
        if evidence_status in {"site_photo", "historical_photo"} and (not caption.strip() or not source_note.strip()):
            fail("现场/历史现场素材需填写画面说明和来源/拍摄时期；仍属于本地人工声明")
        if kind not in {"photo", "video", "reference"} or not 1 <= len(title) <= 160 or rights not in {"true", "false"} or len(caption) > 2000 or len(source_note) > 2000:
            fail("素材字段或使用权确认不合法")
        if not data or len(data) > MAX_FILE:
            fail("文件为空或超过100MiB限制")
        mime = getattr(file, "content_type", "")
        formats = [(b"\x89PNG\r\n\x1a\n", "png", "image/png"), (b"\xff\xd8\xff", "jpg", "image/jpeg"), (b"GIF8", "gif", "image/gif")]
        extension = None
        if kind == "photo":
            for magic, ext, expected in formats:
                if data.startswith(magic) and mime == expected:
                    extension = ext
            if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and mime == "image/webp":
                extension = "webp"
            if len(data) > 20*1024*1024:
                fail("照片超过20MiB限制")
        elif kind == "video" and len(data) >= 12 and data[4:8] == b"ftyp" and mime in {"video/mp4", "video/quicktime"}:
            extension = "mov" if mime == "video/quicktime" else "mp4"
        elif kind == "reference":
            if mime == "application/pdf" and data.startswith(b"%PDF-"):
                extension = "pdf"
            elif mime == "text/plain" and len(data) <= 1024*1024:
                try:
                    text = data.decode("utf-8")
                    if re.search(r"<\s*(?:html|svg|script|iframe|!doctype)", text, re.I):
                        fail("不接受HTML/SVG参考文件")
                    extension = "txt"
                except UnicodeError:
                    fail("文本参考必须为UTF-8")
        if extension is None or Path(filename).suffix.lower() not in {"."+extension, ".jpeg" if extension == "jpg" else "."+extension}:
            fail("文件扩展名、内容类型与实际文件签名不符；不接受SVG/HTML")
        storage_name = uuid.uuid4().hex+"."+extension
        target = asset_root/storage_name
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            if kind in {"photo", "video"}:
                if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
                    fail("缺少本地媒体校验工具，不能把未校验媒体登记为可用")
                probe = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-of", "json", str(target)], capture_output=True, timeout=20)
                streams = json.loads(probe.stdout or b"{}") .get("streams", [])
                visual = [stream for stream in streams if stream.get("codec_type") == "video" and 0 < stream.get("width", 0)*stream.get("height", 0) <= 40000000]
                if probe.returncode or not visual:
                    fail("文件无法作为真实图像/视频校验")
                decoded = subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(target), "-frames:v", "1", "-f", "null", "-"], capture_output=True, timeout=25)
                if decoded.returncode or decoded.stderr.strip():
                    fail("媒体首帧无法完整解码，不能登记为可用素材")
            if extension == "pdf":
                if not shutil.which("pdfinfo"):
                    fail("缺少本地PDF校验工具，不能登记未校验参考文件")
                checked = subprocess.run(["pdfinfo", str(target)], capture_output=True, timeout=15)
                if checked.returncode or not re.search(rb"Pages:\s*[1-9]", checked.stdout):
                    fail("PDF参考无法解析，不登记伪文件")
            item = {"id": uid("asset"), "title": title, "kind": kind, "rights_confirmed": rights == "true", "caption": caption,
                    "source_note": source_note, "evidence_status": evidence_status, "original_name": filename, "media_type": mime, "size_bytes": len(data),
                    "sha256": digest(data), "storage_name": storage_name, "created_at": now()}
            with transaction() as conn:
                insert(conn, "assets", item)
            return asset_dto(item)
        except (subprocess.SubprocessError, ValueError, OSError):
            target.unlink(missing_ok=True)
            fail("本地媒体校验或保存失败，未登记可用素材")
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @router.get("/assets/{asset_id}/file")
    async def asset_file(asset_id: str, request: Request):
        assert_request_scope(request)
        with transaction() as conn:
            asset = get(conn, "assets", asset_id)
        data, state = read_asset(asset)
        if state != "valid":
            fail("素材文件缺失、被替换或不再匹配登记哈希", 409)
        extension = asset["storage_name"].split(".")[-1]
        return Response(data, media_type=asset["media_type"] if asset["kind"] in {"photo", "video"} else "application/octet-stream",
                        headers={"Content-Disposition": f'inline; filename="growth-{asset_id}.{extension}"' if asset["kind"] in {"photo", "video"} else f'attachment; filename="growth-{asset_id}.{extension}"', "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})

    @router.post("/campaigns/{campaign_id}/compile")
    async def compile_package(campaign_id: str, request: Request):
        data = await body(request, CompileInput)
        knowledge, sources = await evidence()
        context = local_context()
        refs = knowledge_refs(data.knowledge_ids, knowledge, sources)
        with transaction() as conn:
            campaign = get(conn, "campaigns", campaign_id)
            if campaign["version"] != data.base_version:
                fail("活动版本已变化，请刷新后编译", 409)
            room_context = resolve_room_window(str(path), campaign.get('room_status_ref'))
            workspace_context = resolve_workspace_plan(str(path), campaign.get('workspace_plan_ref'))
            assets = [get(conn, "assets", item_id) for item_id in data.asset_ids]
            if any(read_asset(asset)[1] != "valid" for asset in assets):
                fail("选用素材文件缺失或哈希已变化", 409)
            asset_refs = [{key: asset[key] for key in ["id", "sha256", "kind", "title", "rights_confirmed", "evidence_status"]} for asset in assets]
            input_hash = digest({"compiler_version": COMPILER_VERSION, "campaign": campaign, "input": data.model_dump(), "knowledge_refs": refs, "assets": asset_refs, "context_hash": digest(context), 'room_status_context': room_context, 'workspace_plan_context': workspace_context})
            old = conn.execute("SELECT package_id FROM gr_compile_inputs WHERE hash=?", (input_hash,)).fetchone()
            if old:
                return package_dto(get(conn, "packages", old[0]), conn, knowledge, sources, context)
            materials, blockers = generate(campaign, data, refs, assets, context, room_context, workspace_context)
            version = 1+max([p["version"] for p in rows(conn, "packages") if p["campaign_id"] == campaign_id] or [0])
            item = {"id": uid("package"), "campaign_id": campaign_id, "campaign_version": campaign["version"], "version": version,
                    "parent_package_id": None, "compiler_version": COMPILER_VERSION, "contract": "yantian.growth-materials.v1", "status": "draft", "material_kind": "production_materials", "source_code": campaign["source_code"],
                    "angle": data.angle, "duration_seconds": data.duration_seconds, "knowledge_refs": refs, "asset_refs": asset_refs,
                    "context_hash": digest(context), 'room_status_context': room_context, 'workspace_plan_context':workspace_context, "production_blockers": blockers, "materials": materials, "provider_calls": [],
                    "external_side_effects": [], "created_at": now(), "input_hash": input_hash}
            item["hash"] = digest(item)
            insert(conn, "packages", item)
            conn.execute("INSERT INTO gr_compile_inputs VALUES (?,?)", (input_hash, item["id"]))
            return package_dto(item, conn, knowledge, sources, context)

    @router.put("/packages/{package_id}")
    async def edit_package(package_id: str, request: Request):
        data = await body(request, EditInput)
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            old = get(conn, "packages", package_id)
            latest = max(p["version"] for p in rows(conn, "packages") if p["campaign_id"] == old["campaign_id"])
            if old["hash"] != data.base_hash or old["version"] != latest:
                fail("稿包已存在新版本或hash不匹配，请刷新后编辑", 409)
            materials = data.materials.model_dump()
            materials["claims"], materials["missing_inputs"] = old["materials"]["claims"], old["materials"]["missing_inputs"]
            materials["task_brief"] = old["materials"].get("task_brief", {})
            materials["usage_checklist"] = old["materials"].get("usage_checklist", [])
            materials["planning_references"] = old["materials"].get("planning_references", [])
            known_ids = {ref["id"] for ref in old["asset_refs"]}
            if any(shot["start_seconds"] >= shot["end_seconds"] or shot["end_seconds"] > old["duration_seconds"] or (shot["asset_id"] and shot["asset_id"] not in known_ids) for shot in materials["storyboard"]):
                fail("分镜时间或素材引用不合法")
            asset_index = {ref["id"]: ref for ref in old["asset_refs"]}
            for shot in materials["storyboard"]:
                ref = asset_index.get(shot["asset_id"])
                if ref and ref.get("evidence_status") != "site_photo":
                    if not shot["capture_needed"] or not any(label in shot["visual"] for label in ["历史", "概念", "参考", "未知"]):
                        fail("历史/概念/未知素材只能作为标明来源的参考镜头，须保留当期补拍状态")
                if not shot["asset_id"] and not shot["capture_needed"]:
                    fail("无现场素材的分镜须标为待拍")
            shots = materials["storyboard"]
            if shots[0]["start_seconds"] != 0 or shots[-1]["end_seconds"] != old["duration_seconds"] or any(a["end_seconds"] != b["start_seconds"] for a, b in zip(shots, shots[1:])):
                fail("分镜须按顺序连续覆盖完整时长，不能重叠或留空")
            expected_voice = "\n".join(shot["voiceover"] for shot in shots)
            def timecode(second):
                return f"00:{second//60:02d}:{second%60:02d},000"
            expected_srt = "\n\n".join(f"{i+1}\n{timecode(shot['start_seconds'])} --> {timecode(shot['end_seconds'])}\n{shot['voiceover']}" for i, shot in enumerate(shots))+"\n"
            if materials["voiceover"].strip() != expected_voice.strip() or materials["srt"].strip() != expected_srt.strip():
                fail("口播与字幕须和分镜台词、时间逐字一致，请同步后保存")
            if any(len(value) > 4000 for value in materials.get("task_brief", {}).values()):
                fail("任务提纲字段过长")
            guard_claims(materials)
            item = {**old, "id": uid("package"), "parent_package_id": old["id"], "version": latest+1,
                    "materials": materials, "status": "draft", "created_at": now(), "input_hash": None}
            item.pop("hash", None)
            item["hash"] = digest(item)
            insert(conn, "packages", item)
            return package_dto(item, conn, knowledge, sources, context)

    @router.post("/packages/{package_id}/reviews")
    async def review_package(package_id: str, request: Request):
        data = await body(request, ReviewInput)
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            item = get(conn, "packages", package_id)
            if data.package_hash != item["hash"]:
                fail("审阅hash与不可变稿包不一致", 409)
            if data.decision == "approve":
                if not all(data.confirmations.model_dump().values()):
                    fail("批准资料包需要事实、权利和交付三项人工确认")
                if approval_blockers(blockers_for(item, conn, knowledge, sources, context)):
                    fail("活动、证据或实际素材已变化/权利未确认，请重新编译", 409)
                guard_claims(item["materials"])
            review = {**data.model_dump(), "id": uid("review"), "package_id": package_id,
                      "review_kind": "local_operator_declaration", "identity_verified": False, "created_at": now()}
            insert(conn, "reviews", review)
            return {"review": review, "package": package_dto(item, conn, knowledge, sources, context)}

    @router.post("/packages/{package_id}/distributions")
    async def register_distribution(package_id: str, request: Request):
        data = await body(request, DistributionInput)
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            item = get(conn, "packages", package_id)
            state = package_dto(item, conn, knowledge, sources, context)
            if item["hash"] != data.package_hash or not state["distribution_ready"]:
                fail("仅精确hash已批准、证据/素材有效且无阻塞的资料包可登记外部发布声明", 409)
            if not any(ref["kind"] in {"photo", "video"} and ref.get("evidence_status") == "site_photo" for ref in item["asset_refs"]):
                fail("缺少实际照片/视频素材，不能登记发布", 409)
            for old in rows(conn, "distributions"):
                if old["package_id"] == package_id and all(old[key] == value for key, value in data.model_dump().items()):
                    return old
            return insert(conn, "distributions", {**data.model_dump(), "id": uid("distribution"), "package_id": package_id,
                          "verification": "operator_declared_unverified", "actual_publication_performed": False, "created_at": now()})

    @router.post("/campaigns/{campaign_id}/metrics")
    async def register_metrics(campaign_id: str, request: Request):
        data = await body(request, MetricInput)
        if data.period_end < data.period_start:
            fail("指标周期结束日不能早于开始日")
        with transaction() as conn:
            get(conn, "campaigns", campaign_id)
            key = digest([campaign_id, data.channel_id, data.period_start, data.period_end])
            old = conn.execute("SELECT metric_id FROM gr_metric_periods WHERE key=?", (key,)).fetchone()
            if old:
                previous = get(conn, "metrics", old[0])
                item = {**data.model_dump(), "id": previous["id"], "campaign_id": campaign_id, "created_at": previous["created_at"], "updated_at": now()}
                conn.execute("UPDATE gr_metrics SET data=? WHERE id=?", (pack(item), item["id"]))
            else:
                item = {**data.model_dump(), "id": uid("metric"), "campaign_id": campaign_id, "created_at": now(), "updated_at": now()}
                insert(conn, "metrics", item)
                conn.execute("INSERT INTO gr_metric_periods VALUES (?,?)", (key, item["id"]))
            return item

    @router.get("/packages/{package_id}/export")
    async def export_package(package_id: str, request: Request):
        assert_request_scope(request)
        knowledge, sources = await evidence()
        context = local_context()
        with transaction() as conn:
            item = get(conn, "packages", package_id)
            state = package_dto(item, conn, knowledge, sources, context)
            package_reviews = [r for r in rows(conn, "reviews") if r["package_id"] == package_id]
        materials = item["materials"]
        marker = "已本地审阅资料（不是成片/已发布证明）" if state["approval_valid"] else "未审或已失效草稿：不得冒充可发布成片"
        readme = marker+"\n\n本ZIP是可执行生产资料包：脚本、分镜、字幕、拍摄及提示词。没有调用模型、生成成片或发布。\n380元仅住宿参考，不是组合套餐报价。人工发布声明未独立核验。\n\n阻塞项：\n"+"\n".join(state["blockers"])
        output = io.BytesIO()
        csv_buffer = io.StringIO(newline="")
        writer = csv.DictWriter(csv_buffer, fieldnames=["start_seconds", "end_seconds", "visual", "voiceover", "asset_id", "capture_needed"])
        writer.writeheader()
        writer.writerows(materials["storyboard"])
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            files = {"README.txt": readme, "manifest.json": json.dumps({"package": item, "current_state": {key: state[key] for key in ["review_status", "approval_valid", "distribution_ready", "blockers"]}, "reviews": package_reviews}, ensure_ascii=False, indent=2),
                     "脚本.md": "# "+materials["title"]+"\n\n"+marker+"\n\n"+materials["voiceover"]+"\n\n## 任务提纲（策划输入）\n"+json.dumps(materials.get("task_brief", {}), ensure_ascii=False, indent=2)+"\n\n## 核对清单与出处\n"+"\n".join(materials.get("usage_checklist", [])),
                     "分镜.csv": "\ufeff"+csv_buffer.getvalue(), "字幕.srt": materials["srt"],
                     "拍摄清单.txt": "\n".join(materials["shot_list"]),
                     "出处与使用清单.md": "\n\n".join(materials.get("usage_checklist", [])),
                     "任务简报.json": json.dumps(materials.get("task_brief", {}), ensure_ascii=False, indent=2),
                     "提示词.txt": "图片提示词：\n"+materials["image_prompt"]+"\n\n视频提示词：\n"+materials["video_prompt"],
                     "渠道文案.md": marker+"\n\n"+"\n\n".join("## "+channel+"\n"+text for channel, text in materials["channel_copy"].items())}
            for filename, content in files.items():
                archive.writestr(filename, content)
        return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="yantian-growth-{package_id}.zip"', "X-Content-Type-Options": "nosniff"})

    @router.post("/providers/jobs")
    @router.post("/publish")
    async def disabled(request: Request):
        fail("本地版未连接外部模型或发布服务；本地待审成片须从当前脚本分镜确认后明确生成", 423)

    from .render_jobs import create_render_router
    router.include_router(create_render_router(str(path), render_snapshot, prefix=""))
    return router
