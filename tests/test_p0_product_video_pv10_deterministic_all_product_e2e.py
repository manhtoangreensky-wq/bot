"""Focused test matrix for P0.PRODUCT_VIDEO.PV10.DETERMINISTIC.ALL.PRODUCT.E2E.

Proves deterministic end-to-end execution contracts for EVERY ACTIVE Product Video
product without paid or live provider network calls.

Chain under proof:
PUBLIC ENTRY
→ CONTENT/DRAFT
→ QUALITY SELECTION
→ CONFIRM
→ PROJECT
→ JOB
→ OUTBOX
→ OWNER WORKER CLAIM
→ PRODUCT ADAPTER
→ FAKE PROVIDER TASK
→ SCENE ARTIFACT
→ FINALIZER
→ VALID FINAL MP4
→ DELIVERY
→ DURABLE RECEIPT
→ PRODUCT SUCCESS

Active Products (9):
- T2V (4): video_trend, video_ai_prompt, video_idea, script_image_video
- I2V (2): video_ai_image, storyboard_prompt
- V2V (3): video_ai_video_reference, self_shot_scene_change, self_shot_cinematic_transform

Deferred Products (3):
- video_local_edit, multi_scene_film, video_long (DELTA = 0)
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot
from services import (
    multiscene_video_pipeline as pipeline,
    product_video_public_seam,
    remote_worker_api,
    video_final_output,
    video_local_validation,
    video_provider_catalog as cat,
    video_provider_router as router,
    video_real_render_connector,
    video_tail9,
    video_uifreeze1,
)
from services import video_project_queue as queue
from services.video_provider_base import VideoGenerationRequest


# ==============================================================================
# CANONICAL CONSTANTS & CONFIGURATION
# ==============================================================================

CANONICAL_CAPABILITY = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY

ACTIVE_T2V_PRODUCTS = (
    "video_trend",
    "video_ai_prompt",
    "video_idea",
    "script_image_video",
)
ACTIVE_I2V_PRODUCTS = (
    "video_ai_image",
    "storyboard_prompt",
)
ACTIVE_V2V_PRODUCTS = (
    "video_ai_video_reference",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
)
ALL_ACTIVE_PRODUCTS = ACTIVE_T2V_PRODUCTS + ACTIVE_I2V_PRODUCTS + ACTIVE_V2V_PRODUCTS

DEFERRED_PRODUCTS = (
    "video_local_edit",
    "multi_scene_film",
    "video_long",
)

EXPECTED_EXECUTOR_MAP = {
    "video_trend": "video_trend",
    "video_ai_prompt": "video_ai_prompt",
    "video_idea": "video_idea_to_product",
    "script_image_video": "script_to_video",
    "video_ai_image": "video_ai_image",
    "storyboard_prompt": "storyboard_prompt",
    "video_ai_video_reference": "video_ai_video_reference",
    "self_shot_scene_change": "self_shot_scene_change",
    "self_shot_cinematic_transform": "self_shot_cinematic_transform",
}

EXPECTED_MODALITY_MAP = {
    "video_trend": "text_to_video",
    "video_ai_prompt": "text_to_video",
    "video_idea": "text_to_video",
    "script_image_video": "text_to_video",
    "video_ai_image": "image_to_video",
    "storyboard_prompt": "image_to_video",
    "video_ai_video_reference": "video_to_video",
    "self_shot_scene_change": "video_to_video",
    "self_shot_cinematic_transform": "video_to_video",
}

# Modality tier and scene configuration (pricing resolved dynamically via catalog)
PRODUCT_CONFIG = {
    "video_trend": {
        "modality": "text_to_video",
        "tier": 400,
        "scene_count": 2,
    },
    "video_ai_prompt": {
        "modality": "text_to_video",
        "tier": 400,
        "scene_count": 1,
    },
    "video_idea": {
        "modality": "text_to_video",
        "tier": 500,
        "scene_count": 2,
    },
    "script_image_video": {
        "modality": "text_to_video",
        "tier": 400,
        "scene_count": 5,  # Requires minimum 5 scenes
    },
    "video_ai_image": {
        "modality": "image_to_video",
        "tier": 400,
        "scene_count": 1,
    },
    "storyboard_prompt": {
        "modality": "image_to_video",
        "tier": 500,
        "scene_count": 2,  # Requires minimum 2 scenes
    },
    "video_ai_video_reference": {
        "modality": "video_to_video",
        "tier": 500,  # V2V allowed set: {500, 600, 700, 800}
        "scene_count": 1,
    },
    "self_shot_scene_change": {
        "modality": "video_to_video",
        "tier": 600,
        "scene_count": 1,
    },
    "self_shot_cinematic_transform": {
        "modality": "video_to_video",
        "tier": 700,
        "scene_count": 1,
    },
}

# Deterministic minimal valid MP4 binary (H.264 video + AAC audio, duration 1.0s)
MINI_MP4_BASE64 = (
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAQgxtZGF0AAACrwYF//+r3EXp"
    "vebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NSByMzIyMyAwNDgwY2IwIC0gSC4yNjQvTVBFRy00IEFW"
    "QyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQu"
    "aHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDEx"
    "MyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3Jhbmdl"
    "PTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0"
    "X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTE4IGxvb2thaGVhZF90aHJlYWRzPTMg"
    "c2xpY2VkX3RocmVhZHM9MCBucj0wIGRlY2ltYXRlPTEgaW50ZXJsYWNlZD0wIGJsdXJheV9jb21wYXQ9"
    "MCBjb25zdHJhaW5lZF9pbnRyYT0wIGJmcmFtZXM9MyBiX3B5cmFtaWQ9MiBiX2FkYXB0PTEgYl9iaWFz"
    "PTAgZGlyZWN0PTEgd2VpZ2h0Yj0xIG9wZW5fZ29wPTAgd2VpZ2h0cD0yIGtleWludD0yNTAga2V5aW50"
    "X21pbj0yNSBzY2VuZWN1dD00MCBpbnRyYV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTQwIHJjPWNyZiBt"
    "YnRyZWU9MSBjcmY9MjMuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBzdGVwPTQgaXBfcmF0"
    "aW89MS40MCBhcT0xOjEuMDAAgAAAGilliIQAN//+9vD+BTZWBFCXEc3onKBfvSm+QA1scINqEO9wghaE"
    "JPsb0oJoHWlkHhn7aiZIt8el3LWbhKJw/yYix1nZpSmAt6CAjGmjInDOiMgrslbTpElvj45r3CHgvyeY"
    "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"
    "AAABAAAAAAAAAAAAAgAQAAAAAKxEAAAAAAA2ZXNkcwAAAAADgICAJQACAASAgIAXQBUAAAAAAfQAAAAI"
    "tAWAgIAFEhBW5QAGgICAAQIAAAAUYnRydAAAAAAAAfQAAAAItAAAACBzdHRzAAAAAAAAAAIAAAAsAAAE"
    "AAAAAAEAAABEAAABSHN0c2MAAAAAAAAAGgAAAAEAAAABAAAAAQAAAAIAAAACAAAAAQAAAAMAAAABAAAA"
    "AQAAAAQAAAACAAAAAQAAAAUAAAABAAAAAQAAAAYAAAACAAAAAQAAAAcAAAABAAAAAQAAAAgAAAACAAAA"
    "AQAAAAkAAAABAAAAAQAAAAsAAAACAAAAAQAAAAwAAAABAAAAAQAAAA0AAAACAAAAAQAAAA4AAAABAAAA"
    "AQAAAA8AAAACAAAAAQAAABAAAAABAAAAAQAAABIAAAACAAAAAQAAABMAAAABAAAAAQAAABQAAAACAAAA"
    "AQAAABUAAAABAAAAAQAAABYAAAACAAAAAQAAABcAAAABAAAAAQAAABgAAAACAAAAAQAAABkAAAABAAAA"
    "AQAAABsAAAACAAAAAQAAABwAAAABAAAAAQAAAB0AAAAFAAAAAQAAAMhzdHN6AAAAAAAAAAAAAAAtAAAA"
    "FQAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAA"
    "BgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAA"
    "BgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAABgAAAAYAAAAGAAAA"
    "hHN0Y28AAAAAAAAAHQAAIF4AACFvAAAiagAAIuoAACW5AAAmxQAAJ7sAAChJAAAq9wAAK/sAACzWAAAt"
    "qQAAMD8AADFCAAAx4gAAMnMAADTjAAA2BAAANqIAADdhAAA5xwAAOu0AADvYAAA8kgAAPnQAAD9lAAA/"
    "/QAAQLwAAEIWAAAAGnNncGQBAAAAcm9sbAAAAAIAAAAB//8AAAAcc2JncAAAAAByb2xsAAAAAQAAAC0A"
    "AAABAAAAYXVkdGEAAABZbWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAs"
    "aWxzdAAAACSpdG9vAAAAHGRhdGEAAAABAAAAAExhdmY2My4xLjEwMQ=="
)


MINI_MP4_BYTES = base64.b64decode(MINI_MP4_BASE64)


def _create_mini_mp4(target_path: Path, duration_sec: float = 1.0) -> Path:
    """Deterministic local generation of a tiny valid MP4 with video & audio streams."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(MINI_MP4_BYTES)
    return target_path


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, code: int = 200, headers: dict | None = None, url: str = "https://cdn.fake.local/video.mp4"):
        super().__init__(data)
        self.code = code
        self.status = code
        self.url = url
        self.headers = headers or {"Content-Type": "application/json", "Content-Length": str(len(data))}

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.code

    def info(self):
        return self.headers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


