"""Local, deterministic validation and design helpers. No model or device I/O."""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def no_controls(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("文本不得包含控制字符")
        return value


class SourceInput(InputModel):
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(default="", max_length=2048)
    source_kind: Literal["public", "local", "oral", "project"]
    scope: str = Field(min_length=1, max_length=2000)
    rights_scope: Literal["internal", "unknown"] = "unknown"
    locator: str = Field(default="", max_length=1000)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("来源链接仅接受无凭据的 http(s) URL；不会抓取网页")
        if re.search(r"(?:^|[?&])(?:token|api_key|secret|password|access_token)=", parsed.query, re.I):
            raise ValueError("来源链接不得包含凭据参数")
        return value


class KnowledgeInput(InputModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20000)
    source_id: str = Field(min_length=1, max_length=120)
    locator: str = Field(min_length=1, max_length=1000)
    region_scope: str = Field(min_length=1, max_length=240)
    domain: Literal["humanities", "nature", "craft", "project"]
    kind: Literal["fact", "interpretation", "requirement"]
    review_status: Literal["draft", "source_checked", "approved", "disputed", "retired"]
    rights_scope: Literal["internal", "unknown"]
    base_version: int | None = Field(default=None, ge=1)
    version: int | None = Field(default=None, ge=1)
    review_note: str = Field(default="", max_length=4000)
    evidence_type: Literal["curated_claim", "document_statement"] = "curated_claim"
    issue_ids: list[str] = Field(default_factory=list, max_length=30)
    aliases: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("aliases")
    @classmethod
    def bounded_aliases(cls, values):
        if any(not isinstance(v, str) or not 1 <= len(v) <= 120 for v in values):
            raise ValueError("检索别名长度须为1..120")
        return list(dict.fromkeys(values))

    @field_validator("issue_ids")
    @classmethod
    def bounded_issue_ids(cls, values):
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", v) for v in values):
            raise ValueError("问题编号不合法")
        return list(dict.fromkeys(values))


class AskInput(InputModel):
    question: str = Field(min_length=1, max_length=2000)


class DesignInput(InputModel):
    title: str = Field(min_length=1, max_length=120)
    purpose: Literal["print_block", "decorative", "undecided"]
    label: str = Field(default="", max_length=30)
    width_mm: float = Field(ge=30, le=500)
    height_mm: float = Field(ge=30, le=500)
    motif: Literal["geometric", "leaf", "wave"]
    mirror_choice: Literal["yes", "no", "unconfirmed"]
    knowledge_ids: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=4000)
    svg: str | None = Field(default=None, max_length=100000)
    label_size_mm: float | None = Field(default=None, ge=2, le=80)
    base_version: int | None = Field(default=None, ge=1)

    @field_validator("knowledge_ids")
    @classmethod
    def knowledge_ids_valid(cls, values):
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", value) for value in values):
            raise ValueError("知识引用编号不合法")
        return list(dict.fromkeys(values))


class Confirmations(InputModel):
    culture: StrictBool = False
    rights: StrictBool = False
    craft: StrictBool = False


class ReviewInput(InputModel):
    version: int = Field(ge=1)
    reviewer_role: str = Field(min_length=1, max_length=120)
    decision: Literal["approve", "revise"]
    comment: str = Field(min_length=1, max_length=4000)
    confirmations: Confirmations


def digest(value):
    content = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ELEMENTS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "title", "desc"}
