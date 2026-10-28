"""Canonical local intake and citation regression, only synthetic temporary DBs."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app
from ingest import import_bundle, validate_bundle

HEADERS = {"X-Yantian-Local": "1", "Origin": "http://testserver"}


def bundle(tmp_path):
    sources, documents, knowledge = [], [], []
    for i, text in enumerate(["严田建村：原文记作北宋964年建村。", "严田建村：原文记作唐代建村，李姓964年迁入。"]):
        path = tmp_path / f"source{i}.txt"
        path.write_text(text, encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append({"id": f"src{i}", "document_key": f"test-doc-{i}", "title": f"合成原件{i}", "url": "", "source_kind": "local", "scope": "合成严田文化原件，未经事实复核", "rights_scope": "internal", "locator": "第1段", "sha256": sha, "filename": path.name, "temporal_scope": "历史描述，日期待核", "region_scope": "严田村"})
        documents.append({"source_id": f"src{i}", "path": str(path), "sha256": sha})
        knowledge.append({"id": f"kn-test-{i}", "title": "严田建村不同记载", "content": text, "source_id": f"src{i}", "locator": "第1段", "region_scope": "严田村", "domain": "humanities", "kind": "interpretation", "review_status": "disputed", "rights_scope": "internal", "review_note": "文档摘录未复核", "evidence_type": "document_statement", "issue_ids": ["issue-history"], "aliases": ["建村年代", "始建年代"]})
    return {"schema_version": "yantian-culture-intake.v1", "batch_key": "synthetic-batch-v1", "sources": sources, "documents": documents, "knowledge": knowledge, "issues": [{"id": "issue-history", "title": "建村年代存在不同记载", "description": "两份合成原文说法不一致，且北宋与964的对应待核；不裁定。", "kind": "disputed", "status": "open", "source_ids": ["src0", "src1"], "knowledge_ids": ["kn-test-0", "kn-test-1"], "topics": ["建村", "年代"], "scope": "合成严田历史原文"}]}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "canonical.sqlite3"
    app = create_app(path)
    raw = bundle(tmp_path)
    receipt = import_bundle(path, raw)
    with TestClient(app) as client:
        yield path, raw, receipt, client


def ask(client, question):
    response = client.post("/api/ask", json={"question": question}, headers=HEADERS)
    assert response.status_code == 200
    return response.json()


def test_import_replay_exact_snapshots_and_no_paths(setup):
    path, raw, receipt, client = setup
    repeated = import_bundle(path, raw)
    assert repeated["replayed"] and repeated["id"] == receipt["id"]
    different_batch = copy.deepcopy(raw)
    different_batch["batch_key"] = "another-replay-label"
    unchanged = import_bundle(path, different_batch)
    assert not unchanged["replayed"]
    assert all(v == 0 for v in unchanged["counts"].values())
    exported = client.get("/api/export").json()
    assert len(exported["imports"]) == 2
    assert len(exported["passages"]) == 2
    assert len(exported["knowledge_versions"]) == 5
    assert str(path.parent) not in json.dumps(exported, ensure_ascii=False)
    assert all(v["training_rights"] == "unknown" for v in exported["knowledge_versions"] if v["evidence_type"] == "document_statement")
    detail = client.get("/api/sources/" + receipt["source_ids"][0]).json()
    passage = detail["passages"][0]
    assert passage["text"] == raw["knowledge"][0]["content"]
    assert passage["sha256"] == hashlib.sha256(passage["text"].encode()).hexdigest()
    assert detail["source"]["sha256"] == raw["sources"][0]["sha256"]
    assert client.get("/api/passages/" + passage["id"]).json()["locator"] == "第1段"
    assert client.get("/api/passages/nonexistent").status_code == 404
    assert client.get("/api/sources/nonexistent").status_code == 404


def test_dispute_and_stable_qa_history(setup):
    path, raw, receipt, client = setup
    answer = ask(client, "严田是什么时候建村的，年代有哪些不同说法？")
    assert answer["status"] == "answered" and answer["evidence_state"] == "document_statement"
    assert answer["disputed"] and len(answer["citations"]) == 2
    assert {v["source_sha256"] for v in answer["citations"]} == {v["sha256"] for v in raw["sources"]}
    assert all(v["passage_id"] and v["passage_sha256"] for v in answer["citations"])
    assert "未经事实复核" in answer["answer"] and "不裁定" in answer["answer"]
    assert "北宋964" in answer["answer"]
    changed = copy.deepcopy(raw)
    changed["batch_key"] = "second-version"
    changed["knowledge"][0]["content"] += " 本段追加合成校注，仍待核。"
    # Changed source bytes and original hashes are required, not a silently rewritten citation.
    Path(changed["documents"][0]["path"]).write_text(changed["knowledge"][0]["content"], encoding="utf-8")
    sha = hashlib.sha256(Path(changed["documents"][0]["path"]).read_bytes()).hexdigest()
    changed["documents"][0]["sha256"] = changed["sources"][0]["sha256"] = sha
    receipt2 = import_bundle(path, changed)
    assert receipt2["counts"]["sources_created"] == 1
    assert receipt2["counts"]["knowledge_versions_created"] == 1
    assert receipt2["counts"]["issues_created"] == 1
    current = next(v for v in client.get("/api/knowledge").json() if v["id"] == "kn-test-0")
    assert current["version"] == 2 and current["source_version"] == 2 and current["review_status"] == "disputed"
    saved = next(v for v in client.get("/api/export").json()["qa_history"] if v["id"] == answer["id"])
    assert saved == answer
    assert client.get("/api/passages/" + answer["citations"][0]["passage_id"]).status_code == 200


def test_import_rolls_back_collision_and_hash_failure(setup):
    path, raw, receipt, client = setup
    before = client.get("/api/export").json()
    bad = copy.deepcopy(raw)
    bad["batch_key"] = "bad-collision"
    bad["sources"][0]["sha256"] = bad["documents"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="指纹"):
        import_bundle(path, bad)
    assert client.get("/api/export").json()["imports"] == before["imports"]
    bad = copy.deepcopy(raw)
    bad["batch_key"] = "bad-existing-id"
    bad["knowledge"][0]["id"] = "kn-three-carvings"
    bad["issues"][0]["knowledge_ids"][0] = "kn-three-carvings"
    with pytest.raises(ValueError, match="冲突"):
        import_bundle(path, bad)
    after = client.get("/api/export").json()
    for key in ["sources", "passages", "knowledge_versions", "issue_versions", "imports"]:
        assert after[key] == before[key]


@pytest.mark.parametrize("question", ["严田木刻起源于哪个朝代？", "谁是严田非遗木刻传承人？", "严田今天客房多少钱？", "严田今天空几间房？", "秩叙堂今天开放吗？", "秩叙堂现在能参观吗？", "火星量子咖啡如何种植？", "严田文化资料有哪些？"])
def test_missing_false_premise_and_current_fact_refusal(setup, question):
    _, _, _, client = setup
    answer = ask(client, question)
    assert answer["status"] == "insufficient_evidence" and answer["citations"] == []
    assert answer["gaps"]
    if any(v in question for v in ["今天", "现在", "谁是"]):
        assert "当前开放" in answer["answer"]


def test_legacy_curated_and_source_scope_gates_remain(setup):
    _, _, _, client = setup
    assert ask(client, "徽州三雕是什么")["status"] == "answered"
    assert ask(client, "严田首期采用什么工艺路线")["status"] == "answered"
    assert ask(client, "严田木刻具有千年历史吗")["status"] == "insufficient_evidence"
    item = next(v for v in client.get("/api/knowledge").json() if v["id"] == "kn-test-0")
    payload = {k: item[k] for k in ["title", "content", "source_id", "locator", "region_scope", "domain", "kind", "review_status", "rights_scope"]}
    # Even deliberately omitting evidence_type cannot upgrade imported records.
    assert client.put("/api/knowledge/kn-test-0", json={**payload, "base_version": 1, "review_status": "approved"}, headers=HEADERS).status_code == 409
    assert client.post("/api/knowledge", json={**payload, "evidence_type": "document_statement"}, headers=HEADERS).status_code == 422


def test_unreadable_untrusted_and_bounded_inputs(setup):
    path, raw, _, client = setup
    bad = copy.deepcopy(raw)
    bad["documents"][0]["path"] = str(path.parent / "does-not-exist")
    with pytest.raises(ValueError, match="常规文件"):
        import_bundle(path, bad)
    bad = copy.deepcopy(raw)
    bad["sources"][0]["filename"] = "../../private"
    with pytest.raises(ValueError):
        validate_bundle(bad)
    bad = copy.deepcopy(raw)
    bad["knowledge"][0]["content"] = "x" * 20001
    with pytest.raises(ValueError):
        validate_bundle(bad)
    assert client.post("/api/ask", json={"question": "x" * 2001}, headers=HEADERS).status_code == 422
    assert client.post("/api/ask", json={"question": ""}, headers=HEADERS).status_code == 422
    assert client.post("/api/ask", json={"question": "严田建村"}, headers={**HEADERS, "Origin": "https://foreign.invalid"}).status_code == 403
    assert client.post("/api/imports", json={"path": "/etc/passwd"}, headers=HEADERS).status_code == 405
    # HTML-looking text is returned only as JSON data; no HTML source execution.
    xss = copy.deepcopy(raw)
    xss["batch_key"] = "untrusted-text"
    xss["knowledge"][0]["aliases"] = ["<img src=x onerror=alert(1)>"]
    import_bundle(path, xss)
    response = client.get("/api/knowledge")
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_original_excerpt_mismatch_refuses_without_writes(setup):
    path, raw, _, client = setup
    before = client.get("/api/export").json()
    bad = copy.deepcopy(raw)
    bad["batch_key"] = "fabricated-quote"
    bad["knowledge"][0]["content"] = "这是未在原件出现的改写，不得冒充引用。"
    with pytest.raises(ValueError, match="原件指定段落不一致"):
        import_bundle(path, bad)
    after = client.get("/api/export").json()
    assert after["knowledge_versions"] == before["knowledge_versions"]
    assert after["imports"] == before["imports"]


def test_legacy_payload_cannot_upgrade_imported_document(setup):
    _, _, _, client = setup
    core = str(Path(__file__).resolve().parents[3] / "services" / "core-backend")
    sys.path.insert(0, core)
    from app.local_os.integration import knowledge_payload
    from app.local_os.bridge import legacy_dto
    from fastapi import HTTPException
    item = next(v for v in client.get("/api/knowledge").json() if v["id"] == "kn-test-0")
    projected = legacy_dto(item)
    assert not projected["verified"]
    for key in ["evidence_type", "issue_ids", "passage_id", "source_sha256", "source_version"]:
        assert projected["metadata"][key] == item[key]
    with pytest.raises(HTTPException) as error:
        knowledge_payload({"review_status": "approved", "base_version": 1}, item)
    assert error.value.status_code == 409
