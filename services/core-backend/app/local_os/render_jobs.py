"""Persistent local video jobs. No provider, publishing or operating-ledger writes.

Only server-owned immutable packages and validated asset bytes reach the worker.
A confirmation permits an internal preview, never public distribution.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .bridge import assert_request_scope

BASE = "/api/local-os/growth"
RENDERER_VERSION = "yantian-local-video-v1"
MAX_ARTIFACT = 200 * 1024 * 1024
CONFIRMATION_SCOPE = "仅确认当前脚本、分镜及参考标识用于本地待审预览；不确认房态、套餐、素材对外权利或发布"
_MANAGERS = {}
_MANAGERS_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else _pack(value).encode()).hexdigest()


def _fail(message, status=409):
    raise HTTPException(status, message)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class RenderChecks(_Input):
    script: bool
    storyboard: bool
    reference_labels: bool


class ConfirmationInput(_Input):
    package_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmations: RenderChecks
    note: str = Field(default="", max_length=2000)


class JobInput(_Input):
    package_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")


async def _body(request, model):
    raw = await request.body()
    if len(raw) > 16 * 1024:
        _fail("成片请求过大", 413)
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        assert_request_scope(request, value)
        value = {key: item for key, item in value.items() if key not in {"tenant", "tenant_id", "site", "site_id"}}
        return model.model_validate(value)
    except (ValueError, UnicodeError, ValidationError):
        _fail("请检查成片确认、脚本版本及输入字段", 422)


def _safe_directory(path, root):
    """Reject symlinks in every owned component, including an existing job dir."""
    root = Path(root)
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        _fail("成片文件目录无效")
    current = root
    for part in ("", *relative.parts):
        if part:
            current = current / part
        if current.is_symlink():
            _fail("成片目录完整性检查失败")
        if current.exists() and not current.is_dir():
            _fail("成片目录完整性检查失败")
    return path


def _read_file(target, root, expected=None):
    target = Path(target)
    _safe_directory(target.parent, root)
    if target.is_symlink():
        _fail("成片文件完整性检查失败")
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                _fail("成片文件类型无效")
            data = handle.read(MAX_ARTIFACT + 1)
    except (OSError, ValueError):
        _fail("成片文件缺失或不可读取")
    if len(data) > MAX_ARTIFACT:
        _fail("成片文件超过本地安全上限")
    if expected and (len(data) != expected["size_bytes"] or _digest(data) != expected["sha256"]):
        _fail("成片文件哈希已变化，请保留记录并重新生成")
    return data


def _write_owned(target, data, root):
    """Replace an owned file atomically without following a target symlink."""
    target = Path(target)
    _safe_directory(target.parent, root)
    if target.is_symlink():
        _fail("成片文件完整性检查失败")
    temporary = target.parent / (".write-" + uuid.uuid4().hex)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(temporary, flags, 0o600), "wb") as handle:
            handle.write(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _default_render(**kwargs):
    from .video_renderer import render_video
    return render_video(**kwargs)


def _renderer_capabilities():
    try:
        from .video_renderer import renderer_capabilities
        return renderer_capabilities()
    except (ImportError, AttributeError):
        return {"available": False, "reason": "本地渲染组件尚未就绪", "renderer_version": RENDERER_VERSION}


class RenderManager:
    def __init__(self, db_path, snapshot, render_fn=None, recover=True):
        self.path = Path(db_path).resolve()
        self.root = self.path.parent / "growth-renders"
        _safe_directory(self.root, self.root)
        self.root.mkdir(exist_ok=True)
        self.snapshot = snapshot
        self.render_fn = render_fn or _default_render
        self.lock = threading.Lock()
        self.thread = None
        self.cancel_event = threading.Event()
        self.capabilities = lambda: ({"available": True, "renderer_version": RENDERER_VERSION} if render_fn else _renderer_capabilities())
        with self.transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS gr_render_confirmations(id TEXT PRIMARY KEY,package_id TEXT NOT NULL,package_hash TEXT NOT NULL,input_hash TEXT NOT NULL,data TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS gr_render_jobs(id TEXT PRIMARY KEY,package_id TEXT NOT NULL,input_key TEXT NOT NULL UNIQUE,data TEXT NOT NULL)")
            if recover:
                for job in self.rows(conn, "jobs"):
                    if job["status"] == "running":
                        self._mark_failed(conn, job, "INTERRUPTED", "上次本地成片进程已中断；保留记录，可明确重试")
        if recover:
            self.start()

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def rows(conn, table):
        if table not in {"jobs", "confirmations"}:
            raise ValueError("invalid internal table")
        return [json.loads(row[0]) for row in conn.execute("SELECT data FROM gr_render_" + table + " ORDER BY rowid")]

    @staticmethod
    def get(conn, table, item_id):
        if table not in {"jobs", "confirmations"}:
            raise ValueError("invalid internal table")
        row = conn.execute("SELECT data FROM gr_render_" + table + " WHERE id=?", (item_id,)).fetchone()
        if not row:
            _fail("指定成片记录不存在", 404)
        return json.loads(row[0])

    @staticmethod
    def save_job(conn, job):
        conn.execute("UPDATE gr_render_jobs SET data=? WHERE id=?", (_pack(job), job["id"]))

    def _attempt_dir(self, job):
        target = self.root / job["id"] / ("attempt-" + str(job["attempt"]))
        _safe_directory(target, self.root)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _artifact(self, file, media_type):
        blob = _read_file(file, self.root)
        return {"storage_path": str(file.relative_to(self.root)), "sha256": _digest(blob), "size_bytes": len(blob), "media_type": media_type}

    def _write_receipt(self, job, payload):
        directory = self._attempt_dir(job)
        target = directory / "receipt.json"
        if target.is_symlink():
            _fail("成片回执完整性检查失败")
        # Only bounded public job metadata, no source paths, credentials or raw records.
        receipt = {"contract": "yantian.local-video-receipt.v1", "job_id": job["id"], "package_id": job["package_id"],
                   "package_hash": job["package_hash"], "input_hash": job["input_hash"], "renderer_version": job["renderer_version"],
                   "confirmation_id": job["confirmation_id"], "confirmation_scope": CONFIRMATION_SCOPE,
                   "input_fingerprints": job.get("input_fingerprints", {}),
                   "status": job["status"], "attempt": job["attempt"], "created_at": job["created_at"],
                   "finished_at": job.get("finished_at"), "preview_only": True, "published": False,
                   "provider_calls": [], "external_side_effects": [], **payload}
        _write_owned(target, json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"), self.root)
        return self._artifact(target, "application/json")

    def _mark_failed(self, conn, job, code, message):
        job.update(status="failed", phase="failed", finished_at=_now(), error={"code": code, "message": message})
        try:
            receipt = self._write_receipt(job, {"error": job["error"]})
            job["artifacts"] = {"receipt": receipt}
        except (OSError, HTTPException):
            job["artifacts"] = {}
        job.setdefault("events", []).append({"at": _now(), "status": "failed", "attempt": job["attempt"], "error": job["error"]})
        self.save_job(conn, job)

    async def current(self, package_id, expected_hash=None):
        state = await self.snapshot(package_id)
        if expected_hash and state["package"]["hash"] != expected_hash:
            _fail("脚本分镜hash不匹配，请读取当前版本")
        return state

    @staticmethod
    def ensure_ready(state):
        if state["blockers"]:
            _fail("当前脚本分镜或来源已变化，请先处理：" + "；".join(state["blockers"][:5]))

    def confirmation_dto(self, confirmation, state):
        valid = confirmation["package_hash"] == state["package"]["hash"] and confirmation["input_hash"] == state["fingerprint"] and not state["blockers"] and confirmation["renderer_version"] == RENDERER_VERSION
        return {**confirmation, "valid": valid, "scope": CONFIRMATION_SCOPE, "blockers": [] if valid else state["blockers"] or ["脚本、素材或渲染输入版本已变化，请重新确认"]}

    def job_dto(self, job, state=None):
        public = {key: value for key, value in job.items() if key not in {"artifacts", "input_key", "events", "previous_attempts", "input_fingerprints"}}
        artifacts = None
        stored = job.get("artifacts", {})
        if stored:
            base = BASE + "/renders/" + job["id"] + "/artifacts/"
            artifacts = {kind: base + kind for kind in stored}
            if "video" in stored:
                artifacts["download"] = base + "video?download=1"
        stale_reasons = []
        if state:
            stale_reasons = state["blockers"] or (["当前输入版本已变化，成片仅供历史追溯"] if state["fingerprint"] != job["input_hash"] else [])
        if job["renderer_version"] != RENDERER_VERSION:
            stale_reasons = [*stale_reasons, "本地渲染器版本已更新，旧成片仅供历史追溯"]
        attempt_history = [{"attempt": previous["attempt"], "status": "failed", "error": previous.get("error"),
                            "finished_at": previous.get("finished_at"),
                            "receipt": BASE + "/renders/" + job["id"] + "/artifacts/receipt?attempt=" + str(previous["attempt"])
                            if previous.get("artifacts", {}).get("receipt") else None}
                           for previous in job.get("previous_attempts", [])]
        return {**public, "artifacts": artifacts, "stale": bool(stale_reasons), "stale_reasons": stale_reasons,
                "attempt_history": attempt_history,
                "preview_only": True, "published": False, "provider_calls": [], "external_side_effects": []}

    def close(self):
        self.cancel_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def start(self):
        with self.lock:
            if self.cancel_event.is_set():
                return
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._drain, name="yantian-local-video", daemon=True)
            self.thread.start()

    def _progress(self, job_id, progress, phase="rendering"):
        with self.transaction() as conn:
            job = self.get(conn, "jobs", job_id)
            if job["status"] != "running":
                return
            job["progress"] = max(job["progress"], min(98, int(progress)))
            job["phase"] = str(phase)[:80]
            self.save_job(conn, job)

    def _drain(self):
        while not self.cancel_event.is_set():
            # Serialize the empty-queue exit with start() to avoid leaving a
            # newly queued record without a worker at the exit boundary.
            with self.lock:
                with self.transaction() as conn:
                    waiting = next((row for row in self.rows(conn, "jobs") if row["status"] == "queued"), None)
                    if not waiting:
                        self.thread = None
                        return
                    waiting.update(status="running", phase="validating", progress=1, started_at=_now(), finished_at=None, error=None)
                    self.save_job(conn, waiting)
            self._run(waiting)

    def _run(self, job):
        try:
            state = asyncio.run(self.current(job["package_id"], job["package_hash"]))
            self.ensure_ready(state)
            if state["fingerprint"] != job["input_hash"]:
                _fail("成片输入版本已变化，请重新确认")
            with self.transaction() as conn:
                confirmation = self.get(conn, "confirmations", job["confirmation_id"])
            if not self.confirmation_dto(confirmation, state)["valid"]:
                _fail("成片确认已失效，请重新确认脚本分镜")
            directory = self._attempt_dir(job)
            inputs = directory / "inputs"
            _safe_directory(inputs, self.root)
            inputs.mkdir(exist_ok=True)
            assets = []
            for asset in state["assets"]:
                blob = asset["bytes"]
                if _digest(blob) != asset["sha256"] or len(blob) != asset["size_bytes"]:
                    _fail("成片素材快照完整性检查失败")
                extension = asset["extension"]
                if not re.fullmatch(r"(?:png|jpg|webp|gif|mp4|mov)", extension):
                    continue
                target = inputs / (asset["id"] + "." + extension)
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", asset["id"]) or target.is_symlink():
                    _fail("成片素材编号无效")
                _write_owned(target, blob, self.root)
                assets.append({key: value for key, value in asset.items() if key not in {"bytes", "extension"}} | {"snapshot_path": str(target)})
            self._progress(job["id"], 5, "rendering")
            result = self.render_fn(job_dir=directory, package_snapshot=state["package"], assets=assets,
                                    progress=lambda progress, phase="rendering": self._progress(job["id"], progress, phase),
                                    cancel_event=self.cancel_event)
            current = asyncio.run(self.current(job["package_id"], job["package_hash"]))
            self.ensure_ready(current)
            if current["fingerprint"] != job["input_hash"]:
                _fail("渲染期间脚本、来源或素材已变化，本次不作为当前成片")
            artifacts = {}
            for kind, mime in [("video", "video/mp4"), ("poster", "image/jpeg"), ("subtitles", "application/x-subrip")]:
                name = result["files"][kind]
                if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                    _fail("本地渲染输出名称无效")
                target = directory / "output" / name
                if target.parent != directory / "output":
                    _fail("本地渲染输出位置无效")
                artifacts[kind] = self._artifact(target, mime)
            metadata = {key: result.get("metadata", {}).get(key) for key in ["duration_seconds", "width", "height", "fps", "sha256", "video_codec", "audio_codec"] if key in result.get("metadata", {})}
            if metadata.get("sha256") != artifacts["video"]["sha256"]:
                _fail("本地渲染输出哈希与渲染回执不一致")
            renderer_receipt = {}
            receipt_name = result.get("files", {}).get("receipt")
            if receipt_name == "receipt.json":
                blob = _read_file(directory / "output" / receipt_name, self.root)
                if len(blob) <= 1024*1024:
                    renderer_receipt = json.loads(blob)
            with self.transaction() as conn:
                job = self.get(conn, "jobs", job["id"])
                job.update(status="succeeded", phase="completed", progress=100, finished_at=_now(), error=None)
                job["artifacts"] = artifacts
                job["metadata"] = metadata
                job["artifacts"]["receipt"] = self._write_receipt(job, {"artifacts": {key: {k: v for k, v in value.items() if k != "storage_path"} for key, value in artifacts.items()}, "warnings": list(dict.fromkeys(current["warnings"] + result.get("warnings", []))), "metadata": job["metadata"], "renderer_receipt": renderer_receipt})
                job.setdefault("events", []).append({"at": _now(), "status": "succeeded", "attempt": job["attempt"]})
                self.save_job(conn, job)
        except Exception as exc:
            message = str(exc.detail)[:600] if isinstance(exc, HTTPException) else getattr(exc, "public_message", "本地成片未完成，请检查渲染依赖及素材后明确重试")
            code = "INPUT_CHANGED" if isinstance(exc, HTTPException) and exc.status_code == 409 else "RENDER_FAILED"
            if type(exc).__module__ == "app.local_os.video_renderer" and type(exc).__name__ in {"RenderError", "RenderCancelled"}:
                message = str(exc)[:600]
                if type(exc).__name__ == "RenderCancelled":
                    code = "INTERRUPTED"
            with self.transaction() as conn:
                current_job = self.get(conn, "jobs", job["id"])
                self._mark_failed(conn, current_job, code, message)


def create_render_router(db_path, snapshot, render_fn=None, recover=True, prefix=BASE):
    """Mount under growth. ``snapshot`` is the existing growth evidence gate."""
    path = str(Path(db_path).resolve())
    with _MANAGERS_LOCK:
        manager = _MANAGERS.get(path)
        if manager is None or manager.cancel_event.is_set():
            manager = RenderManager(path, snapshot, render_fn=render_fn, recover=recover)
            _MANAGERS[path] = manager
        else:
            manager.snapshot = snapshot
    router = APIRouter(prefix=prefix, tags=["本地待审成片"])
    router.add_event_handler("shutdown", manager.close)
    # Exposed for narrow isolated tests; no client can replace renderer/snapshot.
    router.render_manager = manager

    async def state_dto(package_id):
        state = await manager.current(package_id)
        with manager.transaction() as conn:
            confirmations = [value for value in manager.rows(conn, "confirmations") if value["package_id"] == package_id]
            jobs = [manager.job_dto(value, state) for value in manager.rows(conn, "jobs") if value["package_id"] == package_id]
        confirmation = manager.confirmation_dto(confirmations[-1], state) if confirmations else None
        capabilities = manager.capabilities()
        return {"package_id": package_id, "package_hash": state["package"]["hash"], "renderer_version": RENDERER_VERSION, "confirmation": confirmation,
                "readiness": {"available": not state["blockers"], "blockers": state["blockers"], "warnings": state["warnings"]},
                "jobs": jobs, "capabilities": {**capabilities, "publishing_connected": False, "provider_connected": False}, "confirmation_scope": CONFIRMATION_SCOPE}

    @router.get("/packages/{package_id}/render-state")
    async def render_state(package_id: str, request: Request):
        assert_request_scope(request)
        return await state_dto(package_id)

    @router.post("/packages/{package_id}/render-confirmations")
    async def confirm(package_id: str, request: Request):
        data = await _body(request, ConfirmationInput)
        if not all(data.confirmations.model_dump().values()):
            _fail("请逐项确认当前脚本、分镜及参考标识", 422)
        state = await manager.current(package_id, data.package_hash)
        manager.ensure_ready(state)
        with manager.transaction() as conn:
            previous = next((value for value in reversed(manager.rows(conn, "confirmations")) if value["package_id"] == package_id and value["input_hash"] == state["fingerprint"] and value["renderer_version"] == RENDERER_VERSION), None)
            if previous:
                item = previous
            else:
                item = {"id": "render-confirm-" + uuid.uuid4().hex, "package_id": package_id, "package_hash": data.package_hash,
                    "input_hash": state["fingerprint"], "renderer_version": RENDERER_VERSION, "confirmations": data.confirmations.model_dump(),
                    "note": data.note, "confirmation_scope": CONFIRMATION_SCOPE, "identity_verified": False, "created_at": _now()}
                conn.execute("INSERT INTO gr_render_confirmations VALUES (?,?,?,?,?)", (item["id"], package_id, data.package_hash, state["fingerprint"], _pack(item)))
        return await state_dto(package_id)

    @router.post("/packages/{package_id}/renders")
    async def create_job(package_id: str, request: Request):
        data = await _body(request, JobInput)
        state = await manager.current(package_id, data.package_hash)
        manager.ensure_ready(state)
        if not manager.capabilities().get("available"):
            _fail("本地渲染依赖尚未就绪；不会降级调用外部服务", 503)
        input_key = _digest({"package_id": package_id, "input_hash": state["fingerprint"], "renderer_version": RENDERER_VERSION})
        with manager.transaction() as conn:
            confirmation = manager.get(conn, "confirmations", data.confirmation_id)
            if confirmation["package_id"] != package_id or not manager.confirmation_dto(confirmation, state)["valid"]:
                _fail("脚本分镜确认已失效或不属于当前版本")
            previous = next((value for value in manager.rows(conn, "jobs") if value["input_key"] == input_key), None)
            if previous:
                return manager.job_dto(previous, state)
            job = {"id": "render-" + uuid.uuid4().hex, "package_id": package_id, "package_hash": data.package_hash,
                   "campaign_id": state["package"]["campaign_id"], "input_hash": state["fingerprint"], "input_key": input_key,
                   "input_fingerprints": state.get("input_fingerprints", {}),
                   "confirmation_id": confirmation["id"], "renderer_version": RENDERER_VERSION,
                   "status": "queued", "phase": "queued", "progress": 0, "attempt": 1, "created_at": _now(),
                   "started_at": None, "finished_at": None, "error": None, "artifacts": {}, "events": []}
            conn.execute("INSERT INTO gr_render_jobs VALUES (?,?,?,?)", (job["id"], package_id, input_key, _pack(job)))
        manager.start()
        return manager.job_dto(job, state)

    @router.get("/renders/{job_id}")
    async def read_job(job_id: str, request: Request):
        assert_request_scope(request)
        with manager.transaction() as conn:
            job = manager.get(conn, "jobs", job_id)
        try:
            state = await manager.current(job["package_id"])
        except HTTPException:
            state = {"blockers": ["来源或脚本记录已不可用，成片仅供历史追溯"], "fingerprint": ""}
        return manager.job_dto(job, state)

    @router.post("/renders/{job_id}/retry")
    async def retry(job_id: str, request: Request):
        data = await _body(request, JobInput)
        with manager.transaction() as conn:
            old = manager.get(conn, "jobs", job_id)
        state = await manager.current(old["package_id"], data.package_hash)
        manager.ensure_ready(state)
        if not manager.capabilities().get("available"):
            _fail("本地渲染依赖尚未就绪；不会降级调用外部服务", 503)
        with manager.transaction() as conn:
            job = manager.get(conn, "jobs", job_id)
            confirmation = manager.get(conn, "confirmations", data.confirmation_id)
            if job["status"] != "failed":
                _fail("只有失败的本地成片任务可以明确重试")
            if state["fingerprint"] != job["input_hash"] or confirmation["package_id"] != job["package_id"] or not manager.confirmation_dto(confirmation, state)["valid"]:
                _fail("原成片输入或确认已变化，请按当前脚本重新确认生成")
            job.setdefault("previous_attempts", []).append({"attempt": job["attempt"], "error": job.get("error"), "finished_at": job.get("finished_at"), "artifacts": job.get("artifacts", {})})
            job.update(status="queued", phase="queued", progress=0, attempt=job["attempt"] + 1, confirmation_id=confirmation["id"], started_at=None, finished_at=None, error=None, artifacts={})
            manager.save_job(conn, job)
        manager.start()
        return manager.job_dto(job, state)

    @router.api_route("/renders/{job_id}/artifacts/{kind}", methods=["GET", "HEAD"])
    async def artifact_file(job_id: str, kind: Literal["video", "poster", "receipt", "subtitles"], request: Request, download: bool = False, attempt: int | None = None):
        assert_request_scope(request)
        with manager.transaction() as conn:
            job = manager.get(conn, "jobs", job_id)
        selected = job if attempt is None or attempt == job["attempt"] else next((value for value in job.get("previous_attempts", []) if value["attempt"] == attempt), {})
        artifact = selected.get("artifacts", {}).get(kind)
        if not artifact:
            _fail("该成片产物尚未生成", 404)
        relative = artifact["storage_path"]
        if not re.fullmatch(r"render-[a-f0-9]{32}/attempt-[1-9][0-9]*/(?:output/)?[A-Za-z0-9_.-]+", relative):
            _fail("成片文件位置无效")
        data = _read_file(manager.root / relative, manager.root, artifact)
        extension = {"video": "mp4", "poster": "jpg", "receipt": "json", "subtitles": "srt"}[kind]
        headers = {"Content-Disposition": ('attachment' if download else 'inline') + '; filename="yantian-' + job_id + '.' + extension + '"',
                   "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "no-store", "Accept-Ranges": "bytes", "ETag": '"' + artifact["sha256"] + '"'}
        status = 200
        length = len(data)
        range_value = request.headers.get("range")
        if range_value:
            match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", range_value)
            try:
                if not match or not any(match.groups()):
                    raise ValueError
                a, b = match.groups()
                start = int(a) if a else max(0, length - int(b))
                end = min(length - 1, int(b)) if a and b else length - 1
                if start >= length or start > end or (not a and int(b) == 0):
                    raise ValueError
            except (ValueError, OverflowError):
                return Response(status_code=416, headers={**headers, "Content-Range": "bytes */" + str(length)})
            headers["Content-Range"] = f"bytes {start}-{end}/{length}"
            data, status = data[start:end + 1], 206
        headers["Content-Length"] = str(len(data))
        return Response(b"" if request.method == "HEAD" else data, status_code=status, media_type=artifact["media_type"], headers=headers)

    return router
