import json
import sqlite3
from pathlib import Path

import pytest

import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ADMIN_UID = 1


def _product_job(**overrides):
    job = {
        "job_id": "32",
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
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "aspect_ratio": "9:16",
        "original_user_prompt": "video AI sản phẩm thật, không chữ kỹ thuật trong khung hình",
        "addon_plan": {
            "voice_enabled": False,
            "music_enabled": False,
            "subtitle_enabled": False,
            "logo_enabled": False,
        },
        "scene_cards": [
            {
                "scene_index": index,
                "narration_line": f"Lời đọc cảnh {index}.",
                "subtitle_line": f"Phụ đề cảnh {index}.",
                "provider_prompt": f"Scene {index}: cinematic real product visual, no text in frame.",
            }
            for index in range(1, 4)
        ],
    }
    job.update(overrides)
    return job


def _ready_provider(*_args, **_kwargs):
    return {"ok": True, "provider_order": ["shopaikey"], "ready_provider_order": ["shopaikey"], "providers": []}


def _write_mp4(path: Path) -> str:
    path.write_bytes(b"real provider mp4")
    return str(path)


def _seed_product_job(conn: sqlite3.Connection):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "fake_renderer_allowed": False,
        "real_renderer_required": True,
        "provider_call": True,
        "public_user": False,
        "admin_only": True,
        "created_by_admin": True,
        "no_charge": True,
        "scene_count": 3,
        "duration_seconds": 18,
        "original_user_prompt": "job 32 provider attempt diagnostic",
    }
    project = queue.create_video_project(conn, user_id=ADMIN_UID, profile_id="product_review", topic="job32", ratio="9:16", asset_pack=asset_pack)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0},
        addon_plan_json={},
        scene_cards_json=_product_job()["scene_cards"],
        prompt_text="job 32 provider attempt diagnostic",
        total_xu_estimated=0,
        scene_count=3,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=ADMIN_UID, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_provider_ready_product_video_must_select_provider_route(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": False, "error": "provider_submit_failed"})

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path))

    diagnostics = exc.value.diagnostics
    assert diagnostics["provider_route_selected"] is True
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_error"] == "provider_submit_failed"


def test_provider_ready_product_video_must_attempt_provider_before_failed_no_real_visual(monkeypatch, tmp_path):
    output = tmp_path / "raw-prompt.mp4"
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(connector, "_subtitle_raw_prompt_burn_detected", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        connector,
        "process_multiscene_video_pipeline",
        lambda **_kwargs: {"ok": True, "final_video_path": _write_mp4(output), "scene_count": 3},
    )

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path))

    assert str(exc.value) == connector.FAILED_NO_REAL_VISUAL
    assert exc.value.diagnostics["provider_route_selected"] is True
    assert exc.value.diagnostics["provider_attempted"] is True


def test_failed_no_real_visual_not_allowed_before_provider_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": False, "error": connector.FAILED_NO_REAL_VISUAL})

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path))

    diagnostics = exc.value.diagnostics
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_route_selected"] is True
    assert diagnostics["provider_error"] == connector.FAILED_NO_REAL_VISUAL


