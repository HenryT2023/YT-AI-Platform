#!/usr/bin/env python3
"""严田文明智慧工作台：仅本地、摘录问答、不可变稿样与人工审阅。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

try:
    from .ingest import SCHEMA as INTAKE_SCHEMA
    from .domain import (AskInput, DesignInput, KnowledgeInput, ReviewInput, SourceInput,
                         digest, make_svg, select_evidence, usable, validate_knowledge_scope, document_usable, meaningful_overlap, MATCH_STOP)
except ImportError:  # Standalone ``python server.py``.
    from ingest import SCHEMA as INTAKE_SCHEMA
    from domain import (AskInput, DesignInput, KnowledgeInput, ReviewInput, SourceInput,
                        digest, make_svg, select_evidence, usable, validate_knowledge_scope, document_usable, meaningful_overlap, MATCH_STOP)


BASE = Path(__file__).resolve().parent
VERSION = "1.1.0-local-cited-culture"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_versions (id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS design_versions (id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, design_id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_candidates (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS qa_history (id TEXT PRIMARY KEY, data TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex


def pack(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def fail(status, message):
    raise HTTPException(status, message)


def same_local_origin(request):
    """Support a loopback reverse proxy without accepting foreign browser origins."""
    origin = request.headers.get("origin")
    base = urlsplit(str(request.base_url))
    if base.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
        return False
    expected = f"{base.scheme}://{base.netloc}"
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        parsed = urlsplit("http://" + forwarded_host)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path or parsed.username:
            return False
        expected = "http://" + forwarded_host
    return not origin or origin == expected


def fetch_json(conn, sql, parameters=()):
    row = conn.execute(sql, parameters).fetchone()
    return json.loads(row[0]) if row else None


def source_by_id(conn, item_id):
    value = fetch_json(conn, "SELECT data FROM sources WHERE id=?", (item_id,))
    if value and value.get("document_key"):
        peers = [json.loads(v[0]) for v in conn.execute("SELECT data FROM sources")]
        value["is_current_version"] = value.get("version", 1) == max(v.get("version", 1) for v in peers if v.get("document_key") == value["document_key"])
    return value


def latest_knowledge(conn, item_id):
    return fetch_json(conn, "SELECT data FROM knowledge_versions WHERE id=? ORDER BY version DESC LIMIT 1", (item_id,))


def latest_design(conn, item_id):
    return fetch_json(conn, "SELECT data FROM design_versions WHERE id=? ORDER BY version DESC LIMIT 1", (item_id,))


def current_items(conn, table):
    # Table identifiers are private fixed constants, never user input.
    if table not in {"knowledge_versions", "design_versions"}:
        raise ValueError("内部表名不合法")
    rows = conn.execute(f"SELECT t.data FROM {table} t JOIN (SELECT id,MAX(version) version FROM {table} GROUP BY id) h ON t.id=h.id AND t.version=h.version ORDER BY t.rowid DESC").fetchall()
    return [json.loads(row[0]) for row in rows]


def current_issues(conn):
    rows = conn.execute("SELECT t.data FROM culture_issues t JOIN (SELECT id,MAX(version) version FROM culture_issues GROUP BY id) h ON t.id=h.id AND t.version=h.version ORDER BY t.rowid DESC")
    return [json.loads(row[0]) for row in rows]


def public_knowledge(conn, item):
    source = source_by_id(conn, item["source_id"])
    return {**item, "source": {key: source.get(key, "") for key in ["id", "title", "url", "filename", "sha256", "version", "temporal_scope", "region_scope", "local_use_scope", "fact_verification", "is_current_version"]} if source else None}


def source_snapshots(conn, ids):
    snapshots = []
    for knowledge_id in ids:
        item = latest_knowledge(conn, knowledge_id)
        if not item:
            fail(422, "设计引用的知识不存在")
        source = source_by_id(conn, item["source_id"])
        snapshots.append({"knowledge_id": knowledge_id, "knowledge_version": item["version"],
                          "knowledge_hash": digest(item), "source_hash": digest(source),
                          "usable_at_creation": usable(item, source)})
    return snapshots


def current_sources_unchanged(conn, design):
    for snapshot in design["knowledge_snapshots"]:
        item = latest_knowledge(conn, snapshot["knowledge_id"])
        source = source_by_id(conn, item["source_id"]) if item else None
        if not item or item["version"] != snapshot["knowledge_version"] or digest(item) != snapshot["knowledge_hash"] or digest(source) != snapshot["source_hash"] or not usable(item, source):
            return False
    return True


def design_detail(conn, design):
    reviews = [json.loads(row[0]) for row in conn.execute("SELECT data FROM reviews WHERE design_id=? ORDER BY rowid", (design["id"],))]
    versions = [json.loads(row[0]) for row in conn.execute("SELECT data FROM design_versions WHERE id=? ORDER BY version", (design["id"],))]
    relevant = [review for review in reviews if review["version"] == design["version"] and review["design_hash"] == design["hash"]]
    if not current_sources_unchanged(conn, design):
        state = "source_changed"
    elif relevant:
        state = "approved" if relevant[-1]["decision"] == "approve" else "needs_revision"
    else:
        state = "draft"
    return {**design, "status": state,
            "versions": [{key: item[key] for key in ["version", "hash", "created_at"]} for item in versions],
            "reviews": reviews, "approval_is_local_declaration": True,
            "limitations": ["原创设计练习，不声称是传统纹样或历史复刻。", "工艺师角色仅为本地申报，未独立验证身份。", "稿样审阅不构成加工安全证明或已制作回执。"]}


def build_design(conn, data, item_id, version):
    try:
        svg, origin = make_svg(data)
    except ValueError as exc:
        fail(422, str(exc))
    payload = data.model_dump(exclude={"svg", "base_version"})
    payload.update(id=item_id, version=version, svg=svg, svg_origin=origin,
                   knowledge_snapshots=source_snapshots(conn, data.knowledge_ids),
                   created_at=now(), record_origin="design_exercise",
                   fabrication_parameters=None, machine_state="not_applicable_hand_woodcut")
    payload["hash"] = digest(payload)
    return payload


def create_app(db_path=None, seed=True):
    path = Path(db_path) if db_path is not None else BASE / "data" / "studio.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def database(write=False):
        conn = sqlite3.connect(str(path), timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("PRAGMA query_only=ON")
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(SCHEMA + INTAKE_SCHEMA)
        if seed and not connection.execute("SELECT 1 FROM meta WHERE key='seed_initialized'").fetchone():
            seed_data = json.loads((BASE / "seed.json").read_text(encoding="utf-8"))
            for raw in seed_data["sources"]:
                item = {**SourceInput.model_validate({k: v for k, v in raw.items() if k != "id"}).model_dump(), "id": raw["id"], "created_at": now()}
                connection.execute("INSERT OR IGNORE INTO sources(id,data) VALUES (?,?)", (item["id"], pack(item)))
            for raw in seed_data["knowledge"]:
                data = KnowledgeInput.model_validate({k: v for k, v in raw.items() if k != "id"})
                source = source_by_id(connection, data.source_id)
                validate_knowledge_scope(data, source)
                item = {**data.model_dump(exclude={"base_version", "version"}), "id": raw["id"], "version": 1, "created_at": now()}
                connection.execute("INSERT OR IGNORE INTO knowledge_versions(id,version,data) VALUES (?,?,?)", (item["id"], 1, pack(item)))
            connection.execute("INSERT INTO meta(key,value) VALUES ('seed_initialized',?)", (now(),))
        connection.commit()
    finally:
        connection.close()

    app = FastAPI(title="严田文明智慧工作台", version=VERSION, docs_url=None, redoc_url=None)
    app.state.db_path = path

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("x-yantian-local") != "1":
                return JSONResponse({"detail": "本地变更需要 X-Yantian-Local: 1"}, status_code=403)
            origin = request.headers.get("origin")
            try:
                if not same_local_origin(request):
                    return JSONResponse({"detail": "拒绝非同源请求"}, status_code=403)
            except ValueError:
                return JSONResponse({"detail": "请求来源不合法"}, status_code=403)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > 300000:
                        return JSONResponse({"detail": "请求内容超过本地限制"}, status_code=413)
                except ValueError:
                    return JSONResponse({"detail": "请求长度不合法"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        locations = [".".join(str(value) for value in error["loc"] if value != "body") for error in exc.errors()[:5]]
        return JSONResponse({"detail": "输入校验失败，请检查字段及长度/数值范围：" + "、".join(locations)}, status_code=422)

    @app.get("/api/status")
    def status():
        with database() as conn:
            counts = {
                "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "knowledge": conn.execute("SELECT COUNT(DISTINCT id) FROM knowledge_versions").fetchone()[0],
                "designs": conn.execute("SELECT COUNT(DISTINCT id) FROM design_versions").fetchone()[0],
                "reviews": conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
            }
            coverage = {"passages": conn.execute("SELECT COUNT(*) FROM source_passages").fetchone()[0],
                        "issues": len(current_issues(conn)),
                        "imports": conn.execute("SELECT COUNT(*) FROM culture_imports").fetchone()[0]}
        return {"app_name": "严田文明智慧工作台", "version": VERSION, "mode": "local",
                "model": {"connected": False, "mode": "extractive"}, "machine": {"enabled": False},
                "counts": counts, "culture_coverage": {
                    "passages": coverage["passages"], "open_issues": coverage["issues"], "imports": coverage["imports"],
                    "document_statement_notice": "本地文档摘录未经文化事实复核；仅支持有出处的资料记载查询。"}, "data_path_label": "用户指定的本地 SQLite 数据目录"}

    @app.get("/api/sources")
    def sources():
        with database() as conn:
            return [source_by_id(conn, row[0]) for row in conn.execute("SELECT id FROM sources ORDER BY rowid DESC")]

    @app.get("/api/sources/{item_id}")
    def get_source(item_id: str):
        with database() as conn:
            source = source_by_id(conn, item_id)
            if not source:
                fail(404, "来源不存在")
            passages = [json.loads(r[0]) for r in conn.execute("SELECT data FROM source_passages WHERE source_id=? ORDER BY rowid", (item_id,))]
            issues = [v for v in current_issues(conn) if item_id in v.get("source_ids", [])]
            return {"source": source, "passages": passages, "issues": issues}

    @app.get("/api/passages/{item_id}")
    def get_passage(item_id: str):
        with database() as conn:
            passage = fetch_json(conn, "SELECT data FROM source_passages WHERE id=?", (item_id,))
            if not passage:
                fail(404, "原文选段不存在")
            source = source_by_id(conn, passage["source_id"])
            return {**passage, "source": source}

    @app.get("/api/issues")
    def list_issues():
        with database() as conn:
            return current_issues(conn)

    @app.get("/api/imports")
    def list_imports():
        with database() as conn:
            return [json.loads(r[0]) for r in conn.execute("SELECT data FROM culture_imports ORDER BY rowid DESC")]

    @app.post("/api/sources")
    def add_source(data: SourceInput):
        item = {**data.model_dump(), "id": new_id("src"), "created_at": now()}
        with database(True) as conn:
            conn.execute("INSERT INTO sources(id,data) VALUES (?,?)", (item["id"], pack(item)))
        return item

    @app.get("/api/knowledge")
    def knowledge():
        with database() as conn:
            return [public_knowledge(conn, item) for item in current_items(conn, "knowledge_versions")]

    @app.post("/api/knowledge")
    def add_knowledge(data: KnowledgeInput):
        if data.evidence_type == "document_statement":
            fail(422, "文档摘录须通过本地原件校验导入工具登记，以保留段落快照和指纹")
        with database(True) as conn:
            source = source_by_id(conn, data.source_id)
            if not source:
                fail(422, "请选择已登记来源")
            try:
                validate_knowledge_scope(data, source)
            except ValueError as exc:
                fail(422, str(exc))
            item = {**data.model_dump(exclude={"base_version", "version"}), "id": new_id("kn"), "version": 1, "created_at": now()}
            conn.execute("INSERT INTO knowledge_versions VALUES (?,?,?)", (item["id"], 1, pack(item)))
            return public_knowledge(conn, item)

    @app.put("/api/knowledge/{item_id}")
    def update_knowledge(item_id: str, data: KnowledgeInput):
        with database(True) as conn:
            current = latest_knowledge(conn, item_id)
            if not current:
                fail(404, "知识条目不存在")
            if current.get("evidence_type") == "document_statement":
                fail(409, "导入文档摘录不可改写或升格事实；请修订有原件指纹的导入包并追加版本")
            if data.evidence_type == "document_statement":
                fail(422, "文档摘录须通过本地原件校验导入工具登记")
            base_version = data.base_version if data.base_version is not None else data.version
            if base_version is None:
                fail(422, "编辑知识需要 base_version（当前版本号）")
            if base_version != current["version"]:
                fail(409, "知识版本已变化，请刷新后再编辑")
            source = source_by_id(conn, data.source_id)
            if not source:
                fail(422, "请选择已登记来源")
            try:
                validate_knowledge_scope(data, source)
            except ValueError as exc:
                fail(422, str(exc))
            item = {**data.model_dump(exclude={"base_version", "version"}), "id": item_id, "version": current["version"] + 1, "created_at": now()}
            conn.execute("INSERT INTO knowledge_versions VALUES (?,?,?)", (item_id, item["version"], pack(item)))
            return public_knowledge(conn, item)

    @app.post("/api/ask")
    def ask(data: AskInput):
        with database(True) as conn:
            sources = {row[0]: source_by_id(conn, row[0]) for row in conn.execute("SELECT id FROM sources")}
            items = current_items(conn, "knowledge_versions")
            ranked, blocked = select_evidence(data.question, items, sources)
            current_gap = None
            if __import__("re").search(r"(?:今天|今日|现在|目前|当期|实时|本周|明天).*(?:开放|参观|营业|预约|房|价|钱|场次|人数)|(?:开放|营业|能参观|可参观|能预约|可预约).*(?:吗|么|时间)|(?:客房|住房|空房|房价).*(?:多少钱|几间|多少间|价格)|谁.*(?:非遗|传承人)|(?:非遗|传承人).*(?:是谁|名单|身份)", data.question):
                current_gap = "现有文化资料不能核实当前开放、房价库存、预约条件或传承人身份；需由管理者核当期记录或提供有效身份与项目证据。"
                ranked = []
            selected = [row for row in ranked[:3] if row[0] >= ranked[0][0] * 0.7] if ranked else []
            selected_ids = {v[1]["id"] for v in selected}
            all_issues = current_issues(conn)
            issues = [issue for issue in all_issues if
                      (selected_ids.intersection(issue.get("knowledge_ids", [])) and
                       (issue["kind"] != "disputed" or any(len(topic) >= 2 and topic not in MATCH_STOP and not topic.isdigit() and topic in data.question for topic in issue.get("topics", []))))
                      or any(len(topic) >= 2 and topic not in MATCH_STOP and not topic.isdigit() and topic in data.question for topic in issue.get("topics", []))]
            # Once a disputed claim is selected, include all available opposing
            # original excerpts, even when their lexical score is lower.
            peer_ids = {v for issue in issues if issue["kind"] == "disputed" for v in issue.get("knowledge_ids", [])}
            for item in items:
                if not current_gap and item["id"] in peer_ids and item["id"] not in selected_ids and document_usable(item, sources.get(item["source_id"])):
                    selected.append((0, item, sources[item["source_id"]]))
                    selected_ids.add(item["id"])
            citations = []
            for _, item, source in selected[:10]:
                citations.append({"knowledge_id": item["id"], "knowledge_version": item["version"],
                                  "title": item["title"], "source_id": source["id"], "source_title": source["title"], "url": source["url"],
                                  "filename": source.get("filename", ""), "source_version": source.get("version", 1),
                                  "source_sha256": source.get("sha256", ""), "source_scope": source.get("scope", ""),
                                  "temporal_scope": source.get("temporal_scope", "未登记时点"),
                                  "locator": item["locator"], "region_scope": item["region_scope"],
                                  "review_status": item["review_status"], "excerpt": item["content"],
                                  "evidence_type": item.get("evidence_type", "curated_claim"),
                                  "fact_verification": item.get("fact_verification", "source_checked_only"),
                                  "passage_id": item.get("passage_id"), "passage_sha256": item.get("passage_sha256"),
                                  "issue_ids": item.get("issue_ids", [])})
            limitations = ["本版从本地已登记知识中确定性检索摘录，尚未连接生成式模型。", "出处可回查仅表示文档选段与指纹有记录，不代表严田文化事实已经独立核实。", "本地资料摘录许可不构成训练、公开传播或商业使用许可。"]
            limitations.extend(dict.fromkeys(blocked))
            disputed = any(v["kind"] == "disputed" for v in issues)
            gaps = [v["description"] for v in issues if v["kind"] in {"missing", "unreadable", "verification", "rights"}]
            if current_gap:
                gaps.insert(0, current_gap)
            if citations:
                prefix = "以下为资料记载，附原文定位；未经事实复核，不作额外历史推断。" if any(c["evidence_type"] == "document_statement" for c in citations) else "以下为知识条目摘录，附原始来源定位；未作额外历史推断。"
                if disputed:
                    prefix += " 相关资料存在不同说法，以下并列展示，不裁定孰是；原文中的年代或表述疑点均保留待核。"
                answer = prefix + "\n\n" + "\n\n".join(f"[{index+1}] {citation['excerpt']}" for index, citation in enumerate(citations))
                state = "answered"
                evidence_state = "document_statement" if any(c["evidence_type"] == "document_statement" for c in citations) else "curated_claim"
            else:
                answer = "现有可用证据不足，无法回答该问题。" + (current_gap or "请补充具有明确出处、适用范围与本地使用权的资料。")
                state, evidence_state = "insufficient_evidence", "insufficient"
                gaps.append("没有找到足以直接支持该问题的原文选段；资料缺失不能解释为该事物不存在。")
            item = {"id": new_id("qa"), "question": data.question, "answer": answer, "status": state,
                    "mode": "extractive", "model_connected": False, "citations": citations,
                    "evidence_state": evidence_state, "disputed": disputed, "issues": issues, "gaps": list(dict.fromkeys(gaps)),
                    "limitations": limitations, "created_at": now()}
            conn.execute("INSERT INTO qa_history VALUES (?,?)", (item["id"], pack(item)))
            return item

    @app.get("/api/designs")
    def designs():
        with database() as conn:
            return [design_detail(conn, item) for item in current_items(conn, "design_versions")]

    @app.post("/api/designs/preview")
    def preview_design(data: DesignInput):
        try:
            svg, origin = make_svg(data)
        except ValueError as exc:
            fail(422, str(exc))
        with database() as conn:
            source_snapshots(conn, data.knowledge_ids)
        return {"svg": svg, "hash": digest(svg), "svg_origin": origin, "persisted": False,
                "original_design_exercise": True, "machine_enabled": False}

    @app.post("/api/designs")
    def add_design(data: DesignInput):
        with database(True) as conn:
            item = build_design(conn, data, new_id("design"), 1)
            conn.execute("INSERT INTO design_versions VALUES (?,?,?)", (item["id"], 1, pack(item)))
            return design_detail(conn, item)

    @app.get("/api/designs/{item_id}")
    def get_design(item_id: str):
        with database() as conn:
            item = latest_design(conn, item_id)
            if not item:
                fail(404, "稿样不存在")
            return design_detail(conn, item)

    @app.put("/api/designs/{item_id}")
    def update_design(item_id: str, data: DesignInput):
        with database(True) as conn:
            current = latest_design(conn, item_id)
            if not current:
                fail(404, "稿样不存在")
            if data.base_version is None:
                fail(422, "编辑稿样需要 base_version（当前版本号）")
            if data.base_version != current["version"]:
                fail(409, "稿样版本已变化，请刷新后再编辑")
            item = build_design(conn, data, item_id, current["version"] + 1)
            conn.execute("INSERT INTO design_versions VALUES (?,?,?)", (item_id, item["version"], pack(item)))
            return design_detail(conn, item)

    @app.get("/api/designs/{item_id}/svg")
    def download_svg(item_id: str, version: int | None = None):
        with database() as conn:
            item = latest_design(conn, item_id) if version is None else fetch_json(conn, "SELECT data FROM design_versions WHERE id=? AND version=?", (item_id, version))
            if not item:
                fail(404, "指定稿样版本不存在")
            safe_id = "".join(c for c in item["id"] if c.isalnum() or c in "-_")
            filename = f"woodcut-{safe_id}-v{item['version']}.svg"
            return Response(item["svg"], media_type="image/svg+xml", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Content-Security-Policy": "default-src 'none'; style-src 'none'; sandbox"})

    @app.post("/api/designs/{item_id}/reviews")
    def review_design(item_id: str, data: ReviewInput):
        with database(True) as conn:
            item = latest_design(conn, item_id)
            if not item:
                fail(404, "稿样不存在")
            if data.version != item["version"]:
                fail(409, "稿样已有新版本；不能审阅旧版作为当前批准")
            if data.decision == "approve":
                if not all(data.confirmations.model_dump().values()):
                    fail(422, "批准需要文化、权利、工艺三项明确确认")
                if item["purpose"] == "undecided":
                    fail(422, "批准前请明确印版或装饰用途")
                if item["purpose"] == "print_block" and item["mirror_choice"] == "unconfirmed":
                    fail(422, "印版批准前请明确镜像选择")
                if not current_sources_unchanged(conn, item):
                    fail(409, "引用知识已变化、退役或尚不可用；请更新稿样引用并重新审阅")
            review = {**data.model_dump(), "id": new_id("review"), "design_id": item_id,
                      "design_hash": item["hash"], "created_at": now(), "identity_verified": False,
                      "review_scope": "local_declaration_only"}
            conn.execute("INSERT INTO reviews VALUES (?,?,?,?)", (review["id"], item_id, item["version"], pack(review)))
            candidate = {"id": new_id("candidate"), "design_id": item_id, "design_version": item["version"],
                         "review_id": review["id"], "comment": data.comment, "state": "pending_review",
                         "training_rights": "unknown", "created_at": now()}
            conn.execute("INSERT INTO learning_candidates VALUES (?,?)", (candidate["id"], pack(candidate)))
            return {"review": review, "design": design_detail(conn, item)}

    @app.get("/api/learning-candidates")
    def candidates():
        with database() as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT data FROM learning_candidates ORDER BY rowid DESC")]

    @app.get("/api/export")
    def export():
        with database() as conn:
            output = {"app_name": "严田文明智慧工作台", "version": VERSION, "mode": "local", "exported_at": now(),
                      "model": {"connected": False, "mode": "extractive"}, "machine": {"enabled": False}}
            for key, table in [("sources", "sources"), ("knowledge_versions", "knowledge_versions"), ("design_versions", "design_versions"), ("reviews", "reviews"), ("learning_candidates", "learning_candidates"), ("qa_history", "qa_history"), ("passages", "source_passages"), ("issue_versions", "culture_issues"), ("imports", "culture_imports")]:
                output[key] = [json.loads(row[0]) for row in conn.execute(f"SELECT data FROM {table} ORDER BY rowid")]
            output["knowledge"] = current_items(conn, "knowledge_versions")
            output["designs"] = [design_detail(conn, item) for item in current_items(conn, "design_versions")]
        return Response(json.dumps(output, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="yantian-civilization-local-export.json"'})

    @app.get("/api/machines/capabilities")
    def capabilities():
        return {"enabled": False, "route": "hand_woodcut", "state": "not_configured", "operations": [],
                "message": "机器尚未选定；机型、控制器、CAM和机器参数均为not_applicable，本版只支持手工稿样与审阅。"}

    @app.post("/api/machines/jobs")
    async def machine_jobs(request: Request):
        fail(423, "机器接口未启用；本版仅支持手工稿样与审阅。")

    # API routes precede the catch-all static mount. The frontend owns static/.
    app.mount("/static", StaticFiles(directory=str(BASE / "static"), check_dir=False), name="assets")
    app.mount("/", StaticFiles(directory=str(BASE / "static"), html=True, check_dir=False), name="static")
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--data-dir", type=Path, default=BASE / "data")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口须在1024..65535之间")
    import uvicorn
    uvicorn.run(create_app(args.data_dir / "studio.sqlite3"), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
