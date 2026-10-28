"""Bounded, local attachment inspection; raw text never leaves this module.

This module deliberately returns lexical hints, not document or image claims.
The caller owns the already-written private file and its lifecycle.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date


MAX_BYTES = 10 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_ZIP_BYTES = 16 * 1024 * 1024
MAX_ZIP_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_XML_ELEMENTS = 100_000
MAX_XML_DEPTH = 64

INVALID = "附件格式或内容无法安全读取。"
TOO_LARGE = "附件超过本地处理限额。"
UNSUPPORTED = "不支持此附件类型或文件类型不一致。"
UNSAFE = "附件包含不允许的结构或内容。"
UNAVAILABLE = "本地附件校验工具不可用。"

_MIMES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "application/csv"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pdf": {"application/pdf"},
}
_TOPICS = (
    ("住宿", ("住宿", "民宿", "客房", "房态", "入住", "核房")),
    ("木刻", ("木刻", "版画", "版印")),
    ("油纸伞", ("油纸伞", "纸伞", "伞面", "伞绘")),
    ("自然", ("自然", "花园", "农事", "古樟", "水口", "山野", "田园")),
    ("陶瓷", ("陶瓷", "陶艺", "陶板", "拉坯", "烧制")),
    ("徽派", ("徽派", "徽州", "徽文化")),
    ("婺剧", ("婺剧",)),
    ("茶道", ("茶道", "茶事", "茶席", "闻香", "品茶")),
    ("摄影", ("摄影", "拍摄", "照片", "拍照")),
)
_UNSAFE_MARKUP = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b|<\s*(?:[A-Za-z_][\w.-]*:)?(?:html|svg)\b", re.I)
_DOC_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_XLS_MAIN = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_W_STRICT_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
_S_STRICT_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"


def _reject_markup(data: bytes) -> None:
    # Removing NULs also detects UTF-16/32 declarations before XML parsing.
    if _UNSAFE_MARKUP.search(data.replace(b"\x00", b"")):
        raise ValueError(UNSAFE)


def _local_file(data: bytes, local_path: Path) -> Path:
    """Only inspect the exact private regular file supplied by the caller."""
    try:
        path = Path(local_path)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError(INVALID)
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(data):
            raise ValueError(INVALID)
        with path.open("rb") as handle:
            if handle.read(MAX_BYTES + 1) != data:
                raise ValueError(INVALID)
        return path
    except (OSError, TypeError, ValueError):
        raise ValueError(INVALID) from None


def _run_local(args: list[str], *, timeout: float, output_limit: int) -> tuple[int, bytes]:
    """Capture both streams without logging or storing raw extracted content."""
    process = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True,
        )
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise ValueError(INVALID)
            for key, _ in selector.select(min(remaining, 0.25)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    if len(output) + len(chunk) > output_limit:
                        raise ValueError(TOO_LARGE)
                    output.extend(chunk)
                # stderr is captured and drained, but never exposed or logged.
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ValueError(INVALID)
        return process.wait(timeout=remaining), bytes(output)
    except (OSError, subprocess.SubprocessError):
        raise ValueError(INVALID) from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        selector.close()


def _decode_utf8(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(INVALID) from None
    if any(unicodedata.category(ch) == "Cc" and ch not in "\t\n\r" for ch in text):
        raise ValueError(INVALID)
    return text


def _xml(data: bytes) -> ET.Element:
    _reject_markup(data)
    try:
        parser = ET.XMLPullParser(events=("start", "end"))
        depth = 0
        count = 0
        root = None
        for offset in range(0, len(data), 65536):
            parser.feed(data[offset:offset + 65536])
            for event, element in parser.read_events():
                if event == "start":
                    if root is None:
                        root = element
                    depth += 1
                    count += 1
                    if depth > MAX_XML_DEPTH or count > MAX_XML_ELEMENTS:
                        raise ValueError(TOO_LARGE)
                else:
                    depth -= 1
        parser.close()
        if root is None:
            raise ValueError(INVALID)
        return root
    except ET.ParseError:
        raise ValueError(INVALID) from None


def _zip_parts(data: bytes) -> tuple[dict[str, bytes], list[str]]:
    parts: dict[str, bytes] = {}
    warnings: list[str] = []
    names: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise ValueError(TOO_LARGE)
            for item in entries:
                name = item.filename
                components = name.rstrip("/").split("/")
                if (not name or name.startswith("/") or "\\" in name or ":" in name
                        or any(part in {"", ".", ".."} for part in components)
                        or any(unicodedata.category(ch).startswith("C") for ch in name)
                        or name.casefold() in names
                        or stat.S_ISLNK(item.external_attr >> 16)):
                    raise ValueError(UNSAFE)
                names.add(name.casefold())
                if item.flag_bits & 1 or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise ValueError(UNSAFE)
                total += item.file_size
                if item.file_size > MAX_ZIP_ENTRY_BYTES or total > MAX_ZIP_BYTES:
                    raise ValueError(TOO_LARGE)
                lower = name.casefold()
                if (lower.endswith((".svg", ".html", ".htm", ".xhtml", ".vba"))
                        or "vbaproject" in lower or "/macros/" in lower
                        or "/embeddings/" in lower):
                    raise ValueError(UNSAFE)
                if item.is_dir():
                    continue
                with archive.open(item) as handle:
                    content = handle.read(MAX_ZIP_ENTRY_BYTES + 1)
                if len(content) != item.file_size or len(content) > MAX_ZIP_ENTRY_BYTES:
                    raise ValueError(TOO_LARGE)
                _reject_markup(content)
                if lower.endswith((".xml", ".rels")):
                    root = _xml(content)
                    if lower == "[content_types].xml":
                        for element in root.iter():
                            content_type = element.attrib.get("ContentType", "").casefold()
                            if "macroenabled" in content_type or "vba" in content_type or "oleobject" in content_type:
                                raise ValueError(UNSAFE)
                    if lower.endswith(".rels"):
                        if any(el.attrib.get("TargetMode", "").casefold() == "external" for el in root.iter()):
                            warnings.append("附件含外部关系，未读取外部内容。")
                    parts[name] = content
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, OSError):
        raise ValueError(INVALID) from None
    return parts, list(dict.fromkeys(warnings))


def _ooxml_text(data: bytes, extension: str) -> tuple[str, list[str]]:
    parts, warnings = _zip_parts(data)
    main = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
    if "[Content_Types].xml" not in parts or "_rels/.rels" not in parts or main not in parts:
        raise ValueError(INVALID)
    types = _xml(parts["[Content_Types].xml"])
    expected_type = _DOC_MAIN if extension == ".docx" else _XLS_MAIN
    if not any(el.attrib.get("PartName") == "/" + main and el.attrib.get("ContentType") == expected_type for el in types.iter()):
        raise ValueError(UNSUPPORTED)
    main_root = _xml(parts[main])
    expected_ns = (_W_NS, _W_STRICT_NS) if extension == ".docx" else (_S_NS, _S_STRICT_NS)
    if not any(main_root.tag == "{" + ns + "}" + ("document" if extension == ".docx" else "workbook") for ns in expected_ns):
        raise ValueError(INVALID)
    chunks: list[str] = []
    length = 0

    def append(value: str | None) -> None:
        nonlocal length
        if not value:
            return
        length += len(value.encode("utf-8")) + 1
        if length > MAX_TEXT_BYTES:
            raise ValueError(TOO_LARGE)
        chunks.append(value)

    if extension == ".docx":
        for name, content in parts.items():
            if name == main or re.fullmatch(r"word/(?:header\d+|footer\d+|footnotes|endnotes)\.xml", name):
                for element in _xml(content).iter():
                    if element.tag in {"{" + ns + "}t" for ns in expected_ns}:
                        append(element.text)
    else:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in parts:
            for element in _xml(parts["xl/sharedStrings.xml"]).iter():
                if element.tag in {"{" + ns + "}si" for ns in expected_ns}:
                    shared.append("".join(el.text or "" for el in element.iter() if el.tag in {"{" + ns + "}t" for ns in expected_ns}))
        for name, content in parts.items():
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
                continue
            for cell in _xml(content).iter():
                if cell.tag not in {"{" + ns + "}c" for ns in expected_ns}:
                    continue
                tags = {element.tag.rsplit("}", 1)[-1]: element for element in cell}
                if "f" in tags:
                    warnings.append("公式未执行，缓存值仅作文字线索。")
                if cell.attrib.get("t") == "inlineStr":
                    append("".join(el.text or "" for el in cell.iter() if el.tag in {"{" + ns + "}t" for ns in expected_ns}))
                    continue
                value = tags.get("v")
                if value is None or value.text is None:
                    continue
                if cell.attrib.get("t") == "s":
                    try:
                        index = int(value.text)
                        if index < 0 or index >= len(shared):
                            raise ValueError(INVALID)
                        append(shared[index])
                    except (ValueError, IndexError):
                        raise ValueError(INVALID) from None
                else:
                    append(value.text)
        warnings.append("表格仅抽取文字与保存值，未计算公式或推断房态。")
    return "\n".join(chunks), list(dict.fromkeys(warnings))


def _photo_text(path: Path, extension: str) -> tuple[str, list[str]]:
    probe = shutil.which("ffprobe")
    decoder = shutil.which("ffmpeg")
    if not probe or not decoder:
        raise ValueError(UNAVAILABLE)
    code, output = _run_local(
        [probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-of", "json", str(path)],
        timeout=12, output_limit=128 * 1024,
    )
    try:
        streams = json.loads(output).get("streams", [])
        visual = [stream for stream in streams if stream.get("codec_type") == "video"]
        width, height = int(visual[0]["width"]), int(visual[0]["height"])
        if code != 0 or len(visual) != 1 or width <= 0 or height <= 0:
            raise ValueError(INVALID)
        expected_codec = {".jpg": "mjpeg", ".jpeg": "mjpeg", ".png": "png", ".webp": "webp"}[extension]
        if visual[0].get("codec_name") != expected_codec:
            raise ValueError(UNSUPPORTED)
        if width * height > MAX_PIXELS:
            raise ValueError(TOO_LARGE)
    except (json.JSONDecodeError, KeyError, TypeError, IndexError, OverflowError):
        raise ValueError(INVALID) from None
    code, decoded = _run_local(
        [decoder, "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode", "-threads", "1", "-protocol_whitelist", "file,pipe", "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "framemd5", "-"],
        timeout=18, output_limit=65536,
    )
    if code != 0 or not any(line.strip() and not line.startswith(b"#") and line.count(b",") >= 5 for line in decoded.splitlines()):
        raise ValueError(INVALID)
    ocr = shutil.which("tesseract")
    if not ocr:
        return "", ["照片已完成格式校验；本地文字识别不可用，保留视觉参考。"]
    try:
        code, output = _run_local(
            [ocr, str(path), "stdout", "-l", "chi_sim+eng", "--psm", "11"],
            timeout=18, output_limit=MAX_TEXT_BYTES,
        )
        if code == 0:
            text = _decode_utf8(output).strip()
            if text:
                return text, ["照片仅抽取可识别文字，未理解画面或核实现场条件。"]
    except ValueError:
        pass
    return "", ["照片未取得可用文字，保留视觉参考；未理解画面。"]


def _hints(text: str) -> tuple[list[str], list[str]]:
    topics = [topic for topic, words in _TOPICS if any(word in text for word in words)]
    hints: list[str] = []
    pattern = re.compile(r"(?<!\d)(?:(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)|(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})[日号]?|(\d{1,2})月\s*(\d{1,2})[日号]?)")
    for match in pattern.finditer(text):
        values = match.groups()
        try:
            if values[0] is not None or values[3] is not None:
                year, month, day = (int(value) for value in (values[:3] if values[0] is not None else values[3:6]))
                hint = date(year, month, day).isoformat()
            else:
                month, day = int(values[6]), int(values[7])
                date(2000, month, day)  # A yearless February 29 is a valid hint.
                hint = f"{month}月{day}日"
            if hint not in hints:
                hints.append(hint)
            if len(hints) >= 32:
                break
        except ValueError:
            continue
    return topics, hints


def _validate_pdf(data: bytes, path: Path) -> None:
    # A magic prefix alone does not distinguish a PDF from a renamed payload.
    if not re.match(br"%PDF-(?:1\.[0-7]|2\.0)(?:\r|\n|[ \t])", data):
        raise ValueError(UNSUPPORTED)
    if not re.search(br"%%EOF[\r\n \t]*\Z", data[-1024:]):
        raise ValueError(INVALID)
    validator = shutil.which("pdfinfo")
    if not validator:
        raise ValueError(UNAVAILABLE)
    code, _ = _run_local([validator, str(path)], timeout=12, output_limit=128 * 1024)
    if code != 0:
        raise ValueError(INVALID)


def _inspect_attachment(data: bytes, filename: str, media_type: str, local_path: Path) -> dict:
    """Validate local bytes and return only fixed-vocabulary, unverified hints.

    The original filename and extracted body are never returned. ValueError
    messages are fixed safe strings, without parser or process diagnostics.
    """
    if not isinstance(data, bytes) or not data:
        raise ValueError(INVALID)
    if len(data) > MAX_BYTES:
        raise ValueError(TOO_LARGE)
    if (not isinstance(filename, str) or not filename or len(filename) > 255
            or filename != filename.strip() or any(ch in filename for ch in "/\\:")
            or any(unicodedata.category(ch).startswith("C") for ch in filename)):
        raise ValueError(UNSAFE)
    extension = Path(filename).suffix.casefold()
    if not isinstance(media_type, str):
        raise ValueError(UNSUPPORTED)
    mime = media_type.partition(";")[0].strip().casefold()
    if extension not in _MIMES or mime not in _MIMES[extension]:
        raise ValueError(UNSUPPORTED)
    path = _local_file(data, local_path)
    warnings: list[str] = []
    kind = "photo" if extension in {".jpg", ".jpeg", ".png", ".webp"} else "document"
    if kind == "photo":
        valid_signature = (
            extension in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff")
            or extension == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")
            or extension == ".webp" and len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        )
        if not valid_signature:
            raise ValueError(UNSUPPORTED)
        text, warnings = _photo_text(path, extension)
        status = "text_extracted" if text.strip() else "visual_reference"
    elif extension in {".txt", ".md", ".csv"}:
        _reject_markup(data)
        text = _decode_utf8(data)
        if len(data) > MAX_TEXT_BYTES:
            # Keep extraction bounded; never truncate in the middle of UTF-8.
            text = data[:MAX_TEXT_BYTES].decode("utf-8-sig", errors="ignore")
            warnings.append("文字线索仅检查本地处理限额内的内容。")
        if extension == ".csv":
            warnings.append("CSV 仅按文字读取，未执行公式或推断房态。")
        status = "text_extracted" if text.strip() else "unreadable"
    elif extension in {".docx", ".xlsx"}:
        if not data.startswith(b"PK\x03\x04"):
            raise ValueError(UNSUPPORTED)
        text, warnings = _ooxml_text(data, extension)
        status = "text_extracted" if text.strip() else "unreadable"
    else:
        _validate_pdf(data, path)
        extractor = shutil.which("pdftotext")
        if not extractor:
            text = ""
            warnings.append("本地 PDF 文字抽取不可用，未取得可读文字。")
        else:
            try:
                code, output = _run_local(
                    [extractor, "-f", "1", "-l", "20", "-enc", "UTF-8", "-nopgbrk", str(path), "-"],
                    timeout=15, output_limit=MAX_TEXT_BYTES,
                )
                if code != 0:
                    raise ValueError(INVALID)
                text = _decode_utf8(output)
            except ValueError:
                text = ""
                warnings.append("PDF 未取得可读文字，未解释图像或附件。")
        warnings.append("PDF 仅检查前 20 页可提取文字。")
        status = "text_extracted" if text.strip() else "unreadable"
    topics, date_hints = _hints(text)
    if status == "visual_reference":
        summary = "照片已校验，保留视觉参考；未取得可用文字线索。"
    elif status == "unreadable":
        summary = "附件未取得可读文字，需人工补充说明。"
    elif topics:
        summary = "已提取未核实文字主题：" + "、".join(topics) + "。"
    else:
        summary = "已提取文字，但未识别到固定经营主题。"
    return {
        "kind": kind, "media_type": mime, "extension": extension,
        "read_status": status, "summary": summary, "topics": topics,
        "date_hints": date_hints, "warnings": list(dict.fromkeys(warnings)),
    }


def inspect_attachment(data: bytes, filename: str, media_type: str, local_path: Path) -> dict:
    """Public boundary: parser and CLI diagnostics never reach the caller."""
    try:
        return _inspect_attachment(data, filename, media_type, local_path)
    except Exception as error:
        safe_messages = {INVALID, TOO_LARGE, UNSUPPORTED, UNSAFE, UNAVAILABLE}
        message = str(error) if isinstance(error, ValueError) and str(error) in safe_messages else INVALID
        raise ValueError(message) from None
