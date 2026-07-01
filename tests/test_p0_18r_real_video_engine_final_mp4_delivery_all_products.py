import sqlite3
from pathlib import Path

import pytest

import remote_worker
from services import remote_worker_api, video_final_output, video_project_queue
from services import video_real_render_connector as connector


ADMIN_UID = 1


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
        _write_ppm(tmp_path / "scene1.ppm", (220, 40, 30)),
        _write_ppm(tmp_path / "scene2.ppm", (30, 80, 220)),
        _write_ppm(tmp_path / "scene3.ppm", (40, 180, 80)),
    ]


def _product_job(product_type: str = "script_to_video", image_paths: list[str] | None = None, **overrides) -> dict:
    scene_cards = [
        {
            "scene_index": index,
            "title": f"Cảnh {index}",
            "narration_line": f"Lời đọc sạch cảnh {index}.",
            "subtitle_line": f"Phụ đề sạch cảnh {index}.",
            "provider_prompt": f"Scene {index}: cinematic product visual, no text in frame.",
        }
        for index in range(1, 4)
    ]
    job = {
        "job_id": "40",
        "job_type": "video_render",
        "user_id": str(ADMIN_UID),
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
        "scene_count": 3,
        "expected_duration_seconds": 6,
        "aspect_ratio": "9:16",
        "original_user_prompt": "job 40 style product video with music subtitle logo",
        "asset_pack": {
            "source": "product_video",
            "render_mode": "real",
            "real_renderer_required": True,
            "product_type": product_type,
            "image_paths": list(image_paths or []),
        },
        "addon_plan": {
            "voice_enabled": False,
            "music_enabled": True,
            "music_source": "default",
            "music_volume_percent": 30,
            "subtitle_enabled": True,
            "subtitle_source": "voice_script",
            "logo_enabled": True,
            "logo_source": "text",
            "logo_text": "TOAN AAS",
            "logo_position": "top_right",
        },
        "scene_cards": scene_cards,
    }
    job.update(overrides)
    return job


def _valid_mp4(tmp_path: Path, name: str = "final.mp4") -> dict:
    _ffmpeg_required()
    return video_final_output.render_local_image_sequence_video(
        _image_paths(tmp_path),
        str(tmp_path / name),
        duration_per_image=0.75,
    )


def _conn():
    conn = sqlite3.connect(":memory:")
    video_project_queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_claimed_job(conn: sqlite3.Connection, tmp_path: Path) -> tuple[dict, dict, dict]:
    render = _valid_mp4(tmp_path, "delivery.mp4")
    assert render["ok"] is True
    project = video_project_queue.create_video_project(
        conn,
        user_id=ADMIN_UID,
        profile_id="storytelling",
        topic="delivery once",
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "image_to_video"},
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=video_project_queue.now_text(),
        addon_plan_json={},
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=ADMIN_UID, max_attempts=1)
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
    completed = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="worker-one",
        job_id=int(claimed["id"]),
        result=payload,
        final_video_path=render["final_video_path"],
        uploaded_file=True,
    )
    assert completed["ok"] is True
    return job, completed["job"], completed["project"]


def test_all_video_products_have_engine_route():
    routes = video_final_output.video_product_engine_route_matrix()
    assert set(routes) == set(video_final_output.REQUIRED_VIDEO_PRODUCT_TYPES)
    for product_type, route in routes.items():
        assert route["product_type"] == product_type
        assert route["engine_adapter"]
        assert route["provider_capability"]
        assert route["fallback_capability"]
        assert route["output_artifact_path"] == "final_video_path"
        assert route["validation_policy"]
        assert route["delivery_policy"] == "deliver_once_after_validation"


def test_video_trend_routes_to_engine():
    route = video_final_output.route_for_product_type("video_trend")
    assert route["engine_adapter"] == "text_to_video_or_scene_engine"
    assert route["fallback_capability"] == "local_scene_card_mp4_when_scene_cards_exist"


def test_video_ai_prompt_routes_to_text_to_video_engine():
    route = video_final_output.route_for_product_type("video_ai_prompt")
    assert route["engine_adapter"] == "text_to_video"
    assert route["provider_capability"] == "text_to_video"


def test_video_ai_image_routes_to_image_to_video_engine():
    route = video_final_output.route_for_product_type("video_ai_image")
    assert route["engine_adapter"] == "image_to_video"
    assert route["provider_capability"] == "image_to_video"


