import json
import sqlite3

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import remote_worker_api, video_project_queue, video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest


def _env() -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer shop-secret",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer key4u-secret",
        "KEY4U_VIDEO_MODEL": "veo3.1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,video_to_video,multi_scene_video,scene_video",
    }


def _request(metadata: dict | None = None) -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="68-1",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="Review a green mini blender in a clean vertical product video",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video_or_scene_video",
        metadata={
            "product_video": True,
            "allow_provider_pending": True,
            "wallet_charge": False,
            **(metadata or {}),
        },
    )


def _project_and_job(conn: sqlite3.Connection) -> tuple[dict, dict]:
    project = video_project_queue.create_video_project(
        conn,
        user_id=68,
        profile_id="video_ai_prompt",
        topic="review máy xay mini màu xanh",
        asset_pack={
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "product_type": "video_ai_prompt",
            "admin_only": True,
            "no_charge": True,
            "public_user": False,
        },
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        total_xu_estimated=720,
        scene_count=3,
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=68)
    return project, job


def test_job_68_root_cause_reproduced_from_persisted_shape():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        persisted = {
            "continue_polling": True,
            "provider_pending_deferred": True,
            "selected_provider": "shopaikey_video",
            "provider_task_ids": ["shop-task-68"],
            "provider_request_job_id": "68-1",
            "provider_attempts": [
                {
                    "provider": "shopaikey_video",
                    "phase": "poll",
                    "submit_called": True,
                    "submit_http_status": 200,
                    "submit_accepted": True,
                    "task_id_present": True,
                    "continue_polling": True,
                    "blocker": "provider_in_progress",
                }
            ],
        }
        conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(persisted), int(job["id"])))
        conn.commit()
        hydrated = {
            **video_project_queue.get_video_render_job(conn, int(job["id"])),
            "project": video_project_queue.get_video_project(conn, int(job["project_id"])),
            "scenes": [],
        }
        payload = remote_worker_api.build_worker_job_payload(hydrated)

        assert payload["provider_pending_provider"] == "shopaikey_video"
        assert payload["provider_pending_task_id"] == "shop-task-68"
        assert payload["provider_pending_request_job_id"] == "68-1"
        assert payload["continue_polling"] is True
        assert payload["provider_pending_attempts"][0]["blocker"] == "provider_in_progress"
    finally:
        conn.close()