ATTRS = {"viewBox", "width", "height", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "d", "points", "fill", "stroke", "stroke-width", "font-size", "font-family", "font-weight", "text-anchor", "dominant-baseline", "transform", "opacity", "fill-rule", "stroke-linecap", "stroke-linejoin"}
NUMERIC = {"width", "height", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "stroke-width", "font-size", "opacity"}
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def sanitize_svg(value):
    if len(value) > 100000 or re.search(r"<!|<\?|url\s*\(|javascript\s*:|data\s*:|https?\s*:", value, re.I):
        # The standard SVG namespace URI is the only allowed URL-looking text.
        stripped = value.replace('xmlns="http://www.w3.org/2000/svg"', "").replace("xmlns='http://www.w3.org/2000/svg'", "")
        if len(value) > 100000 or re.search(r"<!|<\?|url\s*\(|javascript\s*:|data\s*:|https?\s*:", stripped, re.I):
            raise ValueError("SVG 不允许声明、脚本或外部资源")
    try:
        root = ET.fromstring(value)
    except ET.ParseError:
        raise ValueError("SVG 格式无法解析") from None
    nodes = list(root.iter())
    if len(nodes) > 1500:
        raise ValueError("SVG 元素过多")
    if root.tag not in {"svg", f"{{{SVG_NS}}}svg"}:
        raise ValueError("必须提供 SVG 根元素")
    for node in nodes:
        tag = node.tag
        if tag.startswith("{"):
            namespace, tag = tag[1:].split("}", 1)
            if namespace != SVG_NS:
                raise ValueError("SVG 命名空间不允许")
        if tag not in ELEMENTS or (node is not root and tag == "svg"):
            raise ValueError("SVG 包含不允许的元素")
        for attr, raw in node.attrib.items():
            if attr not in ATTRS or attr.lower().startswith("on") or "href" in attr.lower():
                raise ValueError("SVG 包含不允许的属性或事件")
            if len(raw) > 30000:
                raise ValueError("SVG 属性过长")
            if attr in NUMERIC:
                pattern = rf"{NUMBER}(?:mm)?" if attr in {"width", "height"} else NUMBER
                if not re.fullmatch(pattern, raw):
                    raise ValueError("SVG 数值属性不合法")
                number = float(raw.removesuffix("mm"))
                if not math.isfinite(number) or abs(number) > 1000000:
                    raise ValueError("SVG 数值超出本地预览范围")
            elif attr in {"fill", "stroke"}:
                if raw not in {"none", "black", "white", "currentColor"} and not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?", raw):
                    raise ValueError("SVG 颜色只允许本地纯色")
            elif attr == "d":
                if not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE+.,\s-]*", raw):
                    raise ValueError("SVG 路径不合法")
                if any(not math.isfinite(float(n)) or abs(float(n)) > 1000000 for n in re.findall(NUMBER, raw)):
                    raise ValueError("SVG 路径数值超出范围")
            elif attr in {"points", "viewBox"}:
                if not re.fullmatch(r"[0-9eE+.,\s-]+", raw):
                    raise ValueError("SVG 坐标不合法")
                values = re.findall(NUMBER, raw)
                if attr == "viewBox" and len(values) != 4:
                    raise ValueError("SVG viewBox 必须有四个数值")
                if any(not math.isfinite(float(n)) or abs(float(n)) > 1000000 for n in values):
                    raise ValueError("SVG 坐标超出范围")
            elif attr == "transform":
                transforms = re.findall(r"(?:matrix|translate|scale|rotate|skewX|skewY)\([0-9eE+.,\s-]+\)", raw)
                if not transforms or re.sub(r"\s+", "", "".join(transforms)) != re.sub(r"\s+", "", raw):
                    raise ValueError("SVG 变换不合法")
                if any(not math.isfinite(float(n)) or abs(float(n)) > 1000000 for transform in transforms for n in re.findall(NUMBER, transform)):
                    raise ValueError("SVG 变换数值超出范围")
            elif attr == "font-family" and raw not in {"serif", "sans-serif", "monospace", "Arial"}:
                raise ValueError("SVG 只允许本地通用字体")
            elif attr == "font-weight" and raw not in {"normal", "bold", "400", "600", "700"}:
                raise ValueError("SVG 字重不合法")
            elif attr == "text-anchor" and raw not in {"start", "middle", "end"}:
                raise ValueError("SVG 文本对齐不合法")
            elif attr == "dominant-baseline" and raw not in {"auto", "middle", "central", "hanging"}:
                raise ValueError("SVG 文本基线不合法")
            elif attr == "fill-rule" and raw not in {"nonzero", "evenodd"}:
                raise ValueError("SVG 填充规则不合法")
            elif attr in {"stroke-linecap", "stroke-linejoin"} and raw not in {"butt", "round", "square", "miter", "bevel"}:
                raise ValueError("SVG 线条属性不合法")
    return ET.tostring(root, encoding="unicode")