def test_job32_payload_provider_attempted(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": False, "error": "provider_poll_timeout"})

    with pytest.raises(RuntimeError):
        remote_worker.render_real_video(_product_job(), str(tmp_path))

    result = remote_worker.LAST_REAL_VIDEO_RENDER_RESULT
    assert result["provider_route_selected"] is True
    assert result["provider_attempted"] is True
    assert result["provider_error"] == "provider_poll_timeout"


def test_subtitle_from_narration_voice_off_degrades_not_blocks_provider(monkeypatch, tmp_path):
    output = tmp_path / "subtitle-degrade.mp4"
    captured = {}
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)

    def fake_pipeline(**kwargs):
        captured["enable_subtitle"] = kwargs["enable_subtitle"]
        return {"ok": True, "final_video_path": _write_mp4(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    job = _product_job(addon_plan={"voice_enabled": False, "subtitle_enabled": True, "subtitle_source": "from_narration"})
    result = connector.render_real_video_job(job, str(tmp_path))
    assert "enable_subtitle" in captured
    assert result["provider_route_selected"] is True
    assert result["provider_attempted"] is True
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO


def test_music_default_does_not_block_provider_route(monkeypatch, tmp_path):
    output = tmp_path / "music-default.mp4"
    monkeypatch.setattr(connector, "_ffmpeg_binary", lambda: "")
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(
        connector,
        "process_multiscene_video_pipeline",
        lambda **kwargs: {"ok": True, "final_video_path": _write_mp4(output), "scene_count": kwargs["max_scenes"]},
    )
    result = connector.render_real_video_job(_product_job(addon_plan={"music_enabled": True, "music_source": "default"}), str(tmp_path))
    assert result["provider_route_selected"] is True
    assert result["provider_attempted"] is True
    assert any(item.get("addon") == "music" and item.get("applied") is False for item in result["addon_degrade_notes"])


def test_logo_text_does_not_block_provider_route(monkeypatch, tmp_path):
    output = tmp_path / "logo-text.mp4"
    captured = {}
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)

    def fake_pipeline(**kwargs):
        captured["enable_logo"] = kwargs["enable_logo"]
        captured["logo_position"] = kwargs["logo_position"]
        return {"ok": True, "final_video_path": _write_mp4(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    job = _product_job(addon_plan={"logo_enabled": True, "logo_text": "TOAN AAS", "logo_position": "top_right"})
    result = connector.render_real_video_job(job, str(tmp_path))
    assert captured == {"enable_logo": True, "logo_position": "top_right"}
    assert result["provider_route_selected"] is True
    assert result["provider_attempted"] is True


def test_provider_task_id_or_error_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)
    monkeypatch.setattr(connector, "_local_composer_enabled", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", lambda **_kwargs: {"ok": False})

    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job(), str(tmp_path))

    diagnostics = exc.value.diagnostics
    assert diagnostics["provider_attempted"] is True
    assert diagnostics["provider_task_ids"] or diagnostics["provider_error"]


def test_provider_error_admin_only_public_clean(monkeypatch, tmp_path):
    import bot

    db_path = tmp_path / "p0_18j.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", lambda _job_id: 0)
    conn = sqlite3.connect(db_path)
    queue.ensure_video_project_queue_schema(conn)
    try:
        _project, job = _seed_product_job(conn)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="vps-owner",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["ok"] is True
        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="vps-owner",
            job_id=int(job["id"]),
            safe_error="RuntimeError:provider_poll_timeout",
            retryable=False,
            diagnostics={
                "provider_route_selected": True,
                "provider_attempted": True,
                "provider_error": "shopaikey:poll_timeout",
                "provider_status": "attempted",
                "visual_classification": connector.FAILED_NO_REAL_VISUAL,
                "no_charge": True,
            },
        )
        assert result["ok"] is True
        row = queue.get_video_render_job(conn, int(job["id"]))
        payload = json.loads(row["result_json"])
        assert payload["provider_attempted"] is True
        assert payload["provider_error"] == "shopaikey:poll_timeout"
    finally:
        conn.close()

    debug = bot.video_render_debug_text(int(job["id"]), mode="video_render_debug")
    assert "provider attempted: <code>yes</code>" in debug
    assert "shopaikey:poll_timeout" in debug
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: queue.get_video_render_job(sqlite3.connect(db_path), int(job["id"])))
    public_text = bot.video_b14_queue_status_text(
        {"draft": {"b14_queue_job": {"id": int(job["id"]), "status": "failed"}, "b14_invoice": {"scene_count": 3, "duration_seconds": 18}}},
        None,
        999999,
        "vi",
    )
    assert "shopaikey" not in public_text.lower()
    assert "provider" not in public_text.lower()


def test_no_placeholder_final_success_preserved():
    assert connector.classify_visual_result({"ok": True, "renderer": "local_scene_composer", "placeholder_detected": True}) == connector.PARTIAL_SIMPLE_VIDEO
    assert connector.classify_visual_result({"ok": True, "renderer": "provider_scene_video", "provider_attempted": True}) == connector.FINAL_AI_VIDEO


def test_no_raw_prompt_subtitle_preserved(monkeypatch, tmp_path):
    output = tmp_path / "no-prompt-subtitle.mp4"
    captured = {}
    monkeypatch.setattr(connector, "real_video_provider_readiness", _ready_provider)

    def fake_pipeline(**kwargs):
        captured["enable_subtitle"] = kwargs["enable_subtitle"]
        return {"ok": True, "final_video_path": _write_mp4(output), "scene_count": kwargs["max_scenes"], "subtitle_path": None}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    job = _product_job(scene_cards=[], addon_plan={"subtitle_enabled": True}, original_user_prompt="chủ thể chính: demo sản phẩm")
    result = connector.render_real_video_job(job, str(tmp_path))
    assert captured["enable_subtitle"] is False
    assert result["raw_prompt_burned_into_frame"] is False
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO


def test_no_charge_without_final_ai_video(monkeypatch, tmp_path):
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": False, "ready_provider_order": [], "providers": []})
    with pytest.raises(connector.RealVideoRenderError) as exc_info:
        connector.render_real_video_job(_product_job(), str(tmp_path))
    diagnostics = exc_info.value.diagnostics
    assert diagnostics["blocker"] == "provider_capability_missing"
    assert diagnostics["provider_attempted"] is False
    assert diagnostics["no_charge"] is True