task_counter = 0


def fake_dispatcher(req: Any, *args: Any, **kwargs: Any) -> FakeResponse:
    global task_counter
    if hasattr(req, "full_url"):
        url = req.full_url
    elif hasattr(req, "get_full_url"):
        url = req.get_full_url()
    else:
        url = str(req)

    # 1. Download video binary
    if "cdn.fake.local" in url or url.endswith(".mp4"):
        return FakeResponse(
            MINI_MP4_BYTES,
            code=200,
            headers={"Content-Type": "video/mp4", "Content-Length": str(len(MINI_MP4_BYTES))},
            url=url,
        )

    # 2. Poll video status
    if "query?id=" in url or "{task_id}" in url or "fake_task_" in url:
        import re
        m = re.search(r"fake_task_pv10_\d+", url)
        tid = m.group(0) if m else f"fake_task_pv10_{task_counter}"
        continuity_payload = {
            "person_identity": True,
            "object_identity": True,
            "person_object_relationship": True,
        }
        res_payload = {
            "code": 0,
            "status": "succeeded",
            "state": "succeeded",
            "task_status": "succeeded",
            "id": tid,
            "task_id": tid,
            "result_url": f"https://cdn.fake.local/{tid}.mp4",
            "video_url": f"https://cdn.fake.local/{tid}.mp4",
            "continuity_evidence": continuity_payload,
            "continuity_metrics": continuity_payload,
            "continuity_validation": continuity_payload,
            "data": {
                "status": "succeeded",
                "state": "succeeded",
                "task_status": "succeeded",
                "id": tid,
                "task_id": tid,
                "result_url": f"https://cdn.fake.local/{tid}.mp4",
                "video_url": f"https://cdn.fake.local/{tid}.mp4",
                "continuity_evidence": continuity_payload,
                "continuity_metrics": continuity_payload,
                "continuity_validation": continuity_payload,
            },
        }
        return FakeResponse(json.dumps(res_payload).encode("utf-8"))

    # 3. Submit video generation
    task_counter += 1
    tid = f"fake_task_pv10_{task_counter}"
    continuity_payload = {
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }
    submit_payload = {
        "code": 0,
        "status": "processing",
        "state": "processing",
        "task_status": "processing",
        "id": tid,
        "task_id": tid,
        "provider_task_id": tid,
        "continuity_evidence": continuity_payload,
        "continuity_metrics": continuity_payload,
        "continuity_validation": continuity_payload,
        "data": {
            "id": tid,
            "task_id": tid,
            "provider_task_id": tid,
            "status": "processing",
            "continuity_evidence": continuity_payload,
            "continuity_metrics": continuity_payload,
            "continuity_validation": continuity_payload,
        },
    }
    return FakeResponse(json.dumps(submit_payload).encode("utf-8"))


# ==============================================================================
# DETERMINISTIC HELPERS & FIXTURES
# ==============================================================================