def make_svg(data):
    if data.svg is not None:
        return sanitize_svg(data.svg), "user_supplied"
    w, h = data.width_mm, data.height_mm
    font_size = data.label_size_mm or max(3, min(w, h) * .105)
    label = html.escape(data.label, quote=True)
    motif = []
    stroke = max(.3, min(w, h) * .006)
    if data.motif == "geometric":
        for index in range(5):
            x = w * (.18 + index * .16)
            y, s = h * .32, min(w, h) * .08
            motif.append(f'<path d="M{x:g},{y-s:g} L{x+s:g},{y:g} L{x:g},{y+s:g} L{x-s:g},{y:g} Z"/>')
    elif data.motif == "leaf":
        for index in range(4):
            x, y, s = w * (.23 + index * .18), h * .32, min(w, h) * .10
            motif.append(f'<path d="M{x-s:g},{y+s:g} Q{x-s:g},{y-s:g} {x+s:g},{y-s:g} Q{x+s:g},{y+s:g} {x-s:g},{y+s:g} M{x-s:g},{y+s:g} L{x+s:g},{y-s:g}"/>')
    else:
        for row in range(3):
            y = h * (.22 + row * .10)
            motif.append(f'<path d="M{w*.12:g},{y:g} Q{w*.22:g},{y-h*.09:g} {w*.32:g},{y:g} T{w*.52:g},{y:g} T{w*.72:g},{y:g} T{w*.92:g},{y:g}"/>')
    transform = f'translate({w:g} 0) scale(-1 1)' if data.mirror_choice == "yes" else "translate(0 0)"
    svg = f'<svg xmlns="{SVG_NS}" width="{w:g}mm" height="{h:g}mm" viewBox="0 0 {w:g} {h:g}"><title>原创设计练习：非传统纹样复刻</title><g transform="{transform}"><rect x="2" y="2" width="{w-4:g}" height="{h-4:g}" rx="2" fill="none" stroke="#263b33" stroke-width="{stroke:g}"/><g fill="none" stroke="#263b33" stroke-width="{stroke:g}">{"".join(motif)}</g><text x="{w/2:g}" y="{h*.76:g}" font-size="{font_size:g}" font-family="serif" text-anchor="middle" fill="#263b33">{label}</text></g></svg>'
    return sanitize_svg(svg), "generated_original_exercise"


def tokens(text):
    text = unicodedata.normalize("NFKC", text).lower()
    values = set(re.findall(r"[a-z0-9_]+", text))
    for word in re.findall(r"[\u3400-\u9fff]+", text):
        values.add(word)
        values.update(word[i:i+2] for i in range(len(word)-1))
    return values - {"什么", "哪些", "怎么", "如何", "是否", "可以", "一个", "有关", "关于", "介绍", "一下", "严田"}


def usable(item, source):
    return bool(item.get("evidence_type", "curated_claim") == "curated_claim" and source and item["review_status"] in {"source_checked", "approved"}
                and item["rights_scope"] == "internal" and source["rights_scope"] == "internal")


def source_is_local(source):
    scope = source.get("scope", "")
    return (source.get("source_kind") != "project" and "严田" in scope
            and not re.search(r"不能|不证明|不构成|区域|待核|未经", scope))


def project_question(question):
    return bool(re.search(r"首期|本期|软件|系统|模型|项目需求|工艺路线|机器.*(?:选|开|启)|(?:采用|使用).*工艺", question)) and not bool(re.search(r"起源|朝代|年代|历史|传承人|发源|非遗|祖传|最早", question))


MATCH_STOP = {"严田", "文化", "资料", "村落", "项目", "历史", "有关", "内容", "记录", "情况", "模型", "知识", "介绍", "哪些", "什么", "怎么", "如何", "是否", "可以", "一个", "这个", "我们", "庄园", "村的", "田村", "严田村", "根据", "出处", "一下", "知道", "请问", "时候", "什么时候", "上严", "下严", "上严田", "下严田", "田古", "田的", "的历", "记载", "史记", "录中", "旧文", "原文"}


def meaningful_overlap(question, item):
    query = tokens(question) - MATCH_STOP
    target = tokens(item["title"] + " " + item["content"] + " " + " ".join(item.get("aliases", []))) - MATCH_STOP
    overlap = query & target
    # Numeric coincidences and generic words cannot identify a cultural subject.
    return {v for v in overlap if len(v) >= 2 and not v.isdigit()}


def document_usable(item, source):
    return bool(source and item.get("evidence_type") == "document_statement"
                and item["review_status"] in {"draft", "disputed"}
                and item["rights_scope"] == "internal" and source["rights_scope"] == "internal"
                and source.get("local_use_scope") == "local_excerpt_only"
                and item.get("passage_id") and source.get("sha256") and source.get("is_current_version", True))


