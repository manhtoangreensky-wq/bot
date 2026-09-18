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
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAA3ttZGF03gIATGF2YzYwLjMx"
    "LjEwMgACMEAOAAACVAYF//9Q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NCByMzEwOCAzMWUx"
    "OWY5IC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyMyAtIGh0dHA6Ly93"
    "d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTAgcmVmPTEgZGVibG9jaz0w"
    "OjA6MCBhbmFseXNlPTA6MCBtZT1kaWEgc3VibWU9MCBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVk"
    "X3JlZj0wIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MCA4eDhkY3Q9MCBjcW09MCBkZWFk"
    "em9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0wIHRocmVhZHM9NCBsb29rYWhl"
    "YWRfdGhyZWFkcz0xIHNsaWNlZF90aHJlYWRzPTAgbnI9MCBkZWNpbWF0ZT0xIGludGVybGFjZWQ9MCBi"
    "bHVyYXlfY29tcGF0PTAgY29uc3RyYWluZWRfaW50cmE9MCBiZnJhbWVzPTAgd2VpZ2h0cD0wIGtleWlu"
    "dD0yNTAga2V5aW50X21pbj0xMCBzY2VuZWN1dD0wIGludHJhX3JlZnJlc2g9MCByYz1jcmYgbWJ0cmVl"
    "PTAgY3JmPTIzLjAgcWNvbXA9MC42MCBxcG1pbj0wIHFwbWF4PTY5IHFwc3RlcD00IGlwX3JhdGlvPTEu"
    "NDAgYXE9MACAAAAAUGWIhDoRigACMXHAAEPKOAAIBcnJycnJycnJyddddddddddddddddddddddddddd"
    "dddddddddddddddddddddddddddddddddddddddddeARggBwEYIAcBGCAHAAAABkGaIDqAowEYIAcBGCAH"
    "AAAABkGaQD6AowEYIAcBGCAHAAAABkGaYD6AowEYIAcBGCAHAAAABkGagD6AowEYIAcBGCAHAAAABkGa"
    "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"
    "YQAAAAEAAAAATGF2ZjYwLjE2LjEwMA=="
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
def deterministic_pv10_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure fully deterministic isolated execution across all environments."""
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
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not out_path.is_file() or out_path.stat().st_size == 0:
            _create_mini_mp4(out_path, duration_sec=1.0)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

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
    """Seed project, update invoice, confirm, and verify row deltas and linkage.
    
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

    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "product_type": product_type,
        "engine_adapter": EXPECTED_MODALITY_MAP[product_type],
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "scene_count": scene_count,
        "quality_tier": quality_tier,
        "scene_duration_seconds": scene_sec,
        "duration_seconds": scene_count * scene_sec,
        **inputs,
    }
    tier_name = cat.normalize_tier(quality_tier)
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
    invoice = {
        **shared,
        "tier": str(quality_tier),
        "quality_tier": quality_tier,
        "package_xu": package_xu,
        "scene_duration_seconds": scene_sec,
        "duration_seconds": scene_count * scene_sec,
        "total_xu": package_xu,
        "user_visible_price_xu": package_xu,
        "persisted_quoted_price_xu": package_xu,
        "customer_charge_planned_xu": package_xu,
        "wallet_charge_amount_xu": package_xu,
        "provider_health_at_submit": health,
    }

    initial_projects = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    initial_jobs = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    initial_outbox = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    # Create project
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id=product_type,
        topic=f"PV10 Test {product_type}",
        ratio="9:16",
        asset_pack=shared,
    )
    pid = int(project["project_id"])
    updated_project = queue.update_video_project(
        conn,
        pid,
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        quality_tier=quality_tier,
        total_xu_estimated=package_xu,
    )

    admission = _build_sealed_admission(updated_project, product_type=product_type)

    # Confirm invoice
    confirm_res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=user_id,
        balance_xu=10_000,
        provider_admission=admission,
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
        provider_admission=admission,
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
