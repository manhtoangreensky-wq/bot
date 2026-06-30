import sqlite3
from pathlib import Path

import pytest

import bot
import video_product_system
from services import remote_worker_api, video_final_output, video_project_queue
from services import video_real_render_connector as connector


def _ffmpeg_required():
    ffmpeg = video_final_output.ffmpeg_path()
    ffprobe = video_final_output.ffprobe_path(ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available")
    return ffmpeg, ffprobe


def _write_ppm(path: Path, rgb: tuple[int, int, int]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    r, g, b = rgb
    pixels = " ".join(f"{r} {g} {b}" for _ in range(48 * 48))
    path.write_text(f"P3\n48 48\n255\n{pixels}\n", encoding="ascii")
    return str(path)


def _image_paths(tmp_path: Path) -> list[str]:
    return [
        _write_ppm(tmp_path / "red.ppm", (220, 40, 30)),
        _write_ppm(tmp_path / "blue.ppm", (30, 80, 220)),
    ]


def _product_job(product_type: str, image_paths: list[str] | None = None, **overrides) -> dict:
    job = {
        "job_id": "p0-18p",
        "job_type": "video_render",
        "user_id": "1",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "provider_call": True,
        "public_user": False,
        "admin_only": True,
        "no_charge": True,
        "product_type": product_type,
        "scene_count": max(1, len(image_paths or []) or 1),
        "expected_duration_seconds": max(2, len(image_paths or []) * 2),
        "aspect_ratio": "9:16",
        "original_user_prompt": "product video with real local image scenes",
        "asset_pack": {
            "source": "product_video",
            "render_mode": "real",
            "real_renderer_required": True,
            "product_type": product_type,
            "image_paths": list(image_paths or []),
        },
        "addon_plan": {"voice_enabled": False, "music_enabled": False, "subtitle_enabled": False, "logo_enabled": False},
    }
    job.update(overrides)
    return job


def _conn():
    conn = sqlite3.connect(":memory:")
    video_project_queue.ensure_video_project_queue_schema(conn)
    return conn


def test_image_to_video_local_engine_outputs_valid_mp4(monkeypatch, tmp_path):
    _ffmpeg_required()
    paths = _image_paths(tmp_path)
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})

    result = connector.render_real_video_job(_product_job("image_to_video", paths), str(tmp_path / "work"))

    assert result["ok"] is True
    assert result["renderer"] == video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER
    assert result["visual_source"] == video_final_output.VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO
    validation = video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)
    assert validation["ok"] is True
    assert validation["duration"] > 0
    assert validation["has_video"] is True


def test_storyboard_with_images_outputs_valid_mp4(monkeypatch, tmp_path):
    _ffmpeg_required()
    paths = _image_paths(tmp_path)
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    job = _product_job(
        "storyboard_prompt",
        [],
        scene_cards=[
            {"scene_index": 1, "image_path": paths[0], "video_prompt": "opening image scene"},
            {"scene_index": 2, "image_path": paths[1], "video_prompt": "closing image scene"},
        ],
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "storyboard_prompt"},
        scene_count=2,
        expected_duration_seconds=4,
    )

    result = connector.render_real_video_job(job, str(tmp_path / "storyboard-work"))

    assert result["ok"] is True
    assert result["renderer"] == video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER
    assert result["image_count"] == 2
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_prompt_video_without_provider_fails_clean_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))

    assert str(exc.value) == connector.REAL_VIDEO_RENDER_UNAVAILABLE
    assert exc.value.diagnostics["no_charge"] is True
    assert exc.value.diagnostics["provider_attempted"] is False


def test_video_final_success_requires_valid_mp4(tmp_path):
    invalid = tmp_path / "not-video.mp4"
    invalid.write_bytes(b"not a real mp4")
    result = video_final_output.validate_final_video_output(
        path=str(invalid),
        result={"renderer": video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER, "visual_classification": connector.FINAL_AI_VIDEO},
    )
    assert result["ok"] is False
    assert result["reason"] in {"ffprobe_failed", "output_zero_duration", "output_no_video_stream"}


def test_draft_not_final_delivered():
    result = video_final_output.validate_final_video_output(
        path="",
        result={"renderer": "local_scene_composer", "visual_classification": connector.PARTIAL_SIMPLE_VIDEO},
    )
    assert result["ok"] is False
    assert result["reason"] == "placeholder_not_final_video"


def test_video_delivery_once(monkeypatch, tmp_path):
    _ffmpeg_required()
    paths = _image_paths(tmp_path)
    render = video_final_output.render_local_image_sequence_video(paths, str(tmp_path / "final.mp4"), duration_per_image=1.0)
    assert render["ok"] is True
    conn = _conn()
    project = video_project_queue.create_video_project(
        conn,
        user_id=1,
        profile_id="storytelling",
        topic="delivery once",
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "image_to_video"},
    )
    project = video_project_queue.update_video_project(conn, int(project["project_id"]), status="queued_for_worker", is_confirmed=1, addon_plan_json={})
    video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=1)
    claimed = video_project_queue.claim_next_video_job(conn, worker_id="worker-one")
    payload = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "connector_renderer": video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER,
        "visual_source": video_final_output.VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE,
        "visual_classification": connector.FINAL_AI_VIDEO,
        "final_classification": connector.FINAL_AI_VIDEO,
    }

    first = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="worker-one",
        job_id=int(claimed["id"]),
        result=payload,
        final_video_path=render["final_video_path"],
        uploaded_file=True,
    )
    second = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="worker-one",
        job_id=int(claimed["id"]),
        result=payload,
        final_video_path=render["final_video_path"],
        uploaded_file=True,
    )

    assert first["ok"] is True
    assert first["project"]["video_terminal_state"] == "final_delivered"
    assert second["ok"] is True
    assert second["duplicate"] is True


def test_video_status_no_95_without_final_artifact(monkeypatch):
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: {})
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    text = bot.video_b14_queue_status_text(
        {
            "draft": {
                "b14_queue_job": {"id": 18, "status": "processing", "progress_percent": 95},
                "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "quality_xu": 300},
            }
        },
        None,
        1,
        "vi",
    )
    assert "95%" not in text
    assert "85%" in text


def test_video_debug_read_only():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "video_job_debug" in source
    assert "video_render_debug" in source
    assert "video_delivery_debug" in source


def test_no_video_flow_menu_changed():
    assert video_product_system.VIDEO_MENU_ROWS == (
        ("video_trend", "video_idea"),
        ("storyboard_prompt", "motion_prompt"),
        ("video_ai_real", "script_image_video"),
        ("image_to_video", "frame_video_local"),
        ("self_shot_scene_change", "multi_scene_film"),
        ("video_reference", "audio_addons"),
        ("video_local_edit", "main_menu"),
    )