def select_evidence(question, items, sources, domains=None):
    """Deterministic excerpts; document statements never inherit fact approval."""
    question_tokens = tokens(question) - MATCH_STOP
    is_local, is_project = "严田" in question, project_question(question)
    ranked, blocked = [], []
    requested_domains = set(domains or [])
    exact_subjects = {alias for item in items for alias in item.get("aliases", [])
                      if len(alias) >= 2 and alias not in MATCH_STOP and not alias.isdigit()
                      and alias in question}
    facet = None
    if re.search(r"(?:古樟|古树|樟树).*(?:多少年|多少岁|多大|年龄|树龄)", question):
        facet = {"树龄", "年龄"}
    elif re.search(r"空间|格局|布局|结构|序列", question):
        facet = {"序列", "格局", "布局", "结构", "空间"}
    for item in items:
        if item.get("evidence_type") == "document_statement" and facet and not any(v in item["title"] + " ".join(item.get("aliases", [])) for v in facet):
            continue
        if requested_domains and item["domain"] not in requested_domains:
            continue
        overlap = meaningful_overlap(question, item)
        if exact_subjects and item.get("evidence_type") == "document_statement" and not any(
                subject in item["title"] + item["content"] + " ".join(item.get("aliases", [])) for subject in exact_subjects):
            continue
        if not overlap:
            continue
        source = sources.get(item["source_id"])
        document = document_usable(item, source)
        if not document and not usable(item, source):
            blocked.append("部分匹配资料属于草稿、争议、退役或权利未知，未作为事实回答依据。")
            continue
        if is_local:
            if is_project:
                if item["kind"] != "requirement" and item["domain"] != "project":
                    continue
            elif document:
                if item["domain"] == "project" or source["source_kind"] == "project" or "严田" not in item["region_scope"] or "严田" not in source.get("region_scope", ""):
                    blocked.append("区域资料及项目方案不能证明严田具体历史、起源、对象归属或传承人。")
                    continue
                if re.search(r"起源|发源|非遗|祖传|千年|传承人", question) and not re.search(r"起源|发源|非遗|祖传|千年|传承人", item["content"]):
                    blocked.append("检索到相近主题，但原文不支持问题中的起源、非遗或传承前提。")
                    continue
            elif item["kind"] != "fact" or "严田" not in item["region_scope"] or not source_is_local(source):
                blocked.append("徽州区域资料及项目需求不能证明严田具体历史、起源、对象归属或传承人。")
                continue
        elif item["kind"] == "requirement" and not is_project:
            continue
        score = sum(min(len(term), 6) for term in overlap)
        denominator = sum(min(len(term), 6) for term in question_tokens) or 1
        title_subject_bonus = 1 if any(subject in item["title"] for subject in exact_subjects) else 0
        ranked.append((min(1.0, (score / denominator) * 0.6 + title_subject_bonus * 0.4), item, source))
    return sorted(ranked, key=lambda row: (-row[0], row[1]["id"])), list(dict.fromkeys(blocked))


def validate_knowledge_scope(data, source):
    if data.evidence_type == "document_statement":
        if data.review_status in {"source_checked", "approved"}:
            raise ValueError("资料记载未经事实复核，不可直接标为已核对或批准事实")
        return
    local_assertion = any(
        re.search(r"严田.{0,35}(?:起源|发源|历史|朝代|传承|非遗|年代|始于|始建|已有|拥有|认证|千年)", sentence)
        and not re.search(r"不能|不应|尚未|待核|不可|无法|仍需|不代表|未经|不足", sentence)
        for sentence in re.split(r"[。！？\n]", data.title + "。" + data.content)
    )
    if data.kind == "fact" and ("严田" in data.region_scope or local_assertion) and data.review_status in {"source_checked", "approved"} and not source_is_local(source):
        raise ValueError("该来源仅支持区域资料或项目需求，不能确认严田局地文化事实；请保留为草稿或补充局地来源")
    if data.kind == "fact" and data.domain in {"humanities", "craft", "nature"} and source["source_kind"] == "project" and data.review_status in {"source_checked", "approved"}:
        raise ValueError("项目需求来源不能充当已核对的文化或自然事实证据")
