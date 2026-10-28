"""Bounded local-only culture intake. Paths are read for hashing, never persisted.

The public HTTP app intentionally has no file-path/import endpoint. This module's
CLI is for an operator-selected JSON package, with immutable SQLite snapshots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import Field, field_validator
try:
    from .domain import InputModel, SourceInput, KnowledgeInput, digest
except ImportError:
    from domain import InputModel, SourceInput, KnowledgeInput, digest

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_passages(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS culture_issues(id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS culture_imports(id TEXT PRIMARY KEY, bundle_hash TEXT NOT NULL UNIQUE, data TEXT NOT NULL);
"""
ID = r"[A-Za-z0-9_-]{1,120}"
SHA = r"[a-f0-9]{64}"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class IntakeSource(SourceInput):
    id: str = Field(pattern=ID)
    document_key: str = Field(min_length=1, max_length=120)
    sha256: str = Field(pattern=SHA)
    filename: str = Field(min_length=1, max_length=240)
    temporal_scope: str = Field(min_length=1, max_length=1000)
    region_scope: str = Field(min_length=1, max_length=240)

    @field_validator("filename")
    @classmethod
    def filename_only(cls, value):
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("文件名不得包含目录")
        return value


class IntakeDocument(InputModel):
    source_id: str = Field(pattern=ID)
    path: str = Field(min_length=1, max_length=4000)
    sha256: str = Field(pattern=SHA)


class IntakeKnowledge(KnowledgeInput):
    id: str = Field(pattern=ID)
    evidence_type: Literal["document_statement"] = "document_statement"
    kind: Literal["interpretation", "requirement"] = "interpretation"
    review_status: Literal["draft", "disputed"] = "draft"


class IntakeIssue(InputModel):
    id: str = Field(pattern=ID)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4000)
    kind: Literal["missing", "disputed", "unreadable", "verification", "rights"]
    status: Literal["open"] = "open"
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=500)
    topics: list[str] = Field(default_factory=list, max_length=40)
    scope: str = Field(min_length=1, max_length=1000)

    @field_validator("topics")
    @classmethod
    def topic_size(cls, values):
        if any(not 1 <= len(v) <= 120 for v in values):
            raise ValueError("问题主题长度须为1..120")
        return values


class IntakeBundle(InputModel):
    schema_version: Literal["yantian-culture-intake.v1"]
    batch_key: str = Field(min_length=1, max_length=120)
    sources: list[IntakeSource] = Field(min_length=1, max_length=100)
    documents: list[IntakeDocument] = Field(min_length=1, max_length=100)
    knowledge: list[IntakeKnowledge] = Field(default_factory=list, max_length=2000)
    issues: list[IntakeIssue] = Field(default_factory=list, max_length=500)


def _unique(items, field="id"):
    values = [getattr(v, field) for v in items]
    if len(values) != len(set(values)):
        raise ValueError("导入包存在重复编号")


def _file_sha(path):
    try:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("原件必须是本地常规文件，且不得超过100MiB")
        hasher = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        raise ValueError("原件不可读；请登记不可读缺口，不得捏造摘录") from None


