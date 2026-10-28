"""Temporary media only: local renderer timing, provenance and real encoding."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.local_os import video_renderer as renderer


def package(duration=15, count=2):
    shots = []
    for i in range(count):
        start = duration * i / count
        end = duration * (i + 1) / count
        shots.append({"start_seconds": start, "end_seconds": end,
                      "visual": "合成测试的待拍画面提纲，不是实际房源",
                      "voiceover": f"第{i + 1}镜：请先核实日期与体验安排。",
                      "asset_id": None, "capture_needed": True})
    srt = "\n\n".join(f"{i + 1}\n{renderer._ts(s['start_seconds'])} --> {renderer._ts(s['end_seconds'])}\n{s['voiceover']}"
                         for i, s in enumerate(shots)) + "\n"
    return {"id": "package-synthetic-test", "hash": "a" * 64, "version": 7,
            "duration_seconds": duration,
            "materials": {"title": "合成测试：日期咨询与文化体验", "storyboard": shots,
                          "voiceover": "\n".join(s["voiceover"] for s in shots), "srt": srt},
            "room_status_context": {"window": {"start_date": "2099-04-12", "end_date": "2099-04-12"}}}


def asset(path, item_id, kind="photo", **kwargs):
    return {"id": item_id, "snapshot_path": str(path), "kind": kind,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "media_type": "image/png" if kind == "photo" else "video/mp4",
            "title": "合成测试素材", "caption": "仅用于临时测试",
            "evidence_status": "historical_photo", "rights_confirmed": False, **kwargs}


class VideoRendererTests(unittest.TestCase):
    def test_supported_durations_and_arbitrary_continuous_shot_counts(self):
        for duration in (15, 30, 60):
            for count in (2, 7, 20):
                with self.subTest(duration=duration, count=count):
                    _, shots, result = renderer._validate_package(package(duration, count))
                    self.assertEqual(len(shots), count)
                    self.assertEqual(result, duration)
        self.assertEqual(renderer._date_label(package()), "2099-04-12")
        self.assertNotIn("11月14", renderer._date_label(package()))

    def test_rejects_gaps_overlaps_bad_duration_or_modified_subtitle(self):
        gap = package(); gap["materials"]["storyboard"][1]["start_seconds"] += 1
        overlap = package(); overlap["materials"]["storyboard"][1]["start_seconds"] -= 1
        changed = package(); changed["materials"]["srt"] += "改写的额外字句"
        wrong_duration = package(); wrong_duration["duration_seconds"] = 90
        one_shot = package(count=1)
        for bad in (gap, overlap, changed, wrong_duration, one_shot):
            with self.assertRaises(renderer.RenderError):
                renderer._validate_package(bad)

    def test_long_subtitles_wrap_without_discarding_confirmed_characters(self):
        if not renderer.renderer_capabilities()["available"]:
            self.skipTest("local media dependencies unavailable")
        value = "先确认入住日和离店日，再核实同行人数、文化体验场次与报价。" * 30
        chunks = renderer._caption_chunks(value, 39, 928)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks).replace("\n", ""), value)

    def test_public_api_has_fixed_encoding_parameters(self):
        with patch.object(renderer, "_render_video", return_value={"ok": True}) as render:
            self.assertEqual(renderer.render_video(job_dir=Path("/synthetic"), package_snapshot={}, assets=[]), {"ok": True})
            self.assertEqual(render.call_args.kwargs["width"], 1080)
            self.assertEqual(render.call_args.kwargs["height"], 1920)
            self.assertEqual(render.call_args.kwargs["fps"], 30)

    def test_snapshot_scope_hash_and_missing_references(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = root / "inputs"; inputs.mkdir()
            source = inputs / "safe.png"
            Image.new("RGB", (16, 16), "green").save(source)
            runner = renderer._Runner(root, None, None)
            shot = package()["materials"]["storyboard"][0]
            shot["asset_id"] = "asset-safe"
            good = asset(source, "asset-safe")
            result = renderer._safe_assets(root, [good], [shot], runner)
            self.assertIn("asset-safe", result)
            bad_hash = {**good, "sha256": "b" * 64}
            with self.assertRaisesRegex(renderer.RenderError, "指纹"):
                renderer._safe_assets(root, [bad_hash], [shot], runner)
            outside = root / "outside.png"; outside.write_bytes(source.read_bytes())
            with self.assertRaisesRegex(renderer.RenderError, "任务边界"):
                renderer._safe_assets(root, [{**good, "snapshot_path": str(outside)}], [shot], runner)
            symlink = inputs / "alias.png"; symlink.symlink_to(source)
            with self.assertRaisesRegex(renderer.RenderError, "受控快照"):
                renderer._safe_assets(root, [{**good, "snapshot_path": str(symlink)}], [shot], runner)
            with self.assertRaisesRegex(renderer.RenderError, "快照缺失"):
                renderer._safe_assets(root, [], [shot], runner)

    def test_media_labels_never_promote_historical_unknown_or_pending(self):
        shot = {"capture_needed": True}
        for evidence in ("historical_photo", "concept", "unknown"):
            result = renderer._labels({"evidence_status": evidence, "rights_confirmed": False}, shot)
            self.assertIn("素材权利待核", result)
            self.assertIn("当期镜头待拍", result)
            self.assertNotIn("现场素材", result)
        self.assertIn("非现场实拍", renderer._labels(None, shot))

    def test_cancel_event_terminates_running_subprocess(self):
        with tempfile.TemporaryDirectory() as folder:
            event = threading.Event()
            runner = renderer._Runner(Path(folder), None, event)
            processes = []
            actual_popen = subprocess.Popen

            def capture(*args, **kwargs):
                process = actual_popen(*args, **kwargs)
                processes.append(process)
                return process

            timer = threading.Timer(.25, event.set)
            timer.start()
            started = time.monotonic()
            with patch.object(renderer.subprocess, "Popen", side_effect=capture):
                with self.assertRaises(renderer.RenderCancelled):
                    runner.run([sys.executable, "-c", "import time; time.sleep(10)"])
            timer.join()
            self.assertLess(time.monotonic() - started, 3)
            self.assertIsNotNone(processes[0].poll())

    @unittest.skipUnless(renderer.renderer_capabilities()["available"], "local renderer dependencies unavailable")
    def test_actual_photo_and_video_render_h264_aac_and_preserves_source_srt(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = root / "inputs"; inputs.mkdir()
            photo = inputs / "photo.png"
            Image.new("RGB", (480, 240), (160, 110, 80)).save(photo)
            video = inputs / "source.mp4"
            created = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
                                      "color=c=0x167d55:s=320x180:r=12", "-t", "1", "-c:v", "libx264",
                                      "-threads", "2", "-pix_fmt", "yuv420p", str(video)], capture_output=True, timeout=20)
            self.assertEqual(created.returncode, 0, created.stderr.decode())
            source = package()
            source["materials"]["storyboard"][0]["asset_id"] = "asset-photo"
            source["materials"]["storyboard"][1]["asset_id"] = "asset-video"
            updates = []
            result = renderer._render_video(job_dir=root, package_snapshot=source,
                                            assets=[asset(photo, "asset-photo"),
                                                    asset(video, "asset-video", "video", evidence_status="unknown")],
                                            width=360, height=640, fps=12,
                                            progress=lambda percent, message: updates.append(percent))
            output = root / "output"
            self.assertEqual((output / "subtitles.srt").read_text(), source["materials"]["srt"])
            receipt_text = (output / "receipt.json").read_text()
            self.assertNotIn(str(root), receipt_text)
            receipt = json.loads(receipt_text)
            self.assertEqual(receipt["package_hash"], source["hash"])
            self.assertFalse(receipt["distribution_ready"])
            self.assertEqual(receipt["provider_calls"], [])
            self.assertEqual(receipt["external_side_effects"], [])
            self.assertEqual(result["metadata"]["duration_seconds"], 15)
            self.assertEqual(result["metadata"]["video_codec"], "h264")
            self.assertEqual(result["metadata"]["audio_codec"], "aac")
            self.assertEqual(result["metadata"]["sha256"], hashlib.sha256((output / "video.mp4").read_bytes()).hexdigest())
            self.assertTrue(any("历史" in warning for warning in result["warnings"]))
            self.assertTrue(any("待拍" in warning for warning in result["warnings"]))
            self.assertEqual(updates[-1], 100)
            with Image.open(output / "poster.jpg") as poster:
                self.assertEqual(poster.size, (360, 640))


if __name__ == "__main__":
    unittest.main()