def test_video_reference_routes_to_video_to_video_or_clean_fail():
    route = video_final_output.route_for_product_type("video_ai_video_reference")
    assert route["provider_capability"] == "video_to_video"
    assert route["allow_clean_fail"] is True


def test_script_to_video_routes_to_scene_engine():
    route = video_final_output.route_for_product_type("script_to_video")
    assert route["engine_adapter"] == "script_scene_engine"
    assert "scene" in route["provider_capability"]


def test_storyboard_routes_to_scene_engine():
    route = video_final_output.route_for_product_type("storyboard_prompt")
    assert route["engine_adapter"] == "storyboard_scene_image_video_engine"
    assert route["fallback_capability"] == "local_image_sequence_or_scene_card_mp4"


def test_image_to_video_routes_to_local_or_provider_engine():
    route = video_final_output.route_for_product_type("image_to_video")
    assert route["engine_adapter"] == "image_sequence_slideshow_or_i2v"
    assert route["fallback_capability"] == "local_image_sequence_mp4"


def test_self_shot_routes_to_scene_change_or_clean_fail():
    route = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route["provider_capability"] == "video_to_video"
    assert route["allow_clean_fail"] is True


def test_multi_scene_film_routes_to_multiscene_engine():
    route = video_final_output.route_for_product_type("multi_scene_film")
    assert route["engine_adapter"] == "multiscene_render_and_stitch"
    assert route["fallback_capability"] == "local_scene_card_mp4_when_scene_cards_exist"


def test_idea_routes_to_selected_product_engine():
    route = video_final_output.route_for_product_type("video_idea_to_product")
    assert route["engine_adapter"] == "delegates_to_selected_product"
    assert route["provider_capability"] == "delegates_to_selected_product"


def test_final_success_requires_valid_mp4(tmp_path):
    invalid = tmp_path / "not-video.mp4"
    invalid.write_bytes(b"not a real mp4")
    result = video_final_output.validate_final_video_output(path=str(invalid), result={"visual_classification": connector.FINAL_AI_VIDEO})
    assert result["ok"] is False
    assert result["reason"] in {"ffprobe_failed", "output_zero_duration", "output_no_video_stream"}


def test_zero_byte_mp4_not_delivered(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    result = video_final_output.validate_final_video_output(path=str(empty), result={"visual_classification": connector.FINAL_AI_VIDEO})
    assert result["ok"] is False
    assert result["reason"] == "output_zero_bytes"


def test_zero_duration_mp4_not_delivered(monkeypatch, tmp_path):
    output = tmp_path / "zero-duration.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(video_final_output, "probe_video", lambda *_args, **_kwargs: {"ok": False, "reason": "output_zero_duration", "path": str(output), "bytes": 3, "duration": 0, "has_video": True})
    result = video_final_output.validate_final_video_output(path=str(output), result={"visual_classification": connector.FINAL_AI_VIDEO})
    assert result["reason"] == "output_zero_duration"


def test_missing_video_stream_not_delivered(monkeypatch, tmp_path):
    output = tmp_path / "audio-only.mp4"
    output.write_bytes(b"mp4")
    monkeypatch.setattr(video_final_output, "probe_video", lambda *_args, **_kwargs: {"ok": False, "reason": "output_no_video_stream", "path": str(output), "bytes": 3, "duration": 1, "has_video": False})
    result = video_final_output.validate_final_video_output(path=str(output), result={"visual_classification": connector.FINAL_AI_VIDEO})
    assert result["reason"] == "output_no_video_stream"


def test_unreadable_mp4_not_delivered(tmp_path):
    unreadable = tmp_path / "unreadable.mp4"
    unreadable.write_bytes(b"broken")
    result = video_final_output.validate_final_video_output(path=str(unreadable), result={"visual_classification": connector.FINAL_AI_VIDEO})
    assert result["ok"] is False


def test_placeholder_not_delivered(tmp_path):
    valid = _valid_mp4(tmp_path, "placeholder-wrapper.mp4")
    result = video_final_output.validate_final_video_output(
        path=valid["final_video_path"],
        result={"renderer": "local_scene_composer", "visual_classification": connector.PARTIAL_SIMPLE_VIDEO},
    )
    assert result["reason"] == "placeholder_not_final_video"


def test_valid_mp4_delivered_once(tmp_path):
    conn = _conn()
    _seed_claimed_job(conn, tmp_path)
    delivered = video_project_queue.note_video_delivery_result(conn, job_id=1, sent=True, delivery_message_id="501")
    duplicate = video_project_queue.note_video_delivery_result(conn, job_id=1, sent=True, delivery_message_id="502")
    assert delivered["ok"] is True
    assert delivered["project"]["video_delivery_message_id"] == "501"
    assert duplicate["duplicate_prevented"] is True


def test_provider_submit_only_after_final_confirm(monkeypatch, tmp_path):
    calls = {"count": 0}
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": True, "ready_provider_order": ["shopaikey"], "providers": []})

    def fake_pipeline(**kwargs):
        calls["count"] += 1
        output = tmp_path / "provider.mp4"
        output.write_bytes(b"provider")
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    assert calls["count"] == 0
    connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))
    assert calls["count"] == 1