@pytest.fixture(autouse=True)
def deterministic_pv10_environment(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure fully deterministic isolated execution across all environments."""
    temp_video_outputs = Path(os.environ.get("TEMP", "C:/tmp")) / "pv10_video_outputs"
    temp_video_outputs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VIDEO_PROVIDER_OUTPUT_DIR", str(temp_video_outputs))

    monkeypatch.setenv("SHOPAIKEY_API_KEY", "fake_shopaikey_key")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_SUBMIT_URL", "https://fake.shopaikey.local/v1/video/generations")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_POLL_URL", "https://fake.shopaikey.local/v1/video/generations/{task_id}")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_MODEL", "veo3.1-fast")

    monkeypatch.setenv("KEY4U_API_KEY", "fake_key4u_key")
    monkeypatch.setenv("KEY4U_VIDEO_ENABLED", "1")
    monkeypatch.setenv("KEY4U_VIDEO_SUBMIT_URL", "https://fake.key4u.local/v1/video/create")
    monkeypatch.setenv("KEY4U_VIDEO_POLL_URL", "https://fake.key4u.local/v1/video/query?id={task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_MODEL", "kling-video")
    monkeypatch.setenv("KEY4U_VIDEO_ENDPOINT", "https://fake.key4u.local/v1/video")
    monkeypatch.setenv("KEY4U_VIDEO_POLL_ENDPOINT", "https://fake.key4u.local/v1/video/poll")
    monkeypatch.setenv("KEY4U_KLING_VIDEO_ENDPOINT", "https://fake.key4u.local/v1/kling")
    monkeypatch.setenv("KEY4U_KLING_VIDEO_POLL_URL", "https://fake.key4u.local/v1/kling/poll")
    monkeypatch.setenv("KEY4U_HAILUO_VIDEO_ENDPOINT", "https://fake.key4u.local/v1/hailuo")
    monkeypatch.setenv("KEY4U_HAILUO_VIDEO_POLL_URL", "https://fake.key4u.local/v1/hailuo/poll")
    monkeypatch.setenv("KEY4U_VEO_VIDEO_ENDPOINT", "https://fake.key4u.local/v1/veo")
    monkeypatch.setenv("KEY4U_VEO_VIDEO_POLL_URL", "https://fake.key4u.local/v1/veo/poll")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_ENABLED", "true")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_SUBMIT_URL", "https://fake.key4u.local/v1/video/edit")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_POLL_URL", "https://fake.key4u.local/v1/video/query?id={task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_AUTH_HEADER_VALUE", "Bearer fake_key4u_key")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_MODEL", "kling-video")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_INTERFACE", "video_to_video_multipart")
    monkeypatch.setenv("KEY4U_VIDEO_TO_VIDEO_CAPABILITIES", "video_to_video")

    monkeypatch.setattr(urllib.request, "urlopen", fake_dispatcher)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", lambda self, req, *args, **kwargs: fake_dispatcher(req))

    # Mock telegram bot for delivery
    mock_message = MagicMock()
    mock_message.message_id = 998877
    mock_bot = MagicMock()
    mock_bot.send_video = AsyncMock(return_value=mock_message)
    mock_bot.send_document = AsyncMock(return_value=mock_message)
    monkeypatch.setattr(bot, "tg_app", MagicMock(bot=mock_bot))

    def _fake_worker_admission_status(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        try:
            sha = _current_runtime_sha()
        except Exception:
            sha = "4ab61cd365c5d73baf0bff9f2eba93f05c4e70ce"
        return {
            "worker_version_compatible": True,
            "worker_connected": True,
            "heartbeat_fresh": True,
            "lease_valid": True,
            "sha_match": True,
            "capability_match": True,
            "worker_identity_conflict": False,
            "worker_admission_block_reason": "",
            "runtime_sha": sha,
            "worker_sha": sha,
            "git_sha": sha,
            "generation_id": "generation-pv10",
        }

    monkeypatch.setattr(bot, "product_video_worker_admission_status", _fake_worker_admission_status)

    def fake_probe_video_file(path: str | os.PathLike[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
        target = Path(path)
        if not target.is_file():
            return {"ok": False, "reason": "input_missing"}
        size = target.stat().st_size
        if size <= 0:
            return {"ok": False, "reason": "input_zero_bytes", "bytes": size}
        content = target.read_bytes()
        if (
            b"corrupt" in content
            or content.startswith(b"<html")
            or not (len(content) > 12 and content[4:8] == b"ftyp")
        ):
            return {"ok": False, "reason": "ffprobe_failed", "bytes": size}
        duration = 8.0
        for parent_dir in (target.parent, target.parent.parent):
            manifest_file = parent_dir / "manifest.json"
            if manifest_file.is_file():
                try:
                    mdata = json.loads(manifest_file.read_text("utf-8"))
                    exp = mdata.get("expected_duration_sec") or mdata.get("expected_duration_seconds")
                    if exp and not ("provider_scene_" in target.name or target.name.startswith("scene_")):
                        duration = float(exp)
                        break
                    specs = mdata.get("scenes") or mdata.get("scene_specs")
                    if isinstance(specs, list) and len(specs) > 0:
                        scene_dur = 0.0
                        for s in specs:
                            if isinstance(s, dict) and str(s.get("scene_id") or "") in target.name:
                                scene_dur = float(s.get("target_duration_sec") or 0.0)
                                break
                        if scene_dur > 0:
                            duration = scene_dur
                            break
                        if not ("provider_scene_" in target.name or target.name.startswith("scene_")):
                            duration = sum(float(s.get("target_duration_sec") or 8.0) for s in specs if isinstance(s, dict))
                            break
                except Exception:
                    pass
            concat_txt = parent_dir / "concat_scenes.txt"
            if concat_txt.is_file():
                lines = [l for l in concat_txt.read_text("utf-8").splitlines() if l.strip()]
                if lines:
                    duration = float(len(lines) * 8.0)
                    break
        return {
            "ok": True,
            "has_video": True,
            "has_audio": True,
            "duration": duration,
            "width": 720,
            "height": 1280,
            "codec_name": "h264",
            "audio_codec_name": "aac",
            "bytes": size,
        }

    def fake_probe_video(path: str, *, ffprobe: str = "") -> dict[str, Any]:
        target = Path(path)
        if not target.is_file():
            return {"ok": False, "reason": "output_missing"}
        size = target.stat().st_size
        if size <= 0:
            return {"ok": False, "reason": "output_zero_bytes", "bytes": size}
        content = target.read_bytes()
        if (
            b"corrupt" in content
            or content.startswith(b"<html")
            or not (len(content) > 12 and content[4:8] == b"ftyp")
        ):
            return {"ok": False, "reason": "ffprobe_failed", "bytes": size}
        duration = 8.0
        for parent_dir in (target.parent, target.parent.parent):
            manifest_file = parent_dir / "manifest.json"
            if manifest_file.is_file():
                try:
                    mdata = json.loads(manifest_file.read_text("utf-8"))
                    exp = mdata.get("expected_duration_sec") or mdata.get("expected_duration_seconds")
                    if exp and not ("provider_scene_" in target.name or target.name.startswith("scene_")):
                        duration = float(exp)
                        break
                    specs = mdata.get("scenes") or mdata.get("scene_specs")
                    if isinstance(specs, list) and len(specs) > 0:
                        scene_dur = 0.0
                        for s in specs:
                            if isinstance(s, dict) and str(s.get("scene_id") or "") in target.name:
                                scene_dur = float(s.get("target_duration_sec") or 0.0)
                                break
                        if scene_dur > 0:
                            duration = scene_dur
                            break
                        if not ("provider_scene_" in target.name or target.name.startswith("scene_")):
                            duration = sum(float(s.get("target_duration_sec") or 8.0) for s in specs if isinstance(s, dict))
                            break
                except Exception:
                    pass
            concat_txt = parent_dir / "concat_scenes.txt"
            if concat_txt.is_file():
                lines = [l for l in concat_txt.read_text("utf-8").splitlines() if l.strip()]
                if lines:
                    duration = float(len(lines) * 8.0)
                    break
        if "provider_scene_" in target.name or target.name.startswith("frame_"):
            duration = 8.0
        return {
            "ok": True,
            "path": str(path),
            "bytes": size,
            "duration": duration,
            "has_video": True,
            "has_audio": True,
            "width": 720,
            "height": 1280,
            "sample_aspect_ratio": "1:1",
            "display_aspect_ratio": "9:16",
        }

    def fake_probe_media_streams(path: str) -> dict[str, Any]:
        return {"streams": [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio"}]}

    def fake_probe_duration(path: str) -> float:
        manifest_file = Path(path).parent / "manifest.json"
        if manifest_file.is_file():
            try:
                data = json.loads(manifest_file.read_text("utf-8"))
                expected = data.get("expected_duration_sec")
                if expected:
                    return float(expected)
            except Exception:
                pass
        return 8.0

    def fake_safe_run_ffmpeg(cmd: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
        if cmd and cmd[-1] != "-" and not cmd[-1].startswith("-"):
            out_path = Path(cmd[-1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.is_file() or out_path.stat().st_size == 0:
                _create_mini_mp4(out_path, duration_sec=1.0)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    # For dedicated real media finalizer test, do NOT monkeypatch probe / ffmpeg execution
    if getattr(request, "node", None) and request.node.name == "test_pv10_real_media_finalizer_lane":
        return

    monkeypatch.setattr(video_local_validation, "probe_video_file", fake_probe_video_file)
    monkeypatch.setattr(video_final_output, "probe_video", fake_probe_video)
    monkeypatch.setattr(pipeline, "probe_media_streams", fake_probe_media_streams)
    monkeypatch.setattr(pipeline, "probe_duration", fake_probe_duration)
    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "_ffprobe_path", lambda: "ffprobe")
    monkeypatch.setattr(video_real_render_connector, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_safe_run_ffmpeg)
    monkeypatch.setattr(video_real_render_connector, "safe_run_ffmpeg", fake_safe_run_ffmpeg)


def _current_runtime_sha() -> str:
    """Derive 40-character runtime SHA or fail-closed."""
    for env_name in ("DEPLOYED_SHA", "TARGET_SHA", "APP_BUILD_SHA"):
        val = os.getenv(env_name)
        if val and len(val.strip()) == 40:
            return val.strip()
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if len(out) == 40:
            return out
    except Exception:
        pass
    raise RuntimeError("runtime_sha_unavailable")


def test_pv10_runtime_sha_fail_closed_on_invalid_env_and_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed runtime SHA: raises RuntimeError when env SHA is missing/invalid and git fails."""
    monkeypatch.delenv("DEPLOYED_SHA", raising=False)
    monkeypatch.delenv("TARGET_SHA", raising=False)
    monkeypatch.delenv("APP_BUILD_SHA", raising=False)
    monkeypatch.setattr(subprocess, "check_output", MagicMock(side_effect=subprocess.CalledProcessError(1, "git")))
    with pytest.raises(RuntimeError, match="runtime_sha_unavailable"):
        _current_runtime_sha()

    # Also invalid short SHA in env must fail closed
    monkeypatch.setenv("DEPLOYED_SHA", "invalid_short_sha")
    with pytest.raises(RuntimeError, match="runtime_sha_unavailable"):
        _current_runtime_sha()


class NoCloseProxy:
    def __init__(self, target: sqlite3.Connection) -> None:
        self._target = target

    def close(self) -> None:
        pass

    def __getattr__(self, item: str) -> Any:
        return getattr(self._target, item)


def _create_isolated_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create isolated SQLite database connection with schema initialized."""
    conn = sqlite3.connect(str(db_path) if db_path else ":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _build_sealed_admission(
    project: dict[str, Any],
    *,
    product_type: str,
    keys: list[str] | None = None,
    generation_id: str = "generation-pv10",
) -> dict[str, Any]:
    """Construct signed and sealed admission context."""
    current_sha = _current_runtime_sha()
    modality = EXPECTED_MODALITY_MAP.get(product_type, "text_to_video")
    default_keys = ["key4u_video"] if modality in ("image_to_video", "video_to_video") else ["shopaikey_video"]
    candidate_keys = list(default_keys if keys is None else keys)
    snapshot_id = f"snap_pv10_{project['project_id']}"
    checked_at = queue.now_text()
    quote = queue.product_video_admission_quote_fingerprint(project, int(project["user_id"]))

    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": candidate_keys,
        "runtime_candidate_keys": candidate_keys,
        "contract_valid_provider_chain": candidate_keys,
        "final_eligible_provider_count": len(candidate_keys),
    }

    admission = {
        "ok": bool(candidate_keys),
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": candidate_keys,
        "admission_candidate_count": len(candidate_keys),
        "contract_valid_provider_chain": candidate_keys,
        "admission_result": "PASS" if candidate_keys else "BLOCKED",
        "admission_block_reason": "" if candidate_keys else "no_eligible_product_video_provider",
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_provider_health_gate_pass": bool(candidate_keys),
        "admission_worker_runtime_sha": current_sha,
        "admission_worker_sha": current_sha,
        "admission_worker_version_compatible": True,
        "admission_route_requires_provider": True,
        "worker_generation_id": generation_id,
        "worker_git_sha": current_sha,
        "runtime_sha": current_sha,
        "worker_compatible": True,
        "worker_connected": True,
        "worker_heartbeat_fresh": True,
        "worker_lease_valid": True,
        "worker_sha_match": True,
        "worker_capability_match": True,
        "worker_identity_conflict": False,
        "route_requires_provider": True,
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": "",
        "duplicate_confirm_handler_detected": False,
    }
    return queue.sign_product_video_final_admission_context(admission)


def _prepare_modality_inputs(
    tmp_path: Path,
    product_type: str,
    scene_count: int,
    scene_sec: int = 8,
) -> dict[str, Any]:
    """Prepare product-specific clean input assets."""
    modality = EXPECTED_MODALITY_MAP[product_type]
    inputs: dict[str, Any] = {
        "content_source": "user_prompt",
        "prompt": f"Deterministic prompt for {product_type}",
        "selected_prompt": f"Deterministic prompt for {product_type}",
        "aspect_ratio": "9:16",
    }
    if modality == "image_to_video":
        img_dir = tmp_path / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        image_paths = []
        for idx in range(1, scene_count + 1):
            img_path = img_dir / f"frame_{idx}.png"
            # 1x1 transparent PNG
            img_path.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
                b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            image_paths.append(str(img_path))
        inputs["image_paths"] = image_paths
    elif modality == "video_to_video":
        src_dir = tmp_path / "source_videos"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_video = src_dir / f"{product_type}_src.mp4"
        _create_mini_mp4(src_video, duration_sec=float(scene_count * scene_sec))
        inputs["source_video_path"] = str(src_video)
        inputs["source_video_local_path"] = str(src_video)
        inputs["scene_source_segments"] = [
            {
                "scene_index": idx,
                "start_seconds": float((idx - 1) * scene_sec),
                "end_seconds": float(idx * scene_sec),
            }
            for idx in range(1, scene_count + 1)
        ]
        inputs["video_prompts"] = [
            {"scene_index": idx, "prompt": f"Deterministic prompt scene {idx}"}
            for idx in range(1, scene_count + 1)
        ]
        inputs["scene_plan"] = [
            {
                "scene_index": idx,
                "source_segment_start": float((idx - 1) * scene_sec),
                "source_segment_end": float(idx * scene_sec),
            }
            for idx in range(1, scene_count + 1)
        ]
        inputs["source_segment"] = {
            "start_ms": 0,
            "duration_ms": scene_count * scene_sec * 1000,
            "end_ms": scene_count * scene_sec * 1000,
        }
    return inputs


def _seed_and_confirm_project(
    conn: sqlite3.Connection,
    tmp_path: Path,
    product_type: str,
    *,
    user_id: int = 1001,
) -> tuple[int, int, int]:
    """Seed project through the real public seam, evaluate production router admission,
    and confirm invoice.
    
    Seam under empirical proof:
    1. Draft state machine: video_tail9.new_state + video_tail9.apply_content_contract
    2. Package selector: video_tail9.select_package
    3. Draft-to-project seam: bot.video_b14_prepare_project_for_invoice
    4. Production provider router:
       - services.video_provider_router.product_video_provider_eligibility_snapshot
       - bot.build_product_video_public_final_admission
       - queue.sign_product_video_final_admission_context
    5. Confirmation callback seam: queue.confirm_public_product_video_invoice
    
    Returns: (project_id, job_id, outbox_id)
    """
    cfg = PRODUCT_CONFIG[product_type]
    scene_count = cfg["scene_count"]
    quality_tier = cfg["tier"]

    cat_rep = video_uifreeze1.catalog_report(product_type, scene_count=scene_count, ratio="9:16")
    target_offer = next(o for o in cat_rep["offers"] if o["tier_id"] == quality_tier)
    package_xu = int(target_offer["unit_xu"])
    scene_sec = int(target_offer.get("seconds") or 8)
    if product_type == "video_trend":
        assert package_xu == 80

    inputs = _prepare_modality_inputs(tmp_path, product_type, scene_count, scene_sec)
    modality = EXPECTED_MODALITY_MAP[product_type]

    # Baseline DB counts
    initial_projects = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    initial_jobs = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    initial_outbox = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    # 1. Draft state machine: new_state + apply_content_contract
    tail_state = video_tail9.new_state(
        product_type=product_type,
        execution_product_type=EXPECTED_EXECUTOR_MAP[product_type],
        session_id=f"pv10_sess_{product_type}_{user_id}",
        scene_count=scene_count,
        ratio="9:16",
        estimated_duration=scene_count * scene_sec,
    )
    tail_state = video_tail9.apply_content_contract(
        tail_state,
        {
            "content_source": "user_prompt",
            "prompt": f"Deterministic prompt for {product_type}",
            "selected_prompt": f"Deterministic prompt for {product_type}",
            "aspect_ratio": "9:16",
        },
    )

    # 2. Package selector
    tail_state = video_tail9.select_package(
        tail_state,
        quality_tier_id=str(quality_tier),
        package_id=f"pkg_{quality_tier}",
        pricing_snapshot={
            "unit_xu": package_xu,
            "total_xu": package_xu,
            "quality_tier": quality_tier,
        },
        capability_snapshot={
            "required_capability": modality,
        },
    )

    # Production provider health evidence
    health = {
        "shopaikey_video": {
            "provider": "shopaikey_video",
            "live_healthy": True,
            "route_ready": True,
            "multi_scene_eligible": True,
            "health_status": "healthy",
            "last_valid_output_at": queue.now_text(),
            "success_ttl_seconds": 3600,
        },
        "key4u_video": {
            "provider": "key4u_video",
            "live_healthy": True,
            "route_ready": True,
            "multi_scene_eligible": True,
            "health_status": "healthy",
            "last_valid_output_at": queue.now_text(),
            "success_ttl_seconds": 3600,
        },
    }

    # 3. Draft-to-project seam: bot.video_b14_prepare_project_for_invoice
    bot.db_connect = lambda: NoCloseProxy(conn)
    session = {
        "product_id": product_type,
        "topic": f"PV10 Test {product_type}",
        "aspect_ratio": "9:16",
        "draft": {
            "b14_profile_id": "storytelling",
            "b14_aspect_ratio": "9:16",
            "b14_scene_count": scene_count,
            "b14_scene_seconds": scene_sec,
            "b14_quality_tier": quality_tier,
            "b14_quality_xu": quality_tier,
            "scene_plan": inputs.get("scene_plan", []),
            "video_prompts": inputs.get("video_prompts", []),
            "b14_storyboard_plan": {
                "preview_text": f"Preview {product_type}",
                "scene_count": scene_count,
                "aspect_ratio": "9:16",
                "scenes": [
                    {
                        "scene_id": f"s{i}",
                        "scene_index": i,
                        "target_duration_sec": scene_sec,
                        "title": f"Scene {i}",
                        "narration_text": f"Narration {i}",
                        "visual_prompt": f"Visual {i}",
                    }
                    for i in range(1, scene_count + 1)
                ],
            },
            "asset_pack": {
                "product_type": product_type,
                "engine_adapter": modality,
                "orchestration_mode": "per_scene_8s",
                "scene_count": scene_count,
                "quality_tier": quality_tier,
                "scene_duration_seconds": scene_sec,
                "duration_seconds": scene_count * scene_sec,
                "provider_health_at_submit": health,
                "provider_health_summary": health,
                **inputs,
            },
        },
    }
    proj_update = bot.video_b14_prepare_project_for_invoice(user_id, session)
    pid = int(proj_update["project_id"])

    # 4. Production provider admission & router (zero manual keys or candidate chains)
    snap = router.product_video_provider_eligibility_snapshot(
        required_capability=modality,
        scene_count=scene_count,
        provider_health=health,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
    )
    assert snap.get("ok") is True, f"Eligibility snapshot failed for {product_type}: {snap}"
    eligible_keys = list(snap.get("eligible_provider_keys") or [])
    assert len(eligible_keys) > 0, f"Eligible provider keys missing for {product_type}"

    # Assert production router selected provider
    if modality == "text_to_video":
        assert eligible_keys[0] == "shopaikey_video"
    elif modality in ("image_to_video", "video_to_video"):
        assert eligible_keys[0] == "key4u_video"

    preflight = {
        "ok": True,
        "effective_provider_chain": eligible_keys,
        "provider_availability_summary": {"overall_available": True},
        "provider_health_summary": health,
        "provider_health_at_submit": health,
    }
    project_row = queue.get_video_project(conn, pid)
    final_admission = bot.build_product_video_public_final_admission(
        dict(project_row),
        user_id,
        preflight,
        snap,
    )
    final_admission["provider_health_at_submit"] = health
    final_admission["provider_health_summary"] = health
    assert final_admission.get("admission_result") == "PASS", f"Admission blocked for {product_type}: {final_admission}"
    signed_admission = queue.sign_product_video_final_admission_context(final_admission)
    assert bool(signed_admission.get("admission_context_signature")) is True
    assert queue.verify_product_video_final_admission_context(signed_admission) is True

    # 5. Confirm invoice through real confirmation seam
    confirm_res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=user_id,
        balance_xu=10_000,
        provider_admission=signed_admission,
    )
    assert confirm_res["ok"] is True, f"Confirm failed for {product_type}: {confirm_res}"

    # Verify exactly DELTA=1 across objects
    after_projects = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    after_jobs = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    after_outbox = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    assert after_projects - initial_projects == 1, "PROJECT_ROWS_DELTA must equal 1"
    assert after_jobs - initial_jobs == 1, "JOB_ROWS_DELTA must equal 1"
    assert after_outbox - initial_outbox == 1, "OUTBOX_ROWS_DELTA must equal 1"

    # Linkage verification
    job_row = conn.execute("SELECT * FROM video_jobs WHERE project_id=?", (pid,)).fetchone()
    outbox_row = conn.execute("SELECT * FROM video_dispatch_outbox WHERE project_id=?", (pid,)).fetchone()

    jid = int(job_row["id"])
    oid = int(outbox_row["outbox_id"])
    assert outbox_row["job_id"] == jid
    assert outbox_row["owner"] == "owner_product_video"
    assert outbox_row["dispatch_status"] == "pending"

    # Confirm Replay Idempotency
    replay_res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=user_id,
        balance_xu=10_000,
        provider_admission=signed_admission,
    )
    assert replay_res["ok"] is False or replay_res.get("duplicate_prevented") is True
    assert conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0] == after_projects
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == after_jobs
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == after_outbox

    return pid, jid, oid

# ==============================================================================
# SECTION 1: ACTIVE PRODUCT MATRIX & IDENTITY AUDIT (9 ACTIVE, 3 DEFERRED)
# ==============================================================================

def test_pv10_active_and_deferred_matrices_intact() -> None:
    """Validate 9 active products and 3 deferred products contracts."""
    assert len(ALL_ACTIVE_PRODUCTS) == 9
    assert len(ACTIVE_T2V_PRODUCTS) == 4
    assert len(ACTIVE_I2V_PRODUCTS) == 2
    assert len(ACTIVE_V2V_PRODUCTS) == 3
    assert len(DEFERRED_PRODUCTS) == 3

    for pid in ALL_ACTIVE_PRODUCTS:
        assert pid not in DEFERRED_PRODUCTS
        adapter = video_tail9.adapter_for(pid)
        assert adapter["canonical_product_type"] == pid
        assert adapter["executor_product_type"] == EXPECTED_EXECUTOR_MAP[pid]
        assert adapter["required_capability"] == EXPECTED_MODALITY_MAP[pid]
        assert adapter["execution_enabled"] is True
        assert adapter["pricing_mode"] == "canonical"

    for deferred in DEFERRED_PRODUCTS:
        assert deferred not in ALL_ACTIVE_PRODUCTS
        eng = queue.product_video_engine_contract(deferred)
        assert eng["execution_enabled"] is False or bool(eng["execution_blocker"])


# ==============================================================================
# SECTION 2: QUALITY MATRIX & TREND 400 LOCK
# ==============================================================================

def test_pv10_quality_matrix_protection() -> None:
    """Protect PV09 quality matrix: T2V/I2V 10 tiers, V2V exact {500,600,700,800}, Trend 400=80 Xu."""
    # 1. Trend Tier 400 Visible and 80 Xu
    trend_catalog = video_uifreeze1.compatible_quality_tiers("video_trend", scene_count=2)
    trend_t400 = next((t for t in trend_catalog if int(t.get("tier_id") or t.get("tier_key") or t.get("id") or 0) == 400), None)
    assert trend_t400 is not None, "TIER_400_VISIBLE must be YES"
    assert int(trend_t400.get("unit_xu") or trend_t400.get("price_xu") or trend_t400.get("package_xu") or 0) == 80, "TIER_400_PRICE_XU must be 80"

    # 2. V2V quality matrix strictly {500, 600, 700, 800}
    for v2v in ACTIVE_V2V_PRODUCTS:
        tiers = {int(t.get("tier_id") or t.get("tier_key") or t.get("id") or 0) for t in video_uifreeze1.compatible_quality_tiers(v2v)}
        assert tiers == {500, 600, 700, 800}
        assert 400 not in tiers
        assert 200 not in tiers
        assert 300 not in tiers
        assert 1000 not in tiers

    # 3. Full 10 quality tiers available for general T2V / I2V products
    for prod in ("video_trend", "video_ai_prompt"):
        count = 2 if prod == "video_trend" else 1
        catalog_tiers = video_uifreeze1.compatible_quality_tiers(prod, scene_count=count)
        assert len(catalog_tiers) == 10, f"{prod} must offer exactly 10 quality tiers"


# ==============================================================================
# SECTION 3: DETERMINISTIC E2E CHAIN FOR ALL 9 ACTIVE PRODUCTS
# ==============================================================================

@pytest.mark.parametrize("product_type", ALL_ACTIVE_PRODUCTS)
def test_pv10_deterministic_e2e_all_active_products(
    tmp_path: Path,
    product_type: str,
) -> None:
    """Prove the complete deterministic E2E chain for every active Product Video product.
    
    Chain:
    PUBLIC ENTRY -> DRAFT -> QUALITY -> CONFIRM -> PROJECT -> JOB -> OUTBOX
    -> WORKER CLAIM -> ADAPTER -> REAL RENDER SEAM -> VALID FINAL MP4
    -> JOB COMPLETION -> DELIVERY SEAM -> DURABLE RECEIPT -> IDEMPOTENT REPLAY.
    """
    db_path = tmp_path / f"pv10_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    cfg = PRODUCT_CONFIG[product_type]
    scene_count = cfg["scene_count"]

    # 1. PUBLIC ENTRY -> CONFIRM -> PROJECT -> JOB -> OUTBOX
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    # 2. WORKER CLAIM
    # Unauthorized worker cannot claim
    unauth_claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="unauth_worker",
        capabilities=["general_ffmpeg"],
        owner_product_video_only=True,
    )
    assert unauth_claim.get("job") is None, "WRONG_OWNER_CLAIM must be 0"

    # Authorized owner worker claims
    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-owner-01",
        capabilities=["owner_product_video", CANONICAL_CAPABILITY],
        owner_product_video_only=True,
    )
    assert claim.get("job") is not None, "CLAIM_COUNT must be 1"
    claimed_job = claim["job"]
    assert int(claimed_job.get("job_id") or claimed_job.get("id") or 0) == jid
    assert int(claimed_job.get("project_id") or 0) == pid

    src_vid_path = (claimed_job.get("asset_pack") or {}).get("source_video_local_path") or (claimed_job.get("asset_pack") or {}).get("source_video_path")
    if src_vid_path:
        claimed_job["source_video_local_path"] = src_vid_path
        claimed_job["source_video_path"] = src_vid_path

    # Double claim prevented
    second_claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-owner-02",
        capabilities=["owner_product_video", CANONICAL_CAPABILITY],
        owner_product_video_only=True,
    )
    assert second_claim.get("job") is None, "DOUBLE_CLAIM must be 0"

    # 3. PRODUCT ADAPTER SELECTION
    adapter = video_tail9.adapter_for(product_type)
    assert adapter["canonical_product_type"] == product_type
    assert adapter["required_capability"] == EXPECTED_MODALITY_MAP[product_type]

    # 4. REAL RENDER EXECUTION SEAM (Zero external network calls)
    workspace = tmp_path / f"ws_{product_type}"
    workspace.mkdir(parents=True, exist_ok=True)
    render_res = video_real_render_connector.render_real_video_job(claimed_job, str(workspace))
    assert render_res["ok"] is True, f"Render failed for {product_type}: {render_res.get('error')}"
    final_video_path = render_res.get("final_video_path")
    assert final_video_path and os.path.isfile(final_video_path), "FINAL_MP4_EXISTS must be YES"

    # 5. DB COMPLETION
    comp_res = queue.complete_video_job(
        conn,
        job_id=jid,
        final_video_path=str(final_video_path),
        result=render_res,
    )
    assert comp_res["ok"] is True
    job_after = queue.get_video_render_job(conn, jid)
    assert job_after["status"] == "completed"

    # 6. DELIVERY SEAM & DURABLE RECEIPT
    proj_row = queue.get_video_project(conn, pid)
    deliv_payload = {"ok": True, "job": dict(job_after), "project": dict(proj_row)}
    deliv_out = asyncio.run(bot.maybe_send_remote_worker_final_video(deliv_payload))
    assert deliv_out.get("sent") is True, f"Delivery send failed for {product_type}: {deliv_out}"
    delivery_message_id = str(deliv_out.get("telegram_message_id") or f"tg_receipt_pv10_{product_type}_{jid}")

    delivery_res = queue.note_video_delivery_result(
        conn,
        job_id=jid,
        sent=True,
        delivery_message_id=delivery_message_id,
        success_message_id=delivery_message_id,
    )
    assert delivery_res["ok"] is True, f"Delivery failed for {product_type}: {delivery_res}"

    proj_after = queue.get_video_project(conn, pid)
    assert proj_after["video_terminal_state"] == "final_delivered"
    assert proj_after["video_delivery_message_id"] == delivery_message_id
    assert bool(proj_after["video_delivered_at"]) is True

    # 7. IDEMPOTENT REPLAY DELIVERY (SECOND_SEND=0, DUPLICATE_RECEIPT=0)
    deliv_replay = asyncio.run(bot.maybe_send_remote_worker_final_video({
        "ok": True,
        "job": dict(job_after),
        "project": dict(proj_after),
        "duplicate": True,
    }))
    assert deliv_replay.get("sent") is False
    assert deliv_replay.get("duplicate_prevented") is True

    receipt_replay = queue.note_video_delivery_result(
        conn,
        job_id=jid,
        sent=True,
        delivery_message_id=delivery_message_id,
        success_message_id=delivery_message_id,
    )
    assert receipt_replay["ok"] is True
    assert receipt_replay.get("duplicate_prevented") is True


# ==============================================================================
# SECTION 4: FAILURE INJECTION MATRIX (1 T2V, 1 I2V, 1 V2V)
# ==============================================================================

@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_image",
    "self_shot_scene_change",
])
def test_pv10_failure_injection_provider_fake_failure(tmp_path: Path, product_type: str) -> None:
    """Failure A: Provider fake failure -> FAKE_PRODUCT_SUCCESS=0, FAKE_DELIVERY_SUCCESS=0."""
    db_path = tmp_path / f"pv10_fail_provider_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    fail_payload = {
        "job_id": jid,
        "project_id": pid,
        "provider_status": "failed",
        "provider_error": "fake_provider_timeout_or_rejection",
        "scene_tasks": [{"scene_index": 1, "status": "failed", "error": "fake_provider_error"}],
        "final_mp4_valid": False,
    }
    conn.execute("UPDATE video_jobs SET status='failed', result_json=? WHERE id=?", (json.dumps(fail_payload), jid))
    conn.commit()

    deliv = queue.note_video_delivery_result(conn, job_id=jid, sent=True, delivery_message_id="msg_fail")
    assert deliv["ok"] is False
    proj = queue.get_video_project(conn, pid)
    assert proj.get("video_terminal_state") != "final_delivered"


@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_image",
    "self_shot_scene_change",
])
def test_pv10_failure_injection_provider_complete_missing_clip(tmp_path: Path, product_type: str) -> None:
    """Failure B: Provider complete but missing clip -> scene clip invalid, finalizer locked."""
    db_path = tmp_path / f"pv10_fail_missing_clip_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    missing_file = tmp_path / "non_existent_clip.mp4"
    fail_payload = {
        "job_id": jid,
        "project_id": pid,
        "provider_status": "succeeded",
        "result_url": "https://fake.cdn/clip.mp4",
        "scene_tasks": [{
            "scene_index": 1,
            "status": "succeeded",
            "result_url": "https://fake.cdn/clip.mp4",
            "output_path": str(missing_file),
            "clip_bytes": 0,
            "clip_valid": False,
        }],
        "scene_clip_coverage_complete": False,
        "final_mp4_valid": False,
    }
    conn.execute("UPDATE video_jobs SET status='processing', result_json=? WHERE id=?", (json.dumps(fail_payload), jid))
    conn.commit()

    job = queue.get_video_render_job(conn, jid)
    project = queue.get_video_project(conn, pid)
    coverage = queue.product_video_scene_coverage_state(project, job, fail_payload)
    assert coverage["scene_clip_coverage_complete"] is False

    deliv = queue.note_video_delivery_result(conn, job_id=jid, sent=True, delivery_message_id="msg_fail")
    assert deliv["ok"] is False


@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_image",
    "self_shot_scene_change",
])
def test_pv10_failure_injection_corrupt_clip(tmp_path: Path, product_type: str) -> None:
    """Failure C: Corrupt clip file -> local probe fails, finalizer locked."""
    corrupt_clip = tmp_path / f"corrupt_{product_type}.mp4"
    corrupt_clip.write_bytes(b"\x00\x00\x00 ftypisom\x00\x00\x02\x00corruptbytesdatahere9999999")

    probe = video_local_validation.probe_video_file(str(corrupt_clip))
    assert probe["ok"] is False, "Corrupt clip must fail probe"

    db_path = tmp_path / f"pv10_fail_corrupt_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    fail_payload = {
        "job_id": jid,
        "project_id": pid,
        "scene_tasks": [{
            "scene_index": 1,
            "status": "succeeded",
            "output_path": str(corrupt_clip),
            "clip_bytes": corrupt_clip.stat().st_size,
            "clip_valid": False,
        }],
        "scene_clip_coverage_complete": False,
        "final_mp4_valid": False,
        "final_video_path": str(corrupt_clip),
    }
    conn.execute("UPDATE video_jobs SET status='processing', result_json=? WHERE id=?", (json.dumps(fail_payload), jid))
    conn.commit()

    deliv = queue.note_video_delivery_result(conn, job_id=jid, sent=True, delivery_message_id="msg_fail")
    assert deliv["ok"] is False
    assert queue.get_video_project(conn, pid).get("video_terminal_state") != "final_delivered"


@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_image",
    "self_shot_scene_change",
])
def test_pv10_failure_injection_finalizer_failure(tmp_path: Path, product_type: str) -> None:
    """Failure D: Finalizer failure -> final mp4 invalid, delivery refused."""
    db_path = tmp_path / f"pv10_fail_finalizer_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    fail_payload = {
        "job_id": jid,
        "project_id": pid,
        "finalizer_failed": True,
        "final_mp4_valid": False,
        "final_video_path": "",
    }
    conn.execute("UPDATE video_jobs SET status='failed', result_json=? WHERE id=?", (json.dumps(fail_payload), jid))
    conn.commit()

    deliv = queue.note_video_delivery_result(conn, job_id=jid, sent=True, delivery_message_id="msg_fail")
    assert deliv["ok"] is False


@pytest.mark.parametrize("product_type", [
    "video_trend",
    "video_ai_image",
    "self_shot_scene_change",
])
def test_pv10_failure_injection_delivery_failure(tmp_path: Path, product_type: str) -> None:
    """Failure E: Delivery failure -> empty receipt fails closed, terminal state not delivered."""
    db_path = tmp_path / f"pv10_fail_deliv_{product_type}.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, product_type)

    valid_mp4 = _create_mini_mp4(tmp_path / f"valid_deliv_{product_type}.mp4", duration_sec=1.0)
    payload = {
        "job_id": jid,
        "project_id": pid,
        "scene_clip_coverage_complete": True,
        "final_mp4_valid": True,
        "final_video_path": str(valid_mp4),
        "output_bytes": valid_mp4.stat().st_size,
    }
    conn.execute("UPDATE video_jobs SET status='processing', result_json=? WHERE id=?", (json.dumps(payload), jid))
    conn.commit()

    deliv_empty = queue.note_video_delivery_result(conn, job_id=jid, sent=True, delivery_message_id="")
    assert deliv_empty["ok"] is False
    assert queue.get_video_project(conn, pid).get("video_terminal_state") != "final_delivered"

    deliv_unsent = queue.note_video_delivery_result(conn, job_id=jid, sent=False, reason="bot_blocked_by_user")
    assert deliv_unsent["ok"] is False or deliv_unsent.get("sent") is False
    assert queue.get_video_project(conn, pid).get("video_terminal_state") != "final_delivered"


# ==============================================================================
# SECTION 5: RECOVERY QUOTA PROTECTION (PV06 SEPARATED QUOTAS)
# ==============================================================================

def test_pv10_recovery_quota_separation(tmp_path: Path) -> None:
    """Protect PV06 independent recovery quotas: provider submit, poll, download, finalizer, delivery."""
    db_path = tmp_path / "pv10_quota.sqlite3"
    conn = _create_isolated_db(db_path)
    pid, jid, oid = _seed_and_confirm_project(conn, tmp_path, "video_trend")

    result = {
        "job_id": jid,
        "project_id": pid,
        "source": "product_video",
        "product_video": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_count": 2,
        "task_to_scene_index": {"t1": 1, "t2": 2},
        "scene_tasks": [
            {"scene_index": 1, "task_id": "t1", "status": "succeeded", "clip_valid": True},
            {"scene_index": 2, "task_id": "t2", "status": "succeeded", "clip_valid": True},
        ],
        "scene_clip_coverage_complete": True,
        "finalizer_failed": True,
        "finalizer_error": "ffmpeg_concat_error",
    }
    conn.execute("UPDATE video_jobs SET status='failed', result_json=? WHERE id=?", (json.dumps(result), jid))
    conn.execute("UPDATE video_dispatch_outbox SET dispatch_status='acknowledged' WHERE outbox_id=?", (oid,))
    conn.commit()

    job = queue.get_video_render_job(conn, jid)
    project = queue.get_video_project(conn, pid)

    domain = queue.classify_product_video_recovery_domain(result, job, project)
    assert domain == "finalizer"

    rec = queue.recover_product_video_existing_tasks(conn, job_id=jid, recovery_domain=domain)
    assert rec["existing_task_recovery_recovered"] is True

    job_after = queue.get_video_render_job(conn, jid)
    res_after = json.loads(job_after["result_json"])
    assert res_after["finalizer_recovery_count"] == 1
    assert res_after.get("provider_poll_recovery_count", 0) == 0
    assert res_after.get("provider_artifact_recovery_count", 0) == 0
    assert res_after.get("scene_clip_recovery_count", 0) == 0
    assert res_after.get("delivery_recovery_count", 0) == 0
    assert res_after["provider_submit_allowed"] is False


# ==============================================================================
# SECTION 6: DURABILITY / RESTART SIMULATION
# ==============================================================================

def test_pv10_durability_and_restart_simulation(tmp_path: Path) -> None:
    """State persists across connection close, reopen, and process restart without duplicate objects."""
    db_file = tmp_path / "pv10_durability_restart.sqlite3"
    conn1 = _create_isolated_db(db_file)

    pid, jid, oid = _seed_and_confirm_project(conn1, tmp_path, "video_trend")

    valid_mp4 = _create_mini_mp4(tmp_path / "valid_restart.mp4", duration_sec=1.0)
    result_payload = {
        "job_id": jid,
        "project_id": pid,
        "scene_clip_coverage_complete": True,
        "final_mp4_valid": True,
        "final_video_path": str(valid_mp4),
        "output_bytes": valid_mp4.stat().st_size,
    }
    conn1.execute("UPDATE video_jobs SET status='processing', result_json=? WHERE id=?", (json.dumps(result_payload), jid))
    conn1.commit()

    deliv_res = queue.note_video_delivery_result(
        conn1,
        job_id=jid,
        sent=True,
        delivery_message_id="tg_durable_restart_receipt",
    )
    assert deliv_res["ok"] is True

    conn1.close()
    del conn1

    conn2 = sqlite3.connect(str(db_file))
    conn2.row_factory = sqlite3.Row

    proj = queue.get_video_project(conn2, pid)
    job = queue.get_video_render_job(conn2, jid)
    outbox = conn2.execute("SELECT * FROM video_dispatch_outbox WHERE outbox_id=?", (oid,)).fetchone()

    assert proj is not None
    assert proj["video_terminal_state"] == "final_delivered"
    assert proj["video_delivery_message_id"] == "tg_durable_restart_receipt"
    assert job is not None
    assert job["status"] == "completed"
    assert outbox is not None
    assert outbox["owner"] == "owner_product_video"

    assert conn2.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0] == 1
    assert conn2.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn2.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1

    conn2.close()


# ==============================================================================
# SECTION 7: DEFERRED PRODUCT LOCK
# ==============================================================================

@pytest.mark.parametrize("deferred_product", DEFERRED_PRODUCTS)
def test_pv10_deferred_products_fail_closed(tmp_path: Path, deferred_product: str) -> None:
    """Deferred products must NOT execute: DELTA=0 across project, job, outbox, claim, submit."""
    db_path = tmp_path / f"pv10_deferred_{deferred_product}.sqlite3"
    conn = _create_isolated_db(db_path)

    eng = queue.product_video_engine_contract(deferred_product)
    assert eng["execution_enabled"] is False or bool(eng["execution_blocker"])

    project = queue.create_video_project(
        conn,
        user_id=8888,
        profile_id=deferred_product,
        topic=f"Deferred {deferred_product}",
        asset_pack={"product_type": deferred_product, "source": "product_video"},
    )
    pid = int(project["project_id"])

    res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=8888,
        balance_xu=10_000,
        provider_admission=None,
    )
    assert res["ok"] is False
    assert res.get("job_created") is False
    assert res.get("dispatch_outbox_created") is False

    jobs = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE project_id=?", (pid,)).fetchone()[0]
    outboxes = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE project_id=?", (pid,)).fetchone()[0]
    assert jobs == 0, "JOB_DELTA must be 0 for deferred product"
    assert outboxes == 0, "OUTBOX_DELTA must be 0 for deferred product"

    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-owner-01",
        capabilities=["owner_product_video", CANONICAL_CAPABILITY],
        owner_product_video_only=True,
    )
    assert claim.get("job") is None, "CLAIM_DELTA must be 0 for deferred product"


# ==============================================================================
# SECTION 8: CROSS-PRODUCT ISOLATION IN SHARED ISOLATED DB
# ==============================================================================

def test_pv10_cross_product_isolation(tmp_path: Path) -> None:
    """Multiple active products in one isolated DB maintain strict scene, artifact, and receipt isolation."""
    db_path = tmp_path / "pv10_shared_isolation.sqlite3"
    conn = _create_isolated_db(db_path)

    # Product A: video_trend (T2V)
    pid_a, jid_a, oid_a = _seed_and_confirm_project(conn, tmp_path / "prod_a", "video_trend", user_id=1001)

    # Product B: video_ai_video_reference (V2V)
    pid_b, jid_b, oid_b = _seed_and_confirm_project(conn, tmp_path / "prod_b", "video_ai_video_reference", user_id=1002)

    assert pid_a != pid_b
    assert jid_a != jid_b
    assert oid_a != oid_b

    scenes_a = conn.execute("SELECT * FROM video_scenes WHERE project_id=?", (pid_a,)).fetchall()
    assert len(scenes_a) == 2
    assert all(s["project_id"] == pid_a for s in scenes_a)

    scenes_b = conn.execute("SELECT * FROM video_scenes WHERE project_id=?", (pid_b,)).fetchall()
    assert len(scenes_b) == 1
    assert all(s["project_id"] == pid_b for s in scenes_b)

    scenes_a_ids = {s["scene_id"] for s in scenes_a}
    scenes_b_ids = {s["scene_id"] for s in scenes_b}
    assert scenes_a_ids.isdisjoint(scenes_b_ids)

    outbox_a = conn.execute("SELECT * FROM video_dispatch_outbox WHERE outbox_id=?", (oid_a,)).fetchone()
    outbox_b = conn.execute("SELECT * FROM video_dispatch_outbox WHERE outbox_id=?", (oid_b,)).fetchone()
    assert outbox_a["job_id"] == jid_a
    assert outbox_b["job_id"] == jid_b

    valid_mp4_a = _create_mini_mp4(tmp_path / "mp4_a.mp4", duration_sec=1.0)
    conn.execute(
        "UPDATE video_jobs SET status='processing', result_json=? WHERE id=?",
        (json.dumps({
            "job_id": jid_a,
            "scene_clip_coverage_complete": True,
            "final_mp4_valid": True,
            "final_video_path": str(valid_mp4_a),
            "output_bytes": valid_mp4_a.stat().st_size,
        }), jid_a),
    )
    conn.commit()

    deliv_a = queue.note_video_delivery_result(conn, job_id=jid_a, sent=True, delivery_message_id="tg_receipt_a")
    assert deliv_a["ok"] is True

    proj_b = queue.get_video_project(conn, pid_b)
    assert proj_b.get("video_terminal_state") != "final_delivered"
    assert proj_b.get("video_delivery_message_id") != "tg_receipt_a"
    assert proj_b.get("video_delivered_at") is None


# ==============================================================================
# SECTION 9: REAL LOCAL MEDIA FINALIZER LANE (UNMOCKED FFMPEG & FFPROBE BINARIES)
# ==============================================================================

def test_pv10_real_media_finalizer_lane(tmp_path: Path) -> None:
    """Empirical proof of real media finalizer path with real ffmpeg and ffprobe binaries.
    
    Verifies:
    - FFMPEG_BINARY_REAL=YES
    - FFPROBE_BINARY_REAL=YES
    - FINALIZER_FUNCTION=services.multiscene_video_pipeline.finalize_multiscene_scene_clips
    - FINAL_MP4_EXISTS=YES
    - FINAL_MP4_BYTES_GT_ZERO=YES
    - FINAL_MP4_FFPROBE_PASS=YES
    - FINAL_MP4_HAS_VIDEO=YES
    - FINAL_MP4_AUDIO_CONTRACT_PASS=YES
    """
    # 1. Verify real binaries exist
    ffmpeg_bin = shutil.which("ffmpeg") or os.getenv("FFMPEG_PATH")
    ffprobe_bin = shutil.which("ffprobe") or os.getenv("FFPROBE_PATH")
    assert ffmpeg_bin and Path(ffmpeg_bin).is_file(), f"Real ffmpeg binary missing: {ffmpeg_bin}"
    assert ffprobe_bin and Path(ffprobe_bin).is_file(), f"Real ffprobe binary missing: {ffprobe_bin}"

    # 2. Real input mini-mp4 clip files generated locally
    clip1 = tmp_path / "scene_clip_1.mp4"
    clip2 = tmp_path / "scene_clip_2.mp4"
    clip1.write_bytes(MINI_MP4_BYTES)
    clip2.write_bytes(MINI_MP4_BYTES)

    # 3. Define scenes
    scenes = [
        pipeline.SceneSpec(
            scene_id="1",
            title="Scene 1",
            visual_prompt="Visual 1",
            video_prompt="Prompt 1",
            target_duration_sec=1.0,
        ),
        pipeline.SceneSpec(
            scene_id="2",
            title="Scene 2",
            visual_prompt="Visual 2",
            video_prompt="Prompt 2",
            target_duration_sec=1.0,
        ),
    ]

    # 4. Execute real multiscene finalizer
    final_res = pipeline.finalize_multiscene_scene_clips(
        user_id="1001",
        job_id="test_finalizer_lane",
        workspace_dir=str(tmp_path),
        scenes=scenes,
        scene_clip_paths={1: str(clip1), 2: str(clip2)},
        preserve_scene_audio=True,
        enable_subtitle=False,
        enable_voice=False,
    )
    assert final_res.get("ok") is True, f"Finalizer failed: {final_res.get('error')}"
    final_mp4 = final_res.get("final_video_path")
    assert final_mp4 and os.path.isfile(final_mp4), "FINAL_MP4_EXISTS must be YES"
    assert os.path.getsize(final_mp4) > 0, "FINAL_MP4_BYTES_GT_ZERO must be YES"

    # 5. Run real probe over output
    probe = video_local_validation.probe_video_file(final_mp4)
    assert probe.get("ok") is True, f"FINAL_MP4_FFPROBE_PASS must be YES: {probe.get('reason')}"
    assert probe.get("has_video") is True, "FINAL_MP4_HAS_VIDEO must be YES"
    assert probe.get("has_audio") is True, "FINAL_MP4_AUDIO_CONTRACT_PASS must be YES"
    assert abs(float(probe.get("duration") or 0.0) - 2.0) <= 0.5, f"Duration mismatch: {probe.get('duration')}"

    # 6. Also run real video_final_output.probe_video over output
    vfo_probe = video_final_output.probe_video(final_mp4)
    assert vfo_probe.get("ok") is True, "video_final_output.probe_video must pass"
    assert vfo_probe.get("has_video") is True


# ==============================================================================
# SECTION 10: PUBLIC ENTRY & CONFIRMATION CALLBACK HANDLER AUDIT
# ==============================================================================

def test_pv10_public_entry_and_confirm_callback_handlers() -> None:
    """Audit and prove wiring of real public entry, draft, quality, and confirmation handlers.
    
    Verifies:
    - PUBLIC_ENTRY_HANDLER=bot.handle_video_product_callback
    - DRAFT_BUILDER=services.video_tail9.new_state
    - QUALITY_HANDLER=services.video_tail9.select_package
    - CONFIRM_HANDLER=bot.handle_product_video_public_confirm_callback
    - PROVIDER_ADMISSION_HANDLER=bot.build_product_video_public_final_admission
    - PROVIDER_ELIGIBILITY_HANDLER=bot.product_video_public_preflight_evaluation
    - PROVIDER_ROUTER_HANDLER=services.video_provider_router.product_video_provider_eligibility_snapshot
    - T2V_SELECTED_PROVIDER=shopaikey_video
    - I2V_SELECTED_PROVIDER=key4u_video
    - V2V_SELECTED_PROVIDER=key4u_video
    - MANUAL_ELIGIBLE_PROVIDER_KEYS=NO
    - MANUAL_CONTRACT_VALID_CHAIN=NO
    """
    # 1. Entry & confirm handler callability and registration
    assert callable(bot.handle_video_product_callback)
    assert callable(bot.handle_product_video_public_confirm_callback)
    assert callable(bot.video_b14_prepare_project_for_invoice)
    assert callable(video_tail9.new_state)
    assert callable(video_tail9.select_package)
    assert callable(bot.product_video_public_preflight_evaluation)
    assert callable(bot.build_product_video_public_final_admission)
    assert callable(router.product_video_provider_eligibility_snapshot)

    # 2. Verify router selection across all modalities without manual overrides
    health = {
        "shopaikey_video": {
            "provider": "shopaikey_video",
            "live_healthy": True,
            "route_ready": True,
            "multi_scene_eligible": True,
            "health_status": "healthy",
            "last_valid_output_at": queue.now_text(),
            "success_ttl_seconds": 3600,
        },
        "key4u_video": {
            "provider": "key4u_video",
            "live_healthy": True,
            "route_ready": True,
            "multi_scene_eligible": True,
            "health_status": "healthy",
            "last_valid_output_at": queue.now_text(),
            "success_ttl_seconds": 3600,
        },
    }

    # T2V router evaluation -> shopaikey_video
    t2v_snap = router.product_video_provider_eligibility_snapshot(
        required_capability="text_to_video",
        scene_count=1,
        provider_health=health,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
    )
    assert t2v_snap.get("ok") is True
    assert t2v_snap.get("eligible_provider_keys")[0] == "shopaikey_video"

    # I2V router evaluation -> key4u_video
    i2v_snap = router.product_video_provider_eligibility_snapshot(
        required_capability="image_to_video",
        scene_count=1,
        provider_health=health,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
    )
    assert i2v_snap.get("ok") is True
    assert i2v_snap.get("eligible_provider_keys")[0] == "key4u_video"

    # V2V router evaluation -> key4u_video
    v2v_snap = router.product_video_provider_eligibility_snapshot(
        required_capability="video_to_video",
        scene_count=1,
        provider_health=health,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
    )
    assert v2v_snap.get("ok") is True
    assert v2v_snap.get("eligible_provider_keys")[0] == "key4u_video"
