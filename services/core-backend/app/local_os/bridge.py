"""One Core-owned CultureService; no SQL repository copy or remote transport."""
from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

from fastapi import HTTPException

TENANT = "yantian"
SITE = "yantian-main"
_service = None


def culture_service_type():
    name = "yantian_canonical_culture"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(Path(__file__).resolve().parents[4] / "apps" / "civilization-studio")]
        sys.modules[name] = package
    return importlib.import_module(name + ".service").CultureService


def set_service(service):
    global _service
    _service = service


def get_service():
    if _service is None:
        raise HTTPException(503, "本地统一文化服务尚未初始化；不会降级到外部模型或其他知识库")
    return _service


def assert_scope(tenant=TENANT, site=SITE):
    if tenant != TENANT or site != SITE:
        raise HTTPException(403, "本地统一知识仅适用于 yantian / yantian-main；拒绝其他范围")


def assert_request_scope(request, payload=None):
    assert_scope(request.headers.get("x-tenant-id", TENANT), request.headers.get("x-site-id", SITE))
    payload = payload or {}
    nested = [payload.get(key) for key in ["metadata", "context"] if isinstance(payload.get(key), dict)]
    for values in [request.query_params, payload, *nested]:
        for key in ["tenant", "tenant_id"]:
            if key in values:
                assert_scope(values[key], SITE)
        for key in ["site", "site_id"]:
            if key in values:
                assert_scope(TENANT, values[key])


def legacy_dto(item):
    source = item.get("source") or {}
    return {**item, "tenant_id": TENANT, "site_id": SITE, "source": source.get("title"), "source_record": source,
            "summary": item["content"][:300], "knowledge_type": item["domain"],
            "domains": [item["domain"]], "tags": [], "source_title": source.get("title"),
            "source_url": source.get("url", ""), "verified": item.get("evidence_type", "curated_claim") == "curated_claim" and item["review_status"] == "approved",
            "verified_by": None, "verified_at": None, "citation_count": None,
            "credibility_score": None, "status": "retired" if item["review_status"] == "retired" else "active",
            "updated_at": item["created_at"], "verification_semantics": "local_review_declaration_not_independent_fact_verification",
            "metadata": {key: item.get(key) for key in ["source_id", "locator", "region_scope", "domain", "kind", "review_status", "rights_scope", "version", "review_note", "evidence_type", "issue_ids", "aliases", "passage_id", "passage_sha256", "source_sha256", "source_version", "fact_verification", "training_rights"]}}