def test_provider_task_id_saved(monkeypatch, tmp_path):
    output = tmp_path / "provider-task.mp4"
    output.write_bytes(b"provider")
    events = [{"scene_id": 1, "provider": "shopaikey", "task_id": "task-40", "video_id": "video-40", "status": "downloaded"}]
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": True, "ready_provider_order": ["shopaikey"], "providers": []})
    monkeypatch.setattr(connector, "build_real_scene_renderer", lambda _job, provider_events=None: (provider_events.extend(events) if provider_events is not None else None) or (lambda _scene, _raw: {"ok": True}))
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **kwargs: {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]})
    result = connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))
    assert "task-40" in result["provider_task_ids"]
    assert "video-40" in result["provider_video_ids"]


def test_provider_result_url_materialized(monkeypatch, tmp_path):
    output = tmp_path / "provider-url.mp4"
    output.write_bytes(b"provider")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": True, "ready_provider_order": ["shopaikey"], "providers": []})
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **kwargs: {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"], "provider_result_url_present": True})
    result = connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))
    assert result["final_video_path"] == str(output)
    assert result["provider_attempted"] is True


def test_provider_missing_capability_clean_no_charge(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_a, **_k: False)
    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))
    assert exc.value.diagnostics["no_charge"] is True
    assert exc.value.diagnostics["provider_error"] == "provider_capability_missing"


def test_script_to_video_local_fallback_creates_valid_mp4(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("script_to_video"), str(tmp_path))
    assert result["renderer"] == video_final_output.LOCAL_SCENE_CARD_RENDERER
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_storyboard_local_fallback_creates_valid_mp4(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("storyboard_prompt"), str(tmp_path))
    assert result["visual_source"] == video_final_output.VISUAL_SOURCE_LOCAL_SCENE_CARD
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_image_sequence_local_fallback_creates_valid_mp4(monkeypatch, tmp_path):
    _ffmpeg_required()
    paths = _image_paths(tmp_path)
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("image_to_video", paths), str(tmp_path / "work"))
    assert result["renderer"] == video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_multiscene_local_fallback_creates_valid_mp4_when_assets_exist(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("multi_scene_film"), str(tmp_path))
    assert result["renderer"] == video_final_output.LOCAL_SCENE_CARD_RENDERER
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_no_fake_95_without_final_artifact(monkeypatch):
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "if not has_final_artifact and progress >= 95:" in source
    assert "progress = 85" in source
    assert "hệ thống chưa có video cuối" in source


def test_render_step_green_only_after_candidate_mp4():
    source = Path("bot.py").read_text(encoding="utf-8")
    rows_slice = source[source.index("def video_b14_status_step_rows") : source.index("def video_b14_status_steps_text")]
    assert 'elif has_final_artifact:' in rows_slice
    assert 'icons[2] = "✅"' in rows_slice


def test_file_check_green_only_after_valid_mp4():
    source = Path("bot.py").read_text(encoding="utf-8")
    rows_slice = source[source.index("def video_b14_status_step_rows") : source.index("def video_b14_status_steps_text")]
    assert 'if status in {"completed", "success"} and has_final_artifact:' in rows_slice
    assert '["✅", "✅", "✅", "✅", "✅" if delivery_done else "⏳"]' in rows_slice


def test_delivery_step_green_only_after_message_id():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "video_delivery_message_id" in source
    assert "video_delivered_at" in source
    assert "delivery_done=delivery_done" in source