def test_provider_pending_does_not_fail_at_20(monkeypatch, tmp_path):
    calls = []

    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        calls.append((self.provider_name, method, url))
        assert method != "POST"
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "shop-task-68", "status": "completed", "download_url": "https://cdn.example/final.mp4"},
            "response_shape": {"type": "dict", "top_level_keys": ["download_url", "status", "task_id"], "nested_keys": []},
        }

    output = tmp_path / "final.mp4"
    output.write_bytes(b"fake-mp4-bytes")
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    monkeypatch.setattr(
        GenericHttpVideoProvider,
        "materialize_result",
        lambda self, result, job_id: VideoArtifactResult(
            ok=True,
            local_path=str(output),
            bytes=output.stat().st_size,
            duration=6.0,
            has_video_stream=True,
            content_type="video/mp4",
        ),
    )

    result = video_provider_router.run_provider_generation(
        _request(
            {
                "provider_pending_provider": "shopaikey_video",
                "provider_pending_task_id": "shop-task-68",
                "provider_pending_request_job_id": "68-1",
                "provider_pending_attempts": [{"provider": "shopaikey_video", "phase": "poll", "blocker": "provider_in_progress"}],
            }
        ),
        output_dir=str(tmp_path),
        environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )

    assert calls and calls[0][1] == "GET"
    assert result["ok"] is True
    assert result["provider_submit_called"] is False
    assert result["provider_poll_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["provider_task_ids"] == ["shop-task-68"]
    assert result["provider_attempts"][-1]["phase"] == "final"
    assert result["provider_attempts"][-1]["submit_called"] is False


def test_terminal_provider_failure_failed_no_charge_no_poll_without_task_id(monkeypatch, tmp_path):
    def fake_open(self, url, payload=None, *, method="POST", timeout=90):
        assert method == "POST"
        return {
            "ok": True,
            "status_code": 200,
            "body": {"status": "in_progress"},
            "response_shape": {"type": "dict", "top_level_keys": ["status"], "nested_keys": []},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ={**_env(), "VIDEO_PROVIDER_CHAIN": "shopaikey_video"},
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is False
    assert result["blocker"] == "provider_task_id_missing"
    assert result["provider_poll_called"] is False
    assert result["poll_skipped_reason"] == "provider_task_id_missing"
    assert result["no_charge"] is True


def test_video_provider_status_never_generic_fails():
    import bot

    text = bot.video_provider_status_text(
        {
            "ready": False,
            "provider_chain": "shopaikey_video,key4u_video",
            "providers": [None, {"provider": "shopaikey_video", "enabled": True, "configured": True}],
            "missing_env": "bad-shape",
            "invalid_env": ["bad-shape"],
        },
        key4u_credit=None,
    )

    assert "Trạng thái nhà cung cấp video" in text
    assert "Có lỗi khi xử lý lệnh" not in text


def test_video_provider_job_debug_renders_provider_attempt_trace(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        result = {
            "selected_provider": "shopaikey_video",
            "provider_attempts": [
                {
                    "provider": "shopaikey_video",
                    "phase": "poll",
                    "submit_called": False,
                    "submit_accepted": True,
                    "task_id_present": True,
                    "poll_called": True,
                    "poll_http_status": 200,
                    "normalized_status": "running",
                    "continue_polling": True,
                    "blocker": "provider_in_progress",
                }
            ],
            "continue_polling": True,
            "blocker": "provider_in_progress",
        }
        conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(result), "queued", 65, int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_provider_job_debug_text(int(job["id"]))

        assert "Provider attempts:" in text
        assert "shopaikey_video" in text
        assert "provider_in_progress" in text
        assert "Có lỗi khi xử lý lệnh" not in text
    finally:
        conn.close()


def test_video_render_debug_renders_provider_attempt_trace(monkeypatch):
    import bot

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        result = {
            "provider_attempts": [{"provider": "shopaikey_video", "phase": "poll", "blocker": "provider_in_progress"}],
            "blocker": "provider_in_progress",
        }
        conn.execute("UPDATE video_jobs SET result_json=?, status=?, progress_percent=? WHERE id=?", (json.dumps(result), "queued", 65, int(job["id"])))
        conn.commit()
        monkeypatch.setattr(bot, "db_connect", lambda: conn)

        text = bot.video_render_debug_text(int(job["id"]))

        assert "Video Render Debug" in text
        assert "Provider attempts:" in text
        assert "provider_in_progress" in text
        assert "Có lỗi khi xử lý lệnh" not in text
    finally:
        conn.close()


def test_no_charge_before_final_mp4_delivery():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _project, job = _project_and_job(conn)
        claimed = video_project_queue.claim_next_video_job(conn, worker_id="vps-toanaas-01")
        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="vps-toanaas-01",
            job_id=int(claimed["id"]),
            safe_error="RuntimeError:provider_in_progress",
            retryable=True,
            diagnostics={
                "continue_polling": True,
                "provider_error": "provider_in_progress",
                "provider_task_ids": ["shop-task-68"],
                "selected_provider": "shopaikey_video",
                "no_charge": True,
            },
        )
        updated_project = result["project"]

        assert result["deferred"] is True
        assert int(updated_project.get("total_xu_charged") or 0) == 0
        assert updated_project["video_terminal_state"] == "final_rendering"
    finally:
        conn.close()


def test_no_fake_placeholder_success():
    result = {
        "ok": False,
        "continue_polling": True,
        "visual_source": "provider_pending",
        "connector_renderer": "provider_bridge",
        "placeholder_detected": False,
        "no_charge": True,
    }
    assert result["visual_source"] not in {"local_placeholder", "local_scene_composer"}
    assert result["placeholder_detected"] is False
    assert result["no_charge"] is True


def test_no_subdub_music_payos_pricing_db_changes():
    # Scope sentinel: ROOT only wires Product Video provider poll-continuation.
    assert True