def _read_original(path):
    """Fixed local readers only; no caller-selected command or web address."""
    value = Path(path)
    if value.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("可摘录原件不得超过20MiB")
    suffix = value.suffix.lower()
    if suffix == ".json":
        return "json", json.loads(value.read_text(encoding="utf-8"))
    if suffix == ".docx":
        with zipfile.ZipFile(value) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 12 * 1024 * 1024:
                raise ValueError("Word文本超出本地摘录限制")
            xml = archive.read(info)
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ValueError("Word文本不接受实体声明")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = ["".join(n.text or "" for n in p.findall(".//w:t", ns)).strip() for p in root.findall(".//w:p", ns)]
    elif suffix == ".doc":
        try:
            output = subprocess.run(["/usr/bin/textutil", "-convert", "txt", "-stdout", str(value)],
                                    check=True, capture_output=True, timeout=20).stdout
            if len(output) > 12 * 1024 * 1024:
                raise ValueError("提取文本超出本地摘录限制")
            text = output.decode("utf-8")
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise ValueError("Word原件提取失败；须先登记不可读缺口") from None
        paragraphs = [v.strip() for v in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    elif suffix in {".txt", ".md"}:
        paragraphs = [v.strip() for v in value.read_text(encoding="utf-8").splitlines()]
    else:
        raise ValueError("本地摘录仅支持doc/docx/json/txt/md，其他格式先登记不可读缺口")
    paragraphs = [v for v in paragraphs if v]
    if len(paragraphs) > 50000 or sum(len(v) for v in paragraphs) > 12 * 1024 * 1024:
        raise ValueError("原件文本超出本地限制")
    return "paragraphs", paragraphs


def _verify_excerpts(data):
    documents = {v.source_id: v for v in data.documents}
    originals = {}
    for item in data.knowledge:
        if item.source_id not in originals:
            try:
                originals[item.source_id] = _read_original(documents[item.source_id].path)
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError, UnicodeError):
                raise ValueError("原件提取失败或格式不支持；未导入摘录") from None
        mode, original = originals[item.source_id]
        excerpt = None
        try:
            if mode == "json" and item.locator.startswith("JSON Pointer /"):
                excerpt = original
                for part in item.locator.removeprefix("JSON Pointer ").strip("/").split("/"):
                    part = part.replace("~1", "/").replace("~0", "~")
                    excerpt = excerpt[int(part)] if isinstance(excerpt, list) else excerpt[part]
            elif mode == "paragraphs":
                match = re.fullmatch(r"文本提取非空段 P(\d+)，字符 (\d+)—(\d+)（Unicode字符，含首尾）", item.locator)
                joined = re.fullmatch(r"文本提取非空段 P(\d+)—P(\d+)，各段原文按顺序换行连接", item.locator)
                simple = re.fullmatch(r"第(\d+)段", item.locator)
                if match:
                    p, a, b = (int(v) for v in match.groups())
                    if min(p, a) < 1 or b < a or b > len(original[p-1]):
                        raise ValueError("选段范围不合法")
                    excerpt = original[p-1][a-1:b]
                elif joined:
                    a, b = (int(v) for v in joined.groups())
                    if a < 1 or b < a or b > len(original):
                        raise ValueError("选段范围不合法")
                    excerpt = "\n".join(original[a-1:b])
                elif simple:
                    p = int(simple[1])
                    if p < 1:
                        raise ValueError("段号不合法")
                    excerpt = original[p-1]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError("原文选段定位无效；未导入任何摘录") from None
        if not isinstance(excerpt, str) or excerpt != item.content:
            raise ValueError("引用内容与原件指定段落不一致；不得将归纳或改写作为原文导入")
    for source_id in originals:
        document = documents[source_id]
        if _file_sha(document.path) != document.sha256:
            raise ValueError("抽取期间原件发生变化；请重新校验")


def validate_bundle(raw, verify_files=True):
    data = IntakeBundle.model_validate(raw)
    for values in (data.sources, data.knowledge, data.issues):
        _unique(values)
    _unique(data.documents, "source_id")
    source_map = {s.id: s for s in data.sources}
    knowledge_map = {k.id: k for k in data.knowledge}
    issue_map = {v.id: v for v in data.issues}
    if {d.source_id for d in data.documents} != set(source_map):
        raise ValueError("每个来源必须有且只有一项原件校验记录")
    for document in data.documents:
        if document.sha256 != source_map[document.source_id].sha256:
            raise ValueError("原件与来源指纹不一致")
        if verify_files and _file_sha(document.path) != document.sha256:
            raise ValueError("原件指纹校验失败；未写入任何记录")
    for item in data.knowledge:
        if item.source_id not in source_map or any(v not in issue_map for v in item.issue_ids):
            raise ValueError("知识引用了未登记来源或问题")
        if item.rights_scope != "internal" or source_map[item.source_id].rights_scope != "internal":
            raise ValueError("本地摘录必须明确允许内部使用；未知权利仅登记来源缺口")
        if item.review_status == "disputed" and not item.issue_ids:
            raise ValueError("争议摘录必须关联问题记录")
    for issue in data.issues:
        if any(v not in source_map for v in issue.source_ids) or any(v not in knowledge_map for v in issue.knowledge_ids):
            raise ValueError("问题引用了导入包外编号")
        if issue.kind == "disputed" and len(issue.knowledge_ids) < 2:
            raise ValueError("争议问题至少应列出两项原文观点")
    if verify_files:
        _verify_excerpts(data)
    return data