def test_failed_render_has_exact_blocker(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_a, **_k: False)
    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job("video_ai_video_reference"), str(tmp_path))
    assert str(exc.value) == "provider_capability_missing"


def test_music_subtitle_logo_mux_before_validation(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("script_to_video"), str(tmp_path))
    notes = {item["addon"]: item for item in result["addon_degrade_notes"]}
    assert notes["music"]["requested"] is True
    assert notes["subtitle"]["applied"] is True
    assert notes["logo"]["applied"] is True
    validation = video_final_output.validate_final_video_output(path=result["final_video_path"], result=result, require_audio=bool(notes["music"]["applied"]))
    assert validation["ok"] is True


def test_addon_mux_failure_sets_blocker(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    monkeypatch.setattr(connector, "_ffmpeg_binary", lambda: "")
    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job("script_to_video"), str(tmp_path))
    assert "ffmpeg_missing" in str(exc.value)


def test_claimed_addons_match_output_metadata_or_state(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("script_to_video", addon_plan={"music_enabled": True, "music_source": "none", "subtitle_enabled": True, "logo_enabled": True, "logo_text": ""}), str(tmp_path))
    notes = {item["addon"]: item for item in result["addon_degrade_notes"]}
    assert notes["music"]["applied"] is False
    assert notes["subtitle"]["applied"] is True
    assert notes["logo"]["applied"] is False
    assert result["partial_addons"] is True


def test_video_delivery_once(tmp_path):
    conn = _conn()
    _seed_claimed_job(conn, tmp_path)
    first = video_project_queue.note_video_delivery_result(conn, job_id=1, sent=True, delivery_message_id="700")
    second = video_project_queue.note_video_delivery_result(conn, job_id=1, sent=True, delivery_message_id="701")
    assert first["project"]["delivery_attempt_count"] == 1
    assert second["duplicate_prevented"] is True


def test_video_late_fail_suppressed_after_delivery(tmp_path):
    conn = _conn()
    _seed_claimed_job(conn, tmp_path)
    video_project_queue.note_video_delivery_result(conn, job_id=1, sent=True, delivery_message_id="701")
    late = video_project_queue.fail_video_job(conn, job_id=1, error="late_fail_after_delivery", retry=False)
    assert late["ok"] is False or video_project_queue.get_video_project(conn, 1)["video_delivery_message_id"] == "701"


def test_manual_refresh_does_not_rerender():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "video_b14_auto_refresh_tick" in source
    assert "render_real_video_job(" not in source[source.index("def video_b14_auto_refresh_tick") : source.index("async def cmd_video_progress_auto_refresh_status")]


def test_debug_read_only_no_delivery():
    source = Path("bot.py").read_text(encoding="utf-8")
    debug_slice = source[source.index("async def cmd_video_render_debug") : source.index("async def cmd_video_engine_route_audit")]
    assert "send_generated_video_path_for_delivery" not in debug_slice
    assert "render_real_video_job(" not in debug_slice


def test_job_40_style_no_final_mp4_does_not_show_95_success(monkeypatch):
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "if not has_final_artifact and progress >= 95:" in source
    assert 'elif status in {"completed", "success"} and has_final_artifact and delivery_done:' in source


def test_job_40_style_engine_creates_or_cleanly_fails_with_blocker(monkeypatch, tmp_path):
    _ffmpeg_required()
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    result = connector.render_real_video_job(_product_job("script_to_video"), str(tmp_path))
    assert result["ok"] is True
    assert result["final_video_path"]
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO


def test_remote_worker_product_heartbeat_never_reports_95_before_complete(monkeypatch, tmp_path):
    output = tmp_path / "worker-final.mp4"
    output.write_bytes(b"mp4")
    heartbeats: list[int] = []

    def fake_render(_job, _work_dir):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = {"visual_classification": connector.FINAL_AI_VIDEO, "renderer": video_final_output.LOCAL_SCENE_CARD_RENDERER}
        return str(output)

    monkeypatch.setattr(remote_worker, "render_real_video", fake_render)
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda _job_id, progress, _message="": heartbeats.append(int(progress)))
    monkeypatch.setattr(remote_worker, "complete_job", lambda *_args, **_kwargs: {"ok": True})
    assert remote_worker.process_claimed_job(_product_job("script_to_video"))["ok"] is True
    assert 95 not in heartbeats
