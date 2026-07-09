import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from providers.video_generic_http_provider import build_shopaikey_video_payload
from services import multiscene_video_pipeline as mvp
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector
from services.video_provider_base import VideoGenerationRequest


ROOT = Path(__file__).resolve().parents[1]


def _ffmpeg() -> str | None:
    return os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _make_clip(path: Path, *, duration: float = 0.25, color: str = "0x1E88E5") -> str:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg is required for historical multi-clip concat fixture tests")
    result = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=128x224:r=24:d={duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return mvp.ensure_video_output(str(path))


def _renderer(colors: list[str] | None = None):
    palette = colors or ["0x1E88E5", "0x43A047", "0xF4511E", "0x8E24AA", "0xFDD835"]

    def render(scene, output_path):
        color = palette[(int(scene.scene_id) - 1) % len(palette)]
        return _make_clip(Path(output_path), color=color)

    return render


def _run_pipeline(tmp_path: Path, *, scenes: int, seconds_per_scene: int = 8) -> dict:
    workspace = mvp.create_multiscene_workspace(f"r18c_{scenes}_clips")
    return mvp.process_multiscene_video_pipeline(
        user_id="r18c-user",
        job_id=f"r18c-{scenes}",
        user_prompt="Hook. Product benefit. Proof. CTA.",
        workspace_dir=workspace,
        render_video_func=_renderer(),
        max_scenes=scenes,
        default_scene_duration=seconds_per_scene,
        aspect_ratio="9:16",
        enable_voice=False,
        enable_subtitle=False,
    )


def _conn(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "r18c_video_queue.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project(conn, *, scene_count: int = 2, orchestration_mode: str = ""):
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "original_user_prompt": "Video theo trend cho san pham",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        **asset_pack,
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": scene_count * 200,
    }
    if orchestration_mode:
        asset_pack["orchestration_mode"] = orchestration_mode
        asset_pack["provider_orchestration_mode"] = orchestration_mode
        invoice["orchestration_mode"] = orchestration_mode
        invoice["provider_orchestration_mode"] = orchestration_mode
    project = queue.create_video_project(
        conn,
        user_id=1818,
        profile_id="video_trend",
        topic="trend product",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="make a trend product video",
        total_xu_estimated=scene_count * 200,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def test_historical_b13_concat_pipeline_contract_is_present():
    source = (ROOT / "services" / "multiscene_video_pipeline.py").read_text(encoding="utf-8")
    b13_test = (ROOT / "tests" / "test_p0_17b13_multiscene_blackbox.py").read_text(encoding="utf-8")
    assert "def process_multiscene_video_pipeline" in source
    assert "def stitch_scenes" in source
    assert "concat_scenes.txt" in source
    assert "process_multiscene_pipeline_3_scenes_final_mp4" in b13_test


def test_two_clips_8s_each_concat_to_final_16s(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    result = _run_pipeline(tmp_path, scenes=2, seconds_per_scene=8)
    assert result["ok"] is True
    assert result["scene_count"] == 2
    assert Path(result["final_video_path"]).is_file()
    duration = mvp.probe_duration(result["final_video_path"])
    assert 15.0 <= duration <= 17.5


def test_fifteen_clips_8s_each_concat_to_final_120s(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    clip = _make_clip(tmp_path / "clip_8s.mp4", duration=8.0, color="0x43A047")
    output = mvp.stitch_scenes([clip] * 15, str(tmp_path / "final_120s.mp4"))
    assert Path(output).is_file()
    duration = mvp.probe_duration(output)
    assert 118.0 <= duration <= 122.5


def test_missing_clip_never_success_and_never_charge(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    workspace = mvp.create_multiscene_workspace("r18c_missing")

    def broken(scene, output_path):
        if int(scene.scene_id) == 2:
            return {"ok": False, "error": "provider_clip_missing"}
        return _make_clip(Path(output_path), color="0x43A047")

    result = mvp.process_multiscene_video_pipeline(
        user_id="r18c-user",
        job_id="missing",
        user_prompt="One. Two.",
        workspace_dir=workspace,
        render_video_func=broken,
        max_scenes=2,
        default_scene_duration=8,
        aspect_ratio="9:16",
        enable_voice=False,
        enable_subtitle=False,
    )
    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["failed_scenes"] == [2]


def test_public_multiscene_confirm_defaults_to_historical_multiclip_concat(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)
    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    payload = json.loads(str(result["job"].get("result_json") or "{}"))
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["render_pipeline_mode"] == "historical_multi_clip_concat"
    assert payload["clip_count"] == 2
    assert payload["clip_duration_seconds"] == 8
    assert len(payload["provider_scene_tasks"]) == 2
    assert payload["provider_scene_tasks"][0]["request_job_id"].endswith("-1")
    assert payload["final_concat_required"] is True
    assert payload["charge"] == 0


def test_explicit_single_task_legacy_is_preserved(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2, orchestration_mode="single_task_legacy")
    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    payload = json.loads(str(result["job"].get("result_json") or "{}"))
    assert payload["orchestration_mode"] == "single_task_legacy"
    assert payload["render_pipeline_mode"] == "single_task_legacy"
    assert payload["provider_scene_tasks"] == []
    assert payload["final_concat_required"] is False


def test_worker_payload_uses_historical_multiclip_concat_for_multiscene_job():
    hydrated = {
        "id": 218,
        "job_id": 218,
        "job_type": "video_render",
        "status": "queued",
        "result_json": "{}",
        "project": {
            "project_id": 218,
            "user_id": 1818,
            "profile_id": "video_trend",
            "topic": "trend product",
            "prompt_text": "make a product trend video",
            "ratio": "9:16",
            "scene_count": 2,
            "asset_pack_json": json.dumps({"source": "product_video", "render_mode": "real", "provider_call": True, "public_user": True}),
            "invoice_json": json.dumps({"source": "product_video", "render_mode": "real", "provider_call": True, "public_user": True, "scene_count": 2}),
            "addon_plan_json": "{}",
        },
    }
    payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["render_pipeline_mode"] == "historical_multi_clip_concat"
    assert payload["clip_count"] == 2
    assert len(payload["provider_scene_tasks"]) == 2


def test_connector_multiscene_default_and_legacy_task_detection():
    assert connector.product_video_orchestration_mode({"source": "product_video", "scene_count": 2}) == "per_scene_8s"
    assert (
        connector.product_video_orchestration_mode(
            {
                "source": "product_video",
                "scene_count": 2,
                "provider_pending_task_id": "single-task",
                "provider_pending_request_job_id": "218",
            }
        )
        == "single_task_legacy"
    )


def test_shopaikey_per_scene_payload_uses_known_good_8s_clip_contract():
    request = VideoGenerationRequest(
        job_id="218-1",
        product_type="video_trend",
        prompt="A polished 8 second product trend clip.",
        scenes=[{"scene_id": 1, "prompt": "scene prompt"}],
        storyboard=[{"scene_id": 1}],
        image_paths=["/tmp/image.png"],
        source_video_path="/tmp/source.mp4",
        ratio="9:16",
        duration_seconds=16,
        metadata={
            "product_video": True,
            "scene_index": 1,
            "clip_index": 1,
            "orchestration_mode": "per_scene_8s",
            "render_pipeline_mode": "historical_multi_clip_concat",
        },
        required_capability="text_to_video",
    )
    payload = build_shopaikey_video_payload(
        request,
        {
            "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_SMALL_CLIP_SECONDS": "8",
        },
    )
    assert payload["duration"] == 8
    assert payload["duration_seconds"] == 8
    assert payload["model"] == "veo3.1-fast"
    assert "scenes" not in payload
    assert "storyboard" not in payload
    assert "image_paths" not in payload
    assert payload["metadata"]["payload_contract"] == "shopaikey_known_good_small_clip"


def test_debug_status_recover_paths_do_not_submit_in_r18c_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "run_provider" + "_generation(",
        "submit_video" + "_job(",
        "video_provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