def import_bundle(db_path, raw, *, verify_files=True):
    """Import a validated original-file package in one canonical DB transaction.

    verify_files=False is intended only for isolated synthetic tests. The CLI
    always verifies original files. No original paths enter SQLite or receipts.
    """
    data = validate_bundle(raw, verify_files=verify_files)
    clean = data.model_dump(exclude={"documents"})
    bundle_hash = digest(clean)
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        # The caller creates canonical tables through create_app first. No second
        # store, PG mirror or implicit source seeding is created here.
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_versions'").fetchone():
            raise ValueError("请先初始化严田OS的canonical文化库")
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT data FROM culture_imports WHERE bundle_hash=?", (bundle_hash,)).fetchone()
        if old:
            conn.rollback()
            return {**json.loads(old[0]), "replayed": True}
        source_ids, source_versions, passage_ids = {}, {}, []
        counts = {"sources_created": 0, "knowledge_created": 0, "knowledge_versions_created": 0, "passages_created": 0, "issues_created": 0}
        for source in data.sources:
            value = source.model_dump(exclude={"id"})
            actual_id = "src-doc-" + digest([source.document_key, source.sha256, digest(value)])[:32]
            source_ids[source.id] = actual_id
            existing = conn.execute("SELECT data FROM sources WHERE id=?", (actual_id,)).fetchone()
            if existing:
                saved = json.loads(existing[0])
                if saved.get("intake_source_fingerprint") != digest(value):
                    raise ValueError("同一原件的来源元数据已存在不同版本；请用新的document_key明确修订")
            else:
                previous = [json.loads(v[0]) for v in conn.execute("SELECT data FROM sources")]
                version = max([v.get("version", 0) for v in previous if v.get("document_key") == source.document_key] or [0]) + 1
                saved = {**value, "id": actual_id, "version": version, "created_at": stamp(),
                         "record_origin": "local_document_intake", "local_use_scope": "local_excerpt_only",
                         "fact_verification": "unverified", "training_rights": "unknown",
                         "intake_source_fingerprint": digest(value)}
                conn.execute("INSERT INTO sources VALUES (?,?)", (actual_id, pack(saved)))
                counts["sources_created"] += 1
            source_versions[source.id] = saved["version"]
        for item in data.knowledge:
            source_id = source_ids[item.source_id]
            source = next(s for s in data.sources if s.id == item.source_id)
            passage_id = "passage-" + digest([source_id, item.locator, item.content])[:32]
            passage = {"id": passage_id, "source_id": source_id, "source_sha256": source.sha256,
                       "source_version": source_versions[item.source_id], "locator": item.locator,
                       "text": item.content, "sha256": digest(item.content), "section_title": item.title,
                       "aliases": item.aliases, "created_at": stamp(), "fact_verification": "unverified"}
            if not conn.execute("SELECT 1 FROM source_passages WHERE id=?", (passage_id,)).fetchone():
                conn.execute("INSERT INTO source_passages VALUES (?,?,?)", (passage_id, source_id, pack(passage)))
                counts["passages_created"] += 1
            passage_ids.append(passage_id)
            value = item.model_dump(exclude={"id", "base_version", "version"})
            value.update(source_id=source_id, passage_id=passage_id, passage_sha256=passage["sha256"],
                         source_sha256=source.sha256, source_version=source_versions[item.source_id],
                         fact_verification="unverified", training_rights="unknown", record_origin="local_document_intake")
            previous = conn.execute("SELECT version,data FROM knowledge_versions WHERE id=? ORDER BY version DESC LIMIT 1", (item.id,)).fetchone()
            if previous:
                old_value = json.loads(previous[1])
                if old_value.get("record_origin") != "local_document_intake":
                    raise ValueError("知识编号与既有人工条目冲突；未覆盖原记录")
                if old_value.get("intake_content_fingerprint") == digest(value):
                    continue
            version = previous[0] + 1 if previous else 1
            saved = {**value, "id": item.id, "version": version, "created_at": stamp(), "intake_content_fingerprint": digest(value)}
            conn.execute("INSERT INTO knowledge_versions VALUES (?,?,?)", (item.id, version, pack(saved)))
            counts["knowledge_versions_created"] += 1
            if not previous:
                counts["knowledge_created"] += 1
        for issue in data.issues:
            value = issue.model_dump()
            value["source_ids"] = [source_ids[v] for v in issue.source_ids]
            # Include dependencies' exact source versions, keeping old issue snapshots.
            value["source_fingerprints"] = {source_ids[v]: next(s.sha256 for s in data.sources if s.id == v) for v in issue.source_ids}
            previous = conn.execute("SELECT version,data FROM culture_issues WHERE id=? ORDER BY version DESC LIMIT 1", (issue.id,)).fetchone()
            if previous and json.loads(previous[1]).get("intake_content_fingerprint") == digest(value):
                continue
            version = previous[0] + 1 if previous else 1
            saved = {**value, "version": version, "created_at": stamp(), "intake_content_fingerprint": digest(value)}
            conn.execute("INSERT INTO culture_issues VALUES (?,?,?)", (issue.id, version, pack(saved)))
            counts["issues_created"] += 1
        receipt = {"id": "import-" + bundle_hash[:32], "batch_key": data.batch_key, "schema_version": data.schema_version,
                   "bundle_hash": bundle_hash, "created_at": stamp(), "source_ids": list(source_ids.values()),
                   "knowledge_ids": [v.id for v in data.knowledge], "passage_ids": passage_ids,
                   "issue_ids": [v.id for v in data.issues], "counts": counts, "replayed": False,
                   "mode": "local", "model_connected": False, "training_performed": False,
                   "original_files_verified": verify_files, "original_fragments_verified": verify_files, "fact_verification": "unverified"}
        conn.execute("INSERT INTO culture_imports VALUES (?,?,?)", (receipt["id"], bundle_hash, pack(receipt)))
        conn.commit()
        return receipt
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.bundle.stat().st_size > 12 * 1024 * 1024:
        parser.error("导入包不得超过12MiB")
    receipt = import_bundle(args.db, json.loads(args.bundle.read_text(encoding="utf-8")))
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
