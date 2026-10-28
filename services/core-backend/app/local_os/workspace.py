"""Layer one: local operating proposals, separate from video and sales facts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .bridge import assert_request_scope
from .room_status import read_room_status_snapshot

BASE = "/api/local-os/workspace"
COMPILER_VERSION = "yantian-operating-plan.local.v1.1"
MAX_FILE = 10*1024*1024
SAFE_ID = r"^[A-Za-z0-9_-]{1,160}$"
EXTENSIONS = {"jpg", "jpeg", "png", "webp", "txt", "md", "csv", "xlsx", "docx", "pdf"}


def _pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(value if isinstance(value, bytes) else _pack(value).encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fail(message, status=422):
    raise HTTPException(status, message)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)


class RoomRef(Input):
    snapshot_id: str = Field(pattern=SAFE_ID)
    opportunity_id: str = Field(pattern=SAFE_ID)


class PlanInput(Input):
    brief: str = Field(default="", max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=12)
    room_status_ref: RoomRef | None = None
    base_plan_id: str | None = Field(default=None, pattern=SAFE_ID)

    @model_validator(mode="after")
    def valid_input(self):
        if not self.brief and not self.attachment_ids:
            raise ValueError("text or attachment required")
        if len(set(self.attachment_ids)) != len(self.attachment_ids) or any(not re.fullmatch(SAFE_ID, value) for value in self.attachment_ids):
            raise ValueError("invalid attachment IDs")
        if any(ord(char) < 32 and char not in "\n\r\t" for char in self.brief):
            raise ValueError("control character")
        return self


class HashInput(Input):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


async def _body(request, model):
    raw_bytes = await request.body()
    if len(raw_bytes) > 64*1024:
        _fail("操作输入过大", 413)
    try:
        value = json.loads(raw_bytes)
        if not isinstance(value, dict):
            raise ValueError
        assert_request_scope(request, value)
        value = {key: item for key, item in value.items() if key not in {"tenant", "tenant_id", "site", "site_id"}}
        return model.model_validate(value)
    except (ValueError, UnicodeError, ValidationError):
        _fail("请检查输入、附件编号和方案版本；不接受额外原始资料字段")


def _scrub_brief(text):
    """Keep the instruction while removing labeled private-record lines/contacts."""
    lines = []
    for line in text.splitlines():
        if re.search(r"(?:姓名|客人|客户姓名|联系人|身份证|团队名称|团体名称|公司名称|机构名称|手机号|电话|微信|邮箱)\s*[:：]", line):
            lines.append("[私人记录已省略]")
            continue
        line = re.sub(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[联系方式已省略]", line)
        # Date instructions are not contact numbers. Protect only valid dates,
        # then redact other long digit sequences without copying record lines.
        dates = []
        def protect(match):
            try:
                date.fromisoformat(match.group(0))
            except ValueError:
                return match.group(0)
            dates.append(match.group(0))
            return "〔日期"+chr(65+len(dates)-1)+"〕"
        line = re.sub(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", protect, line)
        line = re.sub(r"(?<!\d)\+?\d[\d -]{6,}\d(?!\d)", "[连续号码已省略]", line)
        for index, value in enumerate(dates):
            line = line.replace("〔日期"+chr(65+index)+"〕", value)
        lines.append(line)
    return "\n".join(lines).strip()


def _ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True, timeout=15)


def _table_exists(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _json_row(conn, table, item_id):
    if table not in {"ws_plans", "ws_attachments", "ws_video_handoffs"}:
        raise ValueError("internal table")
    row = conn.execute(f"SELECT data FROM {table} WHERE id=?", (item_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _attachment_bytes(db_path, item):
    root = Path(db_path).resolve().parent/"workspace-attachments"
    name = item.get("storage_name", "")
    if root.is_symlink() or not re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|jpeg|png|webp|txt|md|csv|xlsx|docx|pdf)", name):
        return None
    target = root/name
    if target.is_symlink():
        return None
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            value = handle.read(MAX_FILE+1)
        if len(value) != item["size_bytes"] or _hash(value) != item["sha256"]:
            return None
        return value
    except (OSError, ValueError):
        return None


def _attachment_dto(db_path, item):
    valid = _attachment_bytes(db_path, item) is not None
    value = {key: content for key, content in item.items() if key != "storage_name"}
    value["integrity_state"] = "valid" if valid else "missing_or_changed"
    if item["kind"] == "photo" and valid:
        value["preview_url"] = BASE+"/attachments/"+item["id"]+"/file"
    return value


def _context(db_path, attachments, room_ref=None):
    from .growth import read_local_context, resolve_room_window
    local = read_local_context(db_path)
    snapshot = read_room_status_snapshot(db_path)
    resolved = resolve_room_window(db_path, room_ref) if room_ref else None
    refs = [{"id": item["id"], "sha256": item["sha256"], "kind": item["kind"], "read_status": item["read_status"],
             "topics": item["topics"], "date_hints": item["date_hints"]} for item in attachments]
    source_context = {"compiler_version": COMPILER_VERSION, "local_context_hash": _hash(local),
                      "room_snapshot_id": snapshot["id"] if snapshot else None,
                      "room_snapshot_hash": _hash(snapshot) if snapshot else None,
                      "room_status_ref": room_ref, "attachment_refs": sorted(refs, key=lambda item: item["id"])}
    return local, snapshot, resolved, source_context


def read_workspace_plan(db_path, plan_id):
    """Read a plan with current confirmation/source gates; never create tables."""
    path = Path(db_path).resolve()
    if not path.is_file():
        return None
    try:
        with _ro(path) as conn:
            if not _table_exists(conn, "ws_plans"):
                return None
            item = _json_row(conn, "ws_plans", plan_id)
            if not item:
                return None
            latest = conn.execute("SELECT MAX(version) FROM ws_plans WHERE family_id=?", (item["family_id"],)).fetchone()[0]
            confirmation = conn.execute("SELECT data FROM ws_confirmations WHERE plan_id=? AND plan_hash=?", (plan_id, item["hash"])).fetchone()
            attachments = [_json_row(conn, "ws_attachments", asset_id) for asset_id in item["request"]["attachment_ids"]]
        blockers = []
        intact = all(value is not None and _attachment_bytes(path, value) is not None for value in attachments)
        if not intact:
            blockers.append("附件已缺失或哈希变化，请重新生成方案")
        try:
            _, _, _, context = _context(str(path), [value for value in attachments if value], item["source_context"].get("room_status_ref"))
            stale = context != item["source_context"]
        except (HTTPException, ValueError, OSError):
            stale = True
        if stale:
            blockers.append("本机配置或房态来源已变化，请使用最新资料重新生成方案")
        expected = _hash({key: value for key, value in item.items() if key != "hash"})
        if expected != item["hash"]:
            blockers.append("方案内容与保存哈希不一致")
        superseded = latest != item["version"]
        if superseded:
            blockers.append("方案已有新版本，旧版仅供历史查阅")
        confirmed = bool(confirmation)
        return {**item, "status": "confirmed" if confirmed else "draft", "source_stale": stale or not intact,
                "superseded": superseded, "confirmation_valid": confirmed and not blockers,
                "confirmation": json.loads(confirmation[0]) if confirmation else None, "blockers": blockers}
    except (sqlite3.Error, ValueError, KeyError, OSError):
        return None


def _source_refs(candidate):
    return [{"title": str(ref.get("title", "本机CREATE目录")), "locator": str(ref.get("locator", "")),
             "evidence_state": str(ref.get("evidence_state") or ref.get("evidence_status") or "local_config_reference")}
            for ref in candidate.get("source_refs", []) if isinstance(ref, dict)]


def _select_routes(local, brief, attachments):
    routes = {item["id"]: item for item in local.get("products", []) if isinstance(item, dict) and re.fullmatch(r"R0[1-8]", str(item.get("id", "")))}
    text = brief+" "+" ".join(topic for item in attachments for topic in item["topics"])
    matches = []
    for pattern, route in [(r"木刻|版画|徽派|院落|古建|窗纹", "R03"), (r"纸伞|陶瓷|陶艺|瓷器", "R04"),
                           (r"婺剧|戏曲|雨天", "R05"), (r"农事|农场|餐桌", "R02"), (r"自然|花园|叶片|生态", "R01")]:
        match = re.search(pattern, text)
        if match:
            matches.append((match.start(), route))
    selected = list(dict.fromkeys(route for _, route in sorted(matches)))[:2] or ["R01", "R03"]
    return [routes[route] for route in selected if route in routes]


def _requested_dates(brief, attachments, snapshot):
    """Only valid date clues; a missing year uses the explicit source resolution."""
    year = (snapshot or {}).get("period_resolution", {}).get("resolved_year")
    values = []
    text = brief+" "+" ".join(hint for item in attachments for hint in item["date_hints"])
    for match in re.finditer(r"(?<!\d)(?:(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)|(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})[日号]?)", text):
        parts = match.groups()
        try:
            resolved = date(int(parts[0] or parts[3] or year), int(parts[1] or parts[4]), int(parts[2] or parts[5])).isoformat()
        except (ValueError, TypeError):
            continue
        if resolved not in values:
            values.append(resolved)
        if len(values) == 8:
            break
    return sorted(values)


def _matching_room_ref(brief, attachments, snapshot):
    targets = _requested_dates(brief, attachments, snapshot)
    if not targets or not snapshot:
        return None
    for window in snapshot.get("opportunities", []):
        # A king-only zero window cannot clear unknown twin-room observations.
        if window["kind"] != "ALL_TYPES_ZERO" and "大床" not in brief:
            continue
        if window["start_date"] <= targets[0] <= targets[-1] <= window["end_date"]:
            return {"snapshot_id": snapshot["id"], "opportunity_id": window["id"]}
    return None


def _date_focus(snapshot, resolved, targets):
    if resolved:
        window = resolved["window"]
        target = "意向日期"+"、".join(targets)+"；" if targets else ""
        return target+"来源候选"+window["start_date"]+"至"+window["end_date"]+"（"+"、".join(window["room_types"])+"原表记0；先核房，非可售承诺）"
    if targets:
        return "用户/附件意向日期："+"、".join(targets)+"；未匹配到适用的来源0窗口，日期供给待核，不推断空房。"
    if snapshot and snapshot.get("opportunities"):
        windows = [item for item in snapshot["opportunities"] if item["kind"] == "ALL_TYPES_ZERO"] or snapshot["opportunities"][:2]
        return "优先核对来源日期："+"、".join(item["start_date"]+("至"+item["end_date"] if item["end_date"] != item["start_date"] else "") for item in windows)+"；填0不代表可售，空白和未确认预订保持未知。"
    return "尚无可用于日期推广的来源窗口；按实际房态核对，不生成空房或销量。"


def _generate(brief, attachments, local, snapshot, resolved):
    selected = _select_routes(local, brief, attachments)
    candidates = [{"id": item["id"], "title": item["title"], "positioning": item.get("summary", "本机CREATE体验方向"),
                   "status": item.get("status", "LOCAL_IMPLEMENTED_CATALOG"),
                   "checklist": list(item.get("conditions", []))+["与实际接待方核对本次是否可安排、材料与交付；目录不等于当前套餐已包含。"],
                   "source_refs": _source_refs(item)} for item in selected]
    attachment_topics = sorted({topic for item in attachments for topic in item["topics"]})
    topic_note = "、".join(item["title"] for item in candidates) or "待核对的CREATE文化体验"
    targets = _requested_dates(brief, attachments, snapshot)
    audience_rules = [
        (r"亲子|孩子|小朋友|家庭", "亲子家庭", "围绕同行儿童年龄、材料安全与轻松停留节奏核对住宿及体验安排。"),
        (r"情侣|夫妻|二人|两个人", "情侣或两人同行", "围绕安静住宿、共同创作与行程节奏验证两人体验需求。"),
        (r"朋友|闺蜜|好友|同学", "朋友同行小组", "围绕共同手作、同行人数与可带走成果核对小组安排。"),
        (r"团建|团队|研学|公司", "团队或研学小组", "优先核对分组、场次容量、带队职责和接待资源，不能由目录推定可接团。"),
    ]
    audiences = [{"name": name, "rationale": rationale+"属于策划假设，需以实际咨询验证。", "state": "hypothesis"}
                 for pattern, name, rationale in audience_rules if re.search(pattern, brief)][:2]
    if not audiences:
        audiences = [{"name": "希望慢住并了解文化体验的同行小组", "rationale": "住宿与可选手作可组合安排行程；客群属于策划假设，需以实际咨询验证。", "state": "hypothesis"}]
    audience_note = "、".join(item["name"] for item in audiences)
    channel_templates = [
        (r"小红书", {"id": "xiaohongshu", "title": "小红书", "role": "围绕住哪里、如何安排体验解决出行问题", "actions": ["整理真实住宿与所选体验图文素材", "准备有出处的图文提纲和核房咨询入口"], "readiness": "账号、门店与允许的经营入口待核；不代表已开通或已发布"}),
        (r"抖音|短视频", {"id": "douyin", "title": "抖音", "role": "展示到店、房间与真实体验过程", "actions": ["先列现场拍摄需求", "确认方案后另交视频脚本层"], "readiness": "未自动连接平台、生成成片或发布"}),
        (r"视频号|微信|朋友圈|公众号", {"id": "wechat", "title": "微信内容与咨询", "role": "向已有关注者解释日期与体验安排", "actions": ["准备住宿和所选体验说明", "人工核对可用账号与咨询承接方式"], "readiness": "微信渠道接入、发布与触达均未执行"}),
        (r"独立站|官网|直接咨询", {"id": "direct", "title": "独立站咨询", "role": "承接日期、人数与体验意向", "actions": ["保留来源码", "核房后人工确认房型、体验与报价"], "readiness": "当前本地咨询预览；不自动锁房或收款"}),
    ]
    requested_channels = [item for pattern, item in channel_templates if re.search(pattern, brief)]
    channels = requested_channels or [channel_templates[0][1], channel_templates[1][1]]
    if not any(item["id"] == "direct" for item in channels):
        channels.append(channel_templates[-1][1])
    intent = "面向"+audience_note+"，围绕"+topic_note+"推广住宿与可选体验"
    date_focus = _date_focus(snapshot, resolved, targets)
    checks = ["先核对实际房型、逐房库存、维修/自用和其他渠道占用。", "住宿＋文化体验为现成产品方向；本次套餐包含项、场次、人数、材料和交付仍须逐项确认。",
              "380元只作用户此前提供的淡季住宿参考，不是本方案套餐报价；历史测算价格不带入销售承诺。",
              "图片只提供上传参考或OCR文字线索；没有完成视觉理解，不据照片脑补房间、设施、场地、供给或文化身份。",
              "核对现场素材与发布使用权；历史照片、概念图和当前实拍分别标明。"]
    if snapshot:
        checks += [issue["message"] for issue in snapshot.get("issues", [])]
    else:
        checks.append("尚无已导入的脱敏房态来源，不能把缺数据理解为空房。")
    if not candidates:
        checks.append("本机CREATE目录暂不可读；保留体验策划候选，不补造课程。")
    if targets and not resolved:
        checks.append("意向日期未匹配适用的来源0窗口；空白、预订未确认与来源未覆盖均不得当作空房。")
    if resolved and targets and not all(resolved["window"]["start_date"] <= value <= resolved["window"]["end_date"] for value in targets):
        checks.append("文字意向日期与选定来源窗口不完全一致，请先核对推广日期；不能将窗口外日期视为记0。")
    for item in attachments:
        checks += ["附件「"+item["name"]+"」："+warning for warning in item["warnings"]]
    sources = [{"kind": "owner_statement", "title": "用户此前经营陈述", "locator": "庄园住宿＋文化体验产品方向", "evidence_state": "user_confirmed_scope_not_current_inventory"}]
    for candidate in candidates:
        sources += [{"kind": "create_catalog", **ref} for ref in candidate["source_refs"]]
    for item in attachments:
        sources.append({"kind": "attachment", "title": item["name"], "locator": "sha256:"+item["sha256"], "evidence_state": "sanitized_topic_and_date_clues_only"})
    if snapshot:
        sources.append({"kind": "room_status", "title": snapshot["source"]["filename"], "locator": snapshot["id"]+" / "+snapshot["source"]["range"], "evidence_state": "source_observation_not_sellable_inventory"})
    if resolved:
        sources.append({"kind": "room_window", "title": "所选日期的原表房型格", "locator": snapshot["id"]+" / "+", ".join(resolved["window"]["source_cells"]), "evidence_state": "source_zero_requires_room_verification"})
    return {
        "title": "严田"+audience_note+"住宿与"+("、".join(item["title"] for item in candidates) or "CREATE体验")+"运营方案",
        "intent_summary": intent,
        "one_line_strategy": intent+"；先通过"+"、".join(item["title"] for item in channels)+"收集日期意向并核房，确认方向后再独立交接视频资料。",
        "objective": "收集"+audience_note+"的入住/离店日期、同行人数与"+topic_note+"意向，完成核房和人工报价；不预填销量、入住率或收入。",
        "date_focus": date_focus,
        "audiences": audiences,
        "offering": {"stay_statement": "严田庄园住宿＋文化体验为用户确认的现成产品方向；具体房型与本次包含项目按日期、人数核对。",
                     "experience_candidates": candidates,
                     "price_note": "本方案不设现售套餐价。380元仅为此前淡季住宿参考；CREATE旧模型金额为假设，交通、门票、材料与后续工艺另核。"},
        "channels": channels,
        "actions": [
            {"step": 1, "title": "核对日期与库存", "description": date_focus+" 对照逐房库存，保留空白、粉黄标记和容量差异。", "owner": "经营负责人", "completion_evidence": "有日期、房型、库存来源及人工核房记录"},
            {"step": 2, "title": "确认本次住宿与体验组合", "description": "为"+audience_note+"逐项核对"+topic_note+"；只选一到两项，不把目录全部堆成套餐。", "owner": "接待与体验负责人", "completion_evidence": "明确包含项、时长、场次、容量、材料和交付条件"},
            {"step": 3, "title": "整理现场与文化依据", "description": "补真实房型、公共空间和体验过程素材；概念图保持概念身份。", "owner": "内容负责人", "completion_evidence": "素材来源、日期、使用权及文化引用可追溯"},
            {"step": 4, "title": "确认运营方案方向", "description": "采用此精确版本的策划方向；待核清单仍待核，不自动确认供给或价格。", "owner": "经营负责人", "completion_evidence": "独立的方案确认记录"},
            {"step": 5, "title": "另行交给视频脚本层", "description": "明确点击交接，建立任务；视频层再选择时长、素材、脚本和审阅。", "owner": "内容负责人", "completion_evidence": "绑定方案哈希的视频任务引用，不等于已生成脚本或成片"},
            {"step": 6, "title": "跟进咨询并复盘", "description": "跟进"+"、".join(item["title"] for item in channels)+"的"+audience_note+"咨询，按来源码读取原经营台账；真实指标另登记，未知不填0。", "owner": "运营负责人", "completion_evidence": "咨询、核房、报价、订单及人工收款分别留痕"},
        ],
        "materials_needed": ["真实客房与公共空间当期照片", "所选体验的实际材料、过程与可带走成果", "文化出处与现场接待说明", "各渠道允许的咨询入口与来源码"],
        "checks": list(dict.fromkeys(checks)), "sources": sources,
        "assumptions": ["目标受众与渠道作用属于待验证的策划假设。", "附件线索不构成供给、价格、订单、可售库存或文化史实证明。", "本方案由本地规则结合既有资料编排，未调用外部模型。"]+
                       (["附件文字提示的主题为："+"、".join(attachment_topics)+"；仅用于挑选候选。"] if attachment_topics else []),
    }


def create_workspace_router(db_path, culture_service=None):
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = path.parent/"workspace-attachments"
    if root.is_symlink():
        raise ValueError("workspace attachment directory must not be a symlink")
    root.mkdir(exist_ok=True, mode=0o700)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ws_attachments(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL UNIQUE,data TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS ws_plans(id TEXT PRIMARY KEY,family_id TEXT NOT NULL,version INTEGER NOT NULL,input_hash TEXT NOT NULL UNIQUE,data TEXT NOT NULL,UNIQUE(family_id,version))")
        conn.execute("CREATE TABLE IF NOT EXISTS ws_confirmations(plan_id TEXT PRIMARY KEY,plan_hash TEXT NOT NULL,data TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS ws_video_handoffs(id TEXT PRIMARY KEY,plan_id TEXT NOT NULL UNIQUE,data TEXT NOT NULL)")

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
            _fail("本地方案记录冲突，请刷新后重试", 409)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def current_plan(plan_id, plan_hash=None):
        item = read_workspace_plan(path, plan_id)
        if not item:
            _fail("方案不存在", 404)
        if plan_hash is not None and item["hash"] != plan_hash:
            _fail("方案哈希不匹配，请读取当前版本", 409)
        if item["source_stale"] or item["superseded"] or item["blockers"]:
            _fail("方案版本或来源已变化，请重新生成并确认当前方案", 409)
        return item

    router = APIRouter(prefix=BASE, tags=["第一层操作空间"])

    @router.get("")
    async def snapshot(request: Request):
        assert_request_scope(request)
        from .growth import read_local_context
        local = read_local_context(str(path))
        with _ro(path) as conn:
            ids = [row[0] for row in conn.execute("SELECT id FROM ws_plans ORDER BY rowid DESC")]
            attachments = [json.loads(row[0]) for row in conn.execute("SELECT data FROM ws_attachments ORDER BY rowid DESC")]
        return {"plans": [value for plan_id in ids if (value := read_workspace_plan(path, plan_id))],
                "attachments": [_attachment_dto(path, value) for value in attachments],
                "reference_summary": {"create_routes": [item for item in local.get("products", []) if re.fullmatch(r"R0[1-8]", str(item.get("id", "")))],
                                      "room_status": read_room_status_snapshot(path), "context_hash": _hash(local),
                                      "input_boundary": "照片未作视觉理解；附件只保留脱敏主题/日期线索；方案不等于现售商品或视频脚本。"}}

    @router.post("/attachments")
    async def upload_attachment(request: Request):
        form = None
        try:
            # Starlette's multipart max_part_size does not bound file parts.
            # Bound the whole request before its parser can spool a huge file.
            chunks, body_size = [], 0
            async for chunk in request.stream():
                body_size += len(chunk)
                if body_size > MAX_FILE+64*1024:
                    _fail("附件超过10MiB或multipart包装过大", 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
            form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_FILE)
            assert_request_scope(request, dict(form))
            if set(form)-{"file", "tenant_id", "site_id"}:
                _fail("仅接受文件与固定范围，不接受原始身份/备注字段")
            file = form.get("file")
            if not hasattr(file, "read"):
                _fail("请上传本地文件")
            filename, media_type = file.filename or "", file.content_type or ""
            data = await file.read(MAX_FILE+1)
        except HTTPException:
            raise
        except Exception:
            _fail("附件需使用合法multipart文件")
        finally:
            if form is not None:
                await form.close()
        extension = Path(filename).suffix.lower().lstrip(".")
        if not filename or filename != filename.strip() or len(filename) > 240 or any(char in filename for char in ["/", "\\", ":"]) or any(ord(char) < 32 for char in filename) or extension not in EXTENSIONS:
            _fail("文件名或类型不支持，不接受路径、HTML、SVG或宏文档")
        if not data or len(data) > MAX_FILE:
            _fail("附件为空或超过10MiB", 413)
        content_hash = _hash(data)
        with _ro(path) as conn:
            old = conn.execute("SELECT data FROM ws_attachments WHERE sha256=?", (content_hash,)).fetchone()
        if old:
            old = json.loads(old[0])
            normalized_mime = media_type.partition(";")[0].strip().lower()
            equivalent_extensions = {"jpg", "jpeg"} if extension in {"jpg", "jpeg"} else {extension}
            if old["media_type"] != normalized_mime or old["storage_name"].rsplit(".", 1)[-1] not in equivalent_extensions or _attachment_bytes(path, old) is None:
                _fail("同一附件的类型或保存内容不一致", 409)
            return _attachment_dto(path, old)
        storage_name = uuid.uuid4().hex+"."+extension
        target = root/storage_name
        try:
            if root.is_symlink() or not root.is_dir():
                _fail("附件目录已变化，拒绝写入", 409)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            from .workspace_extract import inspect_attachment
            result = inspect_attachment(data, filename, media_type, target)
            item = {key: value for key, value in result.items() if key != "extension"}
            item.update(id="wsa-"+uuid.uuid4().hex, name=("照片-" if result["kind"] == "photo" else "附件-")+content_hash[:8]+"."+extension,
                        size_bytes=len(data), sha256=content_hash, storage_name=storage_name, created_at=_now())
            with transaction() as conn:
                existing = conn.execute("SELECT data FROM ws_attachments WHERE sha256=?", (content_hash,)).fetchone()
                if existing:
                    target.unlink(missing_ok=True)
                    item = json.loads(existing[0])
                else:
                    conn.execute("INSERT INTO ws_attachments VALUES (?,?,?)", (item["id"], content_hash, _pack(item)))
            return _attachment_dto(path, item)
        except ValueError:
            target.unlink(missing_ok=True)
            _fail("附件签名、内容、压缩结构或安全检查未通过；未保存可用附件")
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @router.get("/attachments/{attachment_id}/file")
    async def attachment_file(attachment_id: str, request: Request):
        assert_request_scope(request)
        if request.headers.get("sec-fetch-site") == "cross-site" or (culture_service and not culture_service.origin_allowed(request)):
            _fail("附件只供本地同源读取", 403)
        with _ro(path) as conn:
            item = _json_row(conn, "ws_attachments", attachment_id)
        if not item:
            _fail("附件不存在", 404)
        value = _attachment_bytes(path, item)
        if value is None:
            _fail("附件已缺失或哈希变化", 409)
        disposition = "inline" if item["kind"] == "photo" else "attachment"
        extension = item["storage_name"].split(".")[-1]
        return Response(value, media_type=item["media_type"] if item["kind"] == "photo" else "application/octet-stream",
                        headers={"Content-Disposition": f'{disposition}; filename="workspace-{attachment_id}.{extension}"',
                                 "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})

    @router.post("/plans")
    async def create_plan(request: Request):
        data = await _body(request, PlanInput)
        brief = _scrub_brief(data.brief)
        with _ro(path) as conn:
            attachments = [_json_row(conn, "ws_attachments", asset_id) for asset_id in data.attachment_ids]
        if any(item is None or _attachment_bytes(path, item) is None for item in attachments):
            _fail("附件不存在、已缺失或哈希变化", 409)
        requested_ref = data.room_status_ref.model_dump() if data.room_status_ref else None
        room_ref = requested_ref or _matching_room_ref(brief, attachments, read_room_status_snapshot(path))
        local, room, resolved, source_context = _context(str(path), attachments, room_ref)
        family = None
        if data.base_plan_id:
            parent = read_workspace_plan(path, data.base_plan_id)
            if not parent or parent["superseded"]:
                _fail("基础方案不存在或已有新版本", 409)
            family = parent["family_id"]
        normalized = {"brief": brief, "attachment_ids": sorted(data.attachment_ids), "room_status_ref": requested_ref}
        input_hash = _hash({"compiler": COMPILER_VERSION, "input": normalized, "source_context": source_context,
                            "family": family, "parent_plan_id": data.base_plan_id})
        with transaction() as conn:
            unchanged = None
            if family:
                latest = conn.execute("SELECT id,data FROM ws_plans WHERE family_id=? ORDER BY version DESC LIMIT 1", (family,)).fetchone()
                if not latest or latest[0] != data.base_plan_id:
                    _fail("方案已有新版本，请刷新后重试", 409)
                parent_item = json.loads(latest[1])
                if (parent_item["request"] == normalized and parent_item["source_context"] == source_context
                        and parent_item["compiler_version"] == COMPILER_VERSION):
                    unchanged = latest[0]
            old = conn.execute("SELECT id FROM ws_plans WHERE input_hash=?", (input_hash,)).fetchone()
            if unchanged:
                plan_id = unchanged
            elif old:
                plan_id = old[0]
            else:
                plan_id = "wsp-"+uuid.uuid4().hex
                version = 1
                if family:
                    latest = conn.execute("SELECT id,version FROM ws_plans WHERE family_id=? ORDER BY version DESC LIMIT 1", (family,)).fetchone()
                    if not latest or latest[0] != data.base_plan_id:
                        _fail("方案已有新版本，请刷新后重试", 409)
                    version = latest[1]+1
                item = {"id": plan_id, "family_id": family or plan_id, "parent_plan_id": data.base_plan_id,
                        "version": version, "created_at": _now(), "request": normalized,
                        "source_context": source_context, "room_status_ref": room_ref,
                        "generation_mode": "local_rules", "compiler_version": COMPILER_VERSION,
                        "plan": _generate(brief, attachments, local, room, resolved)}
                item["hash"] = _hash(item)
                conn.execute("INSERT INTO ws_plans VALUES (?,?,?,?,?)", (plan_id, item["family_id"], version, input_hash, _pack(item)))
        return read_workspace_plan(path, plan_id)

    @router.post("/plans/{plan_id}/confirm")
    async def confirm_plan(plan_id: str, request: Request):
        data = await _body(request, HashInput)
        item = current_plan(plan_id, data.plan_hash)
        with transaction() as conn:
            latest = conn.execute("SELECT MAX(version) FROM ws_plans WHERE family_id=?", (item["family_id"],)).fetchone()[0]
            if latest != item["version"]:
                _fail("方案已有新版本", 409)
            # Recheck external source/attachment gates inside the local write lock.
            current_plan(plan_id, data.plan_hash)
            confirmation = {"plan_hash": data.plan_hash, "confirmed_at": _now(), "kind": "local_direction_confirmation",
                            "identity_verified": False, "scope": "仅采用运营方案方向，不核实供给、房态、报价、权利或发布"}
            conn.execute("INSERT OR IGNORE INTO ws_confirmations VALUES (?,?,?)", (plan_id, data.plan_hash, _pack(confirmation)))
        return read_workspace_plan(path, plan_id)

    @router.post("/plans/{plan_id}/video-handoffs")
    async def video_handoff(plan_id: str, request: Request):
        data = await _body(request, HashInput)
        item = current_plan(plan_id, data.plan_hash)
        if not item["confirmation_valid"]:
            _fail("请先单独确认当前运营方案，再交给视频脚本层", 409)
        from .growth import create_campaign_from_workspace_plan
        # The growth owner atomically checks this plan and deduplicates its task.
        # Its transaction is deliberately not nested inside the receipt write.
        result = create_campaign_from_workspace_plan(str(path), item)
        with transaction() as conn:
            existing = conn.execute("SELECT data FROM ws_video_handoffs WHERE plan_id=?", (plan_id,)).fetchone()
            if existing:
                receipt = json.loads(existing[0])
                if receipt["campaign_id"] != result["campaign_id"]:
                    _fail("视频交接回执冲突，请保留现有任务核对", 409)
            else:
                receipt = {**result, "handoff_id": "wsh-"+uuid.uuid4().hex, "plan_id": plan_id,
                           "plan_hash": item["hash"], "created_at": _now(),
                           "receipt_note": "任务创建与本地回执分别持久化；重试复用同一任务，未编译脚本或发布。"}
                conn.execute("INSERT INTO ws_video_handoffs VALUES (?,?,?)", (receipt["handoff_id"], plan_id, _pack(receipt)))
        return {**receipt, "created": result.get("created", False), "scripts_generated": False}

    return router
