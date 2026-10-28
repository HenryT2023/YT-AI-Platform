"""Bounded, local-only rendering of an immutable layer-two material package.

The caller owns authorization and the private job directory. This module reads
only copied media under ``job_dir/inputs`` and never writes a database, calls a
model, speaks a voiceover, or publishes. Script text is laid out, never rewritten.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import time
import wave
from array import array
from functools import lru_cache
from pathlib import Path
from typing import Callable

RENDERER_VERSION = "yantian-local-video-v1"
MAX_SECONDS = 60
MAX_SHOTS = 20
MAX_MEDIA_BYTES = 100 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_JOB_SECONDS = 300
PAPER = (239, 235, 224)
INK = (24, 59, 48)
WARM = (183, 106, 63)
MUTED = (96, 111, 96)
SANS_FONTS = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)
SERIF_FONTS = (
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
)


class RenderError(RuntimeError):
    """A bounded, public-safe render error without private file paths."""


class RenderCancelled(RenderError):
    pass


def _font_path(serif=False):
    choices = (*SERIF_FONTS, *SANS_FONTS) if serif else SANS_FONTS
    return next((p for p in choices if Path(p).is_file()), None)


def renderer_capabilities() -> dict:
    missing = []
    if importlib.util.find_spec("PIL") is None:
        missing.append("Pillow 图像排版依赖")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            missing.append(name)
    if not _font_path():
        missing.append("中文字体")
    return {
        "available": not missing, "missing": missing,
        "renderer_version": RENDERER_VERSION,
        "mode": "local_preview_render", "duration_seconds": [15, 30, 60],
        "max_shots": MAX_SHOTS, "width": 1080, "height": 1920, "fps": 30,
        "photo_supported": True, "video_supported": True,
        "voiceover_supported": False, "original_instrumental": True,
        "publishing_connected": False, "provider_calls": [],
    }


def _hash_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _text(value, limit, label):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise RenderError(label + "超出本地成片输入限制")
    return value


def _ts(seconds):
    millis = round(seconds * 1000)
    return f"{millis // 3600000:02d}:{millis // 60000 % 60:02d}:{millis // 1000 % 60:02d},{millis % 1000:03d}"


def _validate_package(package: dict) -> tuple[dict, list[dict], int]:
    if not isinstance(package, dict):
        raise RenderError("缺少已保存的脚本版本")
    duration = package.get("duration_seconds")
    if type(duration) is not int or duration not in (15, 30, 60):
        raise RenderError("本地成片目前支持 15、30 或 60 秒")
    materials = package.get("materials")
    if not isinstance(materials, dict):
        raise RenderError("缺少脚本和分镜")
    _text(materials.get("title"), 240, "标题")
    _text(materials.get("voiceover"), 20000, "脚本")
    _text(materials.get("srt"), 30000, "字幕")
    shots = materials.get("storyboard")
    if not isinstance(shots, list) or not 2 <= len(shots) <= MAX_SHOTS:
        raise RenderError("成片须有 2 至 20 个连续分镜")
    previous = 0.0
    for shot in shots:
        if not isinstance(shot, dict):
            raise RenderError("分镜格式不完整")
        start, end = shot.get("start_seconds"), shot.get("end_seconds")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or abs(start - previous) > .0001 or end <= start or end > duration
                or end - start < 1 / 30):
            raise RenderError("分镜必须按实际时间连续覆盖完整片长")
        previous = end
        _text(shot.get("visual"), 2000, "分镜画面")
        _text(shot.get("voiceover"), 4000, "分镜字幕")
        if shot.get("asset_id") is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(shot["asset_id"])):
            raise RenderError("分镜素材引用无效")
        if type(shot.get("capture_needed")) is not bool:
            raise RenderError("分镜缺少待拍状态")
        if not shot.get("asset_id") and not shot["capture_needed"]:
            raise RenderError("无素材镜头须保留待拍标识")
    if abs(previous - duration) > .0001:
        raise RenderError("分镜必须连续覆盖完整片长")
    expected_voice = "\n".join(s["voiceover"] for s in shots)
    expected_srt = "\n\n".join(
        f"{i + 1}\n{_ts(s['start_seconds'])} --> {_ts(s['end_seconds'])}\n{s['voiceover']}"
        for i, s in enumerate(shots)
    ) + "\n"
    if materials["voiceover"].strip() != expected_voice.strip() or materials["srt"].strip() != expected_srt.strip():
        raise RenderError("已保存的脚本、分镜台词与字幕须逐字一致")
    if not re.fullmatch(r"[a-f0-9]{64}", str(package.get("hash", ""))):
        raise RenderError("缺少已保存脚本的精确指纹")
    return materials, shots, duration


class _Runner:
    def __init__(self, job_dir, progress, cancel_event):
        self.job_dir = job_dir
        self.progress = progress
        self.cancel_event = cancel_event
        self.deadline = time.monotonic() + MAX_JOB_SECONDS
        self.count = 0

    def check(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise RenderCancelled("本地视频生成已取消")
        if time.monotonic() >= self.deadline:
            raise RenderError("本地视频生成超时，请减少分镜或素材大小后重试")

    def report(self, percent, message):
        self.check()
        if self.progress:
            self.progress(int(percent), message)

    def run(self, args, timeout=120, stdout=False):
        """Poll child processes so shutdown/cancellation also stops encoders."""
        self.check()
        self.count += 1
        out = self.job_dir / ("process-" + str(self.count) + ".out")
        err = self.job_dir / ("process-" + str(self.count) + ".err")
        started = time.monotonic()
        with out.open("xb") as out_handle, err.open("xb") as err_handle:
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out_handle,
                                    stderr=err_handle, shell=False)
            try:
                while proc.poll() is None:
                    self.check()
                    if time.monotonic() - started > timeout:
                        raise RenderError("本地媒体处理超时")
                    time.sleep(.1)
                if proc.returncode or err.stat().st_size:
                    raise RenderError("本地媒体无法完整解码或编码，请检查对应素材")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
        if stdout:
            if out.stat().st_size > 1024 * 1024:
                raise RenderError("媒体元数据超出读取限制")
            return out.read_bytes()
        return b""


def _probe(runner, path, *, source_video=False):
    args = [shutil.which("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
            "-probesize", "5000000", "-analyzeduration", "5000000"]
    if source_video:
        args += ["-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"]
    args += ["-show_entries", "stream=codec_type,codec_name,width,height,duration:format=duration",
             "-of", "json", str(path)]
    try:
        result = json.loads(runner.run(args, timeout=20, stdout=True))
        video = next(s for s in result.get("streams", []) if s.get("codec_type") == "video")
        width, height = int(video["width"]), int(video["height"])
        duration = float(result["format"].get("duration") or video.get("duration") or 0)
        if not 0 < width * height <= MAX_IMAGE_PIXELS or not math.isfinite(duration) or duration <= 0:
            raise ValueError
        return {"width": width, "height": height, "duration_seconds": duration,
                "video_codec": video.get("codec_name"),
                "audio_codecs": [s.get("codec_name") for s in result.get("streams", []) if s.get("codec_type") == "audio"]}
    except (ValueError, KeyError, StopIteration, TypeError):
        raise RenderError("媒体尺寸、片长或编码元数据无法校验") from None


def _safe_assets(job_dir, assets, shots, runner):
    from PIL import Image, ImageOps
    required = {s["asset_id"] for s in shots if s.get("asset_id")}
    if not isinstance(assets, list) or len(assets) > 100:
        raise RenderError("素材快照数量超出限制")
    inputs = job_dir / "inputs"
    if not inputs.is_dir() or inputs.is_symlink():
        if required:
            raise RenderError("缺少受控素材快照目录")
    result = {}
    for asset in assets:
        runner.check()
        if not isinstance(asset, dict) or asset.get("id") not in required:
            continue
        item_id = asset["id"]
        if item_id in result:
            raise RenderError("素材快照引用重复")
        supplied = Path(asset.get("snapshot_path", ""))
        if not supplied.is_absolute() or supplied.is_symlink():
            raise RenderError("素材必须是本任务受控快照")
        try:
            path = supplied.resolve(strict=True)
            relative = path.relative_to(inputs.resolve(strict=True))
            if len(relative.parts) != 1 or not path.is_file():
                raise ValueError
            if not 0 < path.stat().st_size <= MAX_MEDIA_BYTES:
                raise ValueError
        except (OSError, ValueError):
            raise RenderError("素材快照缺失、过大或超出任务边界") from None
        if not re.fullmatch(r"[a-f0-9]{64}", str(asset.get("sha256", ""))) or _hash_file(path) != asset["sha256"]:
            raise RenderError("素材快照指纹与确认版本不一致")
        kind = asset.get("kind")
        meta = {"id": item_id, "sha256": asset["sha256"], "kind": kind,
                "evidence_status": asset.get("evidence_status", "unknown"),
                "rights_confirmed": asset.get("rights_confirmed") is True,
                "title": _text(asset.get("title", ""), 160, "素材标题"),
                "caption": _text(asset.get("caption", ""), 2000, "素材说明"), "path": path}
        if kind == "photo":
            try:
                with Image.open(path) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP", "GIF"} or image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError
                    image.seek(0)
                    image.draft("RGB", (960, 720))
                    image.load()
                    decoded = ImageOps.exif_transpose(image).convert("RGB")
                    decoded.thumbnail((960, 720), Image.Resampling.LANCZOS)
                    meta["image"] = decoded
            except Exception:
                raise RenderError("照片快照无法完整解码或尺寸超出限制") from None
        elif kind == "video":
            with path.open("rb") as handle:
                signature = handle.read(12)
            if len(signature) < 12 or signature[4:8] != b"ftyp":
                raise RenderError("仅支持已校验的 MP4 / MOV 视频快照")
            meta["probe"] = _probe(runner, path, source_video=True)
        else:
            raise RenderError("参考文档不能直接作为成片画面")
        result[item_id] = meta
    if required != set(result):
        raise RenderError("分镜引用的照片或视频快照缺失")
    return result


@lru_cache(maxsize=128)
def _font(size, serif=False):
    from PIL import ImageFont
    return ImageFont.truetype(_font_path(serif), size)


def _lines(value, size, width, serif=False):
    font = _font(size, serif)
    lines, line = [], ""
    for char in value:
        if char == "\n":
            lines.append(line)
            line = ""
        elif line and font.getlength(line + char) > width:
            lines.append(line)
            line = char
        else:
            line += char
    if line or not lines:
        lines.append(line)
    return lines


def _fit_lines(value, size, width, max_lines, min_size, serif=False):
    while size > min_size and len(_lines(value, size, width, serif)) > max_lines:
        size -= 1
    result = _lines(value, size, width, serif)
    if len(result) > max_lines:
        raise RenderError("标题过长，无法完整排入竖版成片，请缩短标题后重新确认")
    return size, result


def _caption_chunks(value, size, width):
    """Split a long exact subtitle into successive cards, never ellipsize it."""
    if not value:
        return [""]
    lines = _lines(value, size, width)
    return ["\n".join(lines[i:i + 5]) for i in range(0, len(lines), 5)]


def _labels(asset, shot):
    if asset:
        status = asset["evidence_status"]
        kind = {"historical_photo": "历史素材参考", "concept": "概念示意", "concept_image": "概念示意",
                "unknown": "来源状态待核", "site_photo": "现场素材 · 本地人工归类"}.get(status, "素材状态待核")
        labels = [kind]
        if not asset["rights_confirmed"]:
            labels.append("素材权利待核")
        if shot["capture_needed"]:
            labels.append("当期镜头待拍")
        return " · ".join(labels)
    return "待拍镜头 · 原创图形示意 · 非现场实拍"


def _date_label(package):
    context = package.get("room_status_context") or {}
    window = context.get("window") or {}
    start, end = window.get("start_date"), window.get("end_date")
    if isinstance(start, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        if isinstance(end, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end) and end != start:
            return start + " — " + end
        return start
    return "已保存脚本 · 本地剪辑预览"


def _original_graphic(width, height, shot_index):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (width, height), (250, 248, 242))
    draw = ImageDraw.Draw(image)
    margin = width * .14
    left, top, right, bottom = margin, height * .1, width - margin, height * .87
    draw.rectangle((left, top, right, bottom), fill=INK, outline=INK, width=max(1, width // 150))
    draw.rectangle((left + 12, top + 12, right - 12, bottom - 12), outline=PAPER, width=max(1, width // 300))
    # A new geometric arrangement is a visual placeholder, never a sourced
    # traditional motif, simulated room, guest, or physical craft object.
    cols, rows = 4, 3
    cell_w, cell_h = (right - left - 60) / cols, (bottom - top - 60) / rows
    for col in range(cols):
        for row in range(rows):
            x, y = left + 30 + (col + .5) * cell_w, top + 30 + (row + .5) * cell_h
            dx, dy = cell_w * .42, cell_h * .42
            points = [(x, y - dy), (x + dx, y), (x, y + dy), (x - dx, y), (x, y - dy)]
            draw.line(points, fill=PAPER, width=max(1, width // 200))
            if (col + row + shot_index) % 2:
                draw.line((x - dx * .4, y, x + dx * .4, y), fill=PAPER, width=max(1, width // 300))
    return image


def _save_png(image, path):
    with path.open("xb") as handle:
        image.save(handle, format="PNG")


def _draw_card(package, title, caption, labels, index, total, width, height):
    from PIL import Image, ImageDraw
    scale = width / 1080
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size, color=INK, serif=False, anchor=None):
        draw.text((round(x * scale), round(y * scale)), value,
                  font=_font(max(10, round(size * scale)), serif), fill=color, anchor=anchor)

    draw.line((round(76 * scale), round(112 * scale), round(128 * scale), round(112 * scale)),
              fill=WARM, width=max(1, round(5 * scale)))
    text(151, 89, "严田庄园", 36)
    text(1004, 95, f"{index:02d} / {total:02d}", 28, MUTED, anchor="ra")
    text(76, 165, _date_label(package), 24, MUTED)
    title_size, title_lines = _fit_lines(title, max(16, round(75 * scale)),
                                        round(928 * scale), 4, max(13, round(30 * scale)), True)
    y = round(258 * scale)
    for line in title_lines:
        draw.text((round(76 * scale), y), line, font=_font(title_size, True), fill=INK)
        y += round(title_size * 1.22)
    draw.rectangle((round(50 * scale), round(638 * scale), round(1030 * scale), round(1390 * scale)), fill=(225, 222, 211))
    draw.rectangle((round(44 * scale), round(628 * scale), round(1036 * scale), round(1380 * scale)), fill=(250, 248, 242))
    # The evidence label sits outside the media window, on every rendered card.
    label_size, label_lines = _fit_lines(labels, max(10, round(25 * scale)), round(928 * scale), 2,
                                        max(10, round(18 * scale)))
    y = round(1405 * scale)
    for line in label_lines:
        draw.text((round(76 * scale), y), line, font=_font(label_size), fill=MUTED)
        y += round(label_size * 1.3)
    y = round(1486 * scale)
    caption_size = max(12, round(39 * scale))
    for line in caption.split("\n"):
        draw.text((round(76 * scale), y), line, font=_font(caption_size), fill=INK)
        y += round(55 * scale)
    draw.line((round(76 * scale), round(1793 * scale), round(1004 * scale), round(1793 * scale)),
              fill=(187, 194, 179), width=max(1, round(scale)))
    text(76, 1824, "本地预览待审 · 未发布", 29)
    text(76, 1876, "日期、房价与体验安排，以人工核实为准", 22, MUTED)
    return image


def _music(path, seconds, runner):
    """A new deterministic instrumental composition with no sampled audio."""
    sample_rate = 24000
    notes = (220.0, 329.6276, 293.6648, 246.9417, 392.0, 329.6276, 440.0, 293.6648)
    stereo = array("h")
    for sample in range(round(sample_rate * seconds)):
        if sample % sample_rate == 0:
            runner.check()
        t = sample / sample_rate
        index = int(t / 1.7)
        value = 0.0
        for note_index in (index - 1, index):
            start = note_index * 1.7
            age = t - start
            if note_index >= 0 and 0 <= age <= 3.6:
                frequency = notes[note_index % len(notes)]
                envelope = (1 - math.exp(-age * 70)) * math.exp(-age * 1.35)
                value += (math.sin(2 * math.pi * frequency * age)
                          + .23 * math.sin(4 * math.pi * frequency * age)) * envelope * .17
        value += math.sin(2 * math.pi * 110 * t) * .006
        fade = min(1, t / 1.2) * min(1, (seconds - t) / 2)
        pcm = round(max(-.9, min(.9, value * fade)) * 32767)
        stereo.extend((pcm, round(pcm * .98)))
    if os.sys.byteorder != "little":
        stereo.byteswap()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(stereo.tobytes())


def _write_exclusive(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as handle:
        handle.write(data)


def render_video(*, job_dir: Path, package_snapshot: dict, assets: list[dict],
                 progress: Callable[[int, str], None] | None = None, cancel_event=None) -> dict:
    """Render fixed 1080×1920/30 fps output in a server-owned private job folder."""
    return _render_video(job_dir=job_dir, package_snapshot=package_snapshot, assets=assets,
                         progress=progress, cancel_event=cancel_event, width=1080, height=1920, fps=30)


def _render_video(*, job_dir, package_snapshot, assets, progress=None, cancel_event=None,
                  width=1080, height=1920, fps=30):
    # Encoding parameters are internal-only; the HTTP contract never accepts them.
    if not (180 <= width <= 1080 and 320 <= height <= 1920 and width * 16 == height * 9
            and width % 2 == 0 and height % 2 == 0 and 10 <= fps <= 30):
        raise RenderError("内部编码尺寸配置无效")
    capabilities = renderer_capabilities()
    if not capabilities["available"]:
        raise RenderError("缺少本地成片能力：" + "、".join(capabilities["missing"]))
    supplied = Path(job_dir)
    if not supplied.is_absolute() or supplied.is_symlink() or not supplied.is_dir():
        raise RenderError("缺少服务器创建的私有任务目录")
    job_dir = supplied.resolve(strict=True)
    output, work = job_dir / "output", job_dir / "_render"
    if output.is_symlink() or work.exists() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise RenderError("任务输出目录已存在，请使用新的任务目录")
    output.mkdir(mode=0o700, exist_ok=True)
    work.mkdir(mode=0o700)
    runner = _Runner(work, progress, cancel_event)
    materials, shots, duration = _validate_package(package_snapshot)
    runner.report(2, "核对已确认脚本与素材快照")
    asset_index = _safe_assets(job_dir, assets, shots, runner)
    warnings = []
    segments, frame_cursor = [], 0
    total_cards = 0
    scale = width / 1080
    for index, shot in enumerate(shots):
        asset = asset_index.get(shot.get("asset_id"))
        label = _labels(asset, shot)
        if label not in warnings and (not asset or asset["evidence_status"] != "site_photo"
                                      or not asset["rights_confirmed"] or shot["capture_needed"]):
            warnings.append(label)
        chunks = _caption_chunks(shot["voiceover"], max(12, round(39 * scale)), round(928 * scale))
        shot_frames = round(shot["end_seconds"] * fps) - round(shot["start_seconds"] * fps)
        if len(chunks) > shot_frames or total_cards + len(chunks) > 80:
            raise RenderError("字幕过长，无法在当前分镜时长内完整排版，请调整后重新确认")
        total_cards += len(chunks)
        elapsed_frames = 0
        for chunk_index, chunk in enumerate(chunks):
            runner.report(5 + 70 * (index + chunk_index / len(chunks)) / len(shots),
                          f"剪辑第 {index + 1} / {len(shots)} 镜")
            frames = round(shot_frames * (chunk_index + 1) / len(chunks)) - round(shot_frames * chunk_index / len(chunks))
            number = len(segments) + 1
            card_path, media_path = work / f"card-{number:03d}.png", work / f"media-{number:03d}.png"
            card = _draw_card(package_snapshot, materials["title"], chunk, label, index + 1, len(shots), width, height)
            _save_png(card, card_path)
            window_w, window_h = round(960 * scale), round(720 * scale)
            if window_w % 2:
                window_w -= 1
            if window_h % 2:
                window_h -= 1
            if not asset or asset["kind"] == "photo":
                from PIL import Image
                if asset:
                    image = asset["image"].copy()
                    image.thumbnail((window_w, window_h), Image.Resampling.LANCZOS)
                    media = Image.new("RGB", (window_w, window_h), (250, 248, 242))
                    media.paste(image, ((window_w - image.width) // 2, (window_h - image.height) // 2))
                else:
                    media = _original_graphic(window_w, window_h, index)
                _save_png(media, media_path)
            args = [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                    "-threads", "2", "-filter_threads", "1", "-filter_complex_threads", "1",
                    "-protocol_whitelist", "file,pipe", "-loop", "1", "-framerate", str(fps), "-i", str(card_path)]
            if asset and asset["kind"] == "video":
                offset = (elapsed_frames / fps) % asset["probe"]["duration_seconds"]
                args += ["-protocol_whitelist", "file,pipe", "-stream_loop", "-1", "-ss", str(offset),
                         "-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0", "-i", str(asset["path"])]
            else:
                args += ["-protocol_whitelist", "file,pipe", "-loop", "1", "-framerate", str(fps), "-i", str(media_path)]
            graph = (f"[1:v]scale={window_w}:{window_h}:force_original_aspect_ratio=decrease,"
                     f"pad={window_w}:{window_h}:(ow-iw)/2:(oh-ih)/2:color=0xfaf8f2,setsar=1,fps={fps}[window];"
                     f"[0:v][window]overlay=x='{round(60 * scale)}+{2 * scale:.6f}*sin(t*0.5)':"
                     f"y='{round(640 * scale)}+{2 * scale:.6f}*cos(t*0.5)':"
                     "eval=frame:shortest=1,format=yuv420p[v]")
            segment = work / f"scene-{number:03d}.mp4"
            args += ["-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames), "-r", str(fps),
                     "-an", "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "21",
                     "-pix_fmt", "yuv420p", "-map_metadata", "-1", str(segment)]
            runner.run(args, timeout=120)
            segments.append(segment)
            elapsed_frames += frames
            frame_cursor += frames
    if frame_cursor != duration * fps:
        raise RenderError("编码分镜未覆盖精确片长")
    runner.report(78, "合成原创轻音乐")
    music_path = work / "original-instrumental.wav"
    _music(music_path, duration, runner)
    concat_path = work / "segments.txt"
    # Every entry is a generated fixed basename. No source path or user text is
    # ever interpolated into a concat file or ffmpeg filter expression.
    _write_exclusive(concat_path, "\n".join("file '" + p.name + "'" for p in segments).encode("ascii"))
    runner.report(87, "合成 MP4 与字幕文件")
    video_path = output / "video.mp4"
    runner.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                "-protocol_whitelist", "file,pipe", "-f", "concat", "-safe", "1", "-i", str(concat_path),
                "-protocol_whitelist", "file,pipe", "-i", str(music_path), "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-threads", "2", "-b:a", "128k", "-ar", "48000",
                "-t", str(duration), "-map_metadata", "-1", "-movflags", "+faststart", str(video_path)], timeout=60)
    _write_exclusive(output / "subtitles.srt", materials["srt"].encode("utf-8"))
    # Extract the real encoded first frame, including the window's subtle
    # movement, rather than assembling a visually different static poster.
    runner.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                "-protocol_whitelist", "file,pipe", "-i", str(video_path), "-frames:v", "1",
                "-threads", "2", str(output / "poster.jpg")], timeout=20)
    runner.report(95, "校验成片编码与播放时长")
    probe = _probe(runner, video_path)
    if (probe["video_codec"] != "h264" or "aac" not in probe["audio_codecs"]
            or probe["width"] != width or probe["height"] != height
            or abs(probe["duration_seconds"] - duration) > .15):
        raise RenderError("成片编码或时长校验未通过")
    # Decode the entire bounded result; a successful container probe alone is
    # insufficient evidence that the encoded frames and audio are playable.
    runner.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                "-threads", "2", "-i", str(video_path), "-f", "null", "-"], timeout=90)
    metadata = {"duration_seconds": duration, "width": width, "height": height, "fps": fps,
                "sha256": _hash_file(video_path), "video_codec": "h264", "audio_codec": "aac"}
    files = {"video": "video.mp4", "poster": "poster.jpg", "receipt": "receipt.json", "subtitles": "subtitles.srt"}
    receipt = {
        "contract": "yantian.local-video-render.v1", "renderer_version": RENDERER_VERSION,
        "package_id": package_snapshot.get("id"), "package_hash": package_snapshot["hash"],
        "package_version": package_snapshot.get("version"), "files": files, "metadata": metadata,
        "subtitle_sha256": hashlib.sha256(materials["srt"].encode("utf-8")).hexdigest(),
        "subtitle_policy": "已保存 SRT 原文保留；画内长字幕仅按行分页，不改写或省略",
        "shots": [{"start_seconds": s["start_seconds"], "end_seconds": s["end_seconds"],
                   "asset_id": s.get("asset_id"), "capture_needed": s["capture_needed"],
                   "evidence_label": _labels(asset_index.get(s.get("asset_id")), s)} for s in shots],
        "assets": [{key: asset[key] for key in ("id", "sha256", "kind", "evidence_status", "rights_confirmed")}
                   for asset in asset_index.values()],
        "warnings": warnings, "audio": "本地原创合成轻音乐；无口播；不使用原片音轨",
        "graphic": "原创几何图形仅作明确标注的待拍视觉示意，不代表现场或传统纹样出处",
        "motion": "完整媒体窗口轻微浮动，不裁切原始画面；分镜按已保存时间精确切换",
        "publication_status": "LOCAL_PREVIEW_REVIEW_PENDING", "distribution_ready": False,
        "provider_calls": [], "external_side_effects": [],
    }
    _write_exclusive(output / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"))
    runner.report(100, "本地预览已生成，等待人工审阅")
    return {"files": files, "metadata": metadata, "warnings": warnings}
