import asyncio
import inspect
import json
import os
import sqlite3
import subprocess

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import video_project_queue, video_provider_router
from services.video_provider_base import VideoGenerationRequest


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    except Exception:
        return ""


def _is_subdub_scope_branch(branch: str) -> bool:
    lowered = str(branch or "").lower()
    return any(token in lowered for token in ("p0-19m", "subdub", "subtitle-dub", "subtitle_dub"))


def _is_video_preflight_scope_branch(branch: str) -> bool:
    lowered = str(branch or "").lower()
    return any(token in lowered for token in ("p0-18vroot", "video-provider-preflight", "video_debug_x"))


def _env(chain: str = "shopaikey_video,key4u_video") -> dict[str, str]:
    return {
        "VIDEO_PROVIDER_CHAIN": chain,
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


def _request() -> VideoGenerationRequest:
    return VideoGenerationRequest(
        job_id="70-1",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="Tao video san pham ngan theo trend",
        ratio="9:16",
        duration_seconds=6,
        required_capability="text_to_video_or_scene_video",
        metadata={"product_video": True, "allow_provider_pending": True},
    )


def _shopaikey_no_channel(provider: str = "shopaikey_video") -> dict:
    return {
        "ok": False,
        "status_code": 500,
        "body": {
            "code": "get_channel_failed",
            "message": "no available channel for group cheap,gemini,claude_code,veo_3,veo_1,veo_2 model veo3.1-fast (retry)",
        },
        "response_shape": {"type": "dict", "top_level_keys": ["code", "message"], "nested_keys": []},
    }


def _key4u_503(provider: str = "key4u_video") -> dict:
    return {
        "ok": False,
        "status_code": 503,
        "body": {"type": "service_unavailable", "message": f"{provider} temporarily unavailable"},
        "response_shape": {"type": "dict", "top_level_keys": ["message", "type"], "nested_keys": []},
    }


def _job70_result() -> dict:
    return {
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "initial_selected_provider": "shopaikey_video",
        "selected_provider": "key4u_video",
        "selected_provider_before_submit": "key4u_video",
        "provider_fallback_attempted": True,
        "provider_submit_called": True,
        "provider_submit_http_status": 503,
        "provider_submit_http_5xx": True,
        "submit_accepted": False,
        "provider_task_id_saved": False,
        "provider_error": "all_video_providers_submit_unavailable",
        "blocker": "all_video_providers_submit_unavailable",
        "terminal_state": "failed_no_charge",
        "no_charge": True,
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "phase": "submit",
                "submit_called": True,
                "submit_http_status": 500,
                "submit_accepted": False,
                "task_id_present": False,
                "blocker": "provider_capacity_unavailable",
                "safe_error": "code=get_channel_failed; message=no available channel for group cheap,gemini,claude_code,veo_3,veo_1,veo_2 model veo3.1-fast (retry)",
            },
            {
                "provider": "key4u_video",
                "phase": "submit",
                "submit_called": True,
                "submit_http_status": 503,
                "submit_accepted": False,
                "task_id_present": False,
                "blocker": "provider_temporarily_unavailable",
                "safe_error": "provider temporarily unavailable",
            },
        ],
    }


def _job70_conn() -> tuple[sqlite3.Connection, int]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    project = video_project_queue.create_video_project(
        conn,
        user_id=70,
        profile_id="video_trend",
        topic="job70",
        asset_pack={"source": "product_video", "render_mode": "real", "provider_call": True, "product_type": "video_trend", "scene_count": 3},
    )
    video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        total_xu_estimated=300,
        scene_count=3,
        video_terminal_state="failed_no_charge",
        charged_xu=0,
    )
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=70)
    conn.execute(
        "UPDATE video_jobs SET result_json=?, status=?, progress_percent=?, last_error=? WHERE id=?",
        (json.dumps(_job70_result()), "failed", 20, "all_video_providers_submit_unavailable", int(job["id"])),
    )
    conn.commit()
    return conn, int(job["id"])


class _StrictMessage:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text, **kwargs):
        assert len(str(text)) <= 4096
        self.texts.append(str(text))
        return {"ok": True}


class _User:
    id = 1


class _Update:
    effective_user = _User()

    def __init__(self):
        self.message = _StrictMessage()


class _Context:
    def __init__(self, args=None):
        self.args = list(args or [])


def test_video_provider_status_never_generic_fails_with_provider_500_503_shape():
    import bot

    providers = []
    for name in ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"]:
        providers.append(
            {
                "provider": name,
                "enabled": name in {"shopaikey_video", "key4u_video"},
                "configured": name in {"shopaikey_video", "key4u_video"},
                "submit_url_present": name in {"shopaikey_video", "key4u_video"},
                "poll_url_present": name in {"shopaikey_video", "key4u_video"},
                "auth_present": name in {"shopaikey_video", "key4u_video"},
                "model_present": name in {"shopaikey_video", "key4u_video"},
                "credit_status": "low" if name == "key4u_video" else "unknown",
                "fallback_only": name == "key4u_video",
                "blocker": "provider_capacity_unavailable" if name == "shopaikey_video" else "provider_temporarily_unavailable",
                "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            }
        )
    text = bot.video_provider_status_text(
        {
            "ready": False,
            "summary_reason": "all_configured_providers_unavailable",
            "effective_provider_chain": [item["provider"] for item in providers],
            "first_ready_provider": "-",
            "selection_reason": "provider_capacity_unavailable",
            "fallback_order": ["key4u_video", "toanaas_video", "veo", "kling", "generic_http"],
            "enabled_count": 2,
            "configured_count": 2,
            "providers": providers,
        },
        key4u_credit={"credit": "low", "reason": "key4u almost exhausted " * 30},
    )

    assert "Trạng thái nhà cung cấp video" in text
    assert "shopaikey_video" in text
    assert "key4u_video" in text
    assert "debug_truncated" in text
    assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "shop-secret" not in text


def test_video_render_debug_never_generic_fails_for_job_70_shape(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    text = bot.video_render_debug_text(job_id)

    assert "Video Render Debug" in text
    assert "debug_truncated" in text
    assert "shopaikey_video" in text
    assert "key4u_video" in text
    assert "all_video_providers_submit_unavailable" in text
    assert "charge: <code>0</code>" in text
    assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT
    assert "Có lỗi khi xử lý lệnh" not in text


def test_video_render_debug_truncates_long_provider_error_safely(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    long_secret = "sk-secret-should-not-leak"
    result = _job70_result()
    result["provider_attempts"][0]["safe_error"] = "no available channel " * 200 + long_secret
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(result), job_id))
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_render_debug_text(job_id)

    assert len(text) <= bot.VIDEO_DEBUG_REPLY_LIMIT
    assert "no available channel" in text
    assert long_secret not in text
    assert "<code>" in text


def test_video_render_debug_handles_provider_attempts_list_without_task_id(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_provider_job_debug_text(job_id)

    assert "Video Provider Job Debug" in text
    assert "provider task id saved: <code>no</code>" in text
    assert "Provider attempts:" in text
    assert "provider_capacity_unavailable" in text


def test_video_debug_commands_send_compact_output_not_generic(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _Update()

    asyncio.run(bot.cmd_video_render_debug(update, _Context([str(job_id)])))

    assert update.message.texts
    assert "Video Render Debug" in update.message.texts[0]
    assert "Có lỗi khi xử lý lệnh" not in update.message.texts[0]


def test_no_secret_leak_in_debug_commands(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    result = _job70_result()
    result["provider_attempts"][0]["safe_error"] = "Authorization=Bearer abc-secret-token"
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(result), job_id))
    conn.commit()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    text = bot.video_render_debug_text(job_id)

    assert "abc-secret-token" not in text
    assert "Bearer" not in text or "***" in text


def test_provider_capacity_unavailable_classifies_shopaikey_get_channel_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _shopaikey_no_channel(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env("shopaikey_video"),
        sleep_func=lambda _seconds: None,
    )

    assert result["provider_submit_blocker"] == "provider_capacity_unavailable"
    assert result["provider_submit_http_5xx"] is True
    assert result["no_charge"] is True


def test_key4u_503_classified_temporarily_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", lambda self, *_a, **_k: _key4u_503(self.provider_name))

    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env("key4u_video"),
        sleep_func=lambda _seconds: None,
    )

    assert result["provider_submit_blocker"] == "provider_temporarily_unavailable"
    assert result["provider_submit_http_status"] == 503
    assert result["no_charge"] is True


def test_primary_unavailable_requires_confirmation_before_paid_fallback(monkeypatch, tmp_path):
    def fake_open(self, *_args, **_kwargs):
        return _shopaikey_no_channel(self.provider_name) if self.provider_name == "shopaikey_video" else _key4u_503(self.provider_name)

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open)
    result = video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )

    assert result["blocker"] == "paid_fallback_requires_confirmation"
    assert result["paid_retry_requires_confirmation"] is True
    assert result["external_provider_spend_prevented"] is True
    assert result["no_charge"] is True
    assert not result.get("output_path")


def test_provider_unavailable_public_copy_has_no_debug_terms():
    import bot

    text = bot.PRODUCT_VIDEO_PROVIDER_BUSY_COPY_VI

    assert "chưa trừ Xu" in text
    for forbidden in ("provider", "API", "http", "debug", "worker", "payload"):
        assert forbidden.lower() not in text.lower()


def test_no_charge_when_provider_preflight_blocks_job():
    import bot

    conn, _job_id = _job70_conn()
    result = bot.product_video_provider_availability_preflight(conn)

    assert result["ok"] is False
    assert result["job_creation_blocked_by_provider_availability"] is True
    assert result["no_charge_reason"] == "provider_preflight_all_unavailable"
    assert result["unavailable_reason_by_provider"]["shopaikey_video"] == "provider_capacity_unavailable"
    assert result["unavailable_reason_by_provider"]["key4u_video"] == "provider_temporarily_unavailable"
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1


def test_one_available_provider_allows_job():
    import bot

    conn, job_id = _job70_conn()
    partial = _job70_result()
    partial["configured_provider_chain"] = ["shopaikey_video", "key4u_video"]
    partial["provider_attempts"] = [partial["provider_attempts"][0]]
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(partial), job_id))
    conn.commit()

    result = bot.product_video_provider_availability_preflight(conn)

    assert result["ok"] is True
    assert result["job_creation_blocked_by_provider_availability"] is False


def test_job_70_all_providers_submit_failed_shape_renders_all_debug(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)

    render_text = bot.video_render_debug_text(job_id)
    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    provider_text = bot.video_provider_job_debug_text(job_id)

    assert "shopaikey_video" in render_text
    assert "key4u_video" in render_text
    assert "shopaikey_video" in provider_text
    assert "key4u_video" in provider_text
    assert "charge: <code>0</code>" in provider_text


def test_progress_status_debug_existing_failed_job_70_recovered_from_db(monkeypatch):
    import bot

    conn, job_id = _job70_conn()
    monkeypatch.setattr(bot, "db_connect", lambda: conn)
    monkeypatch.setattr(bot, "PROGRESS_AUTO_REFRESH_JOBS", {})

    text = bot.product_progress_debug_text(str(job_id), "", {})

    assert "recovered_from_db_for_status_debug: <code>yes</code>" in text
    assert "persisted_job_status: <code>failed</code>" in text
    assert "Percent: <code>20%</code>" in text


def test_no_subdub_music_payos_pricing_db_changes():
    branch = _current_branch_name()
    if _is_subdub_scope_branch(branch) or not _is_video_preflight_scope_branch(branch):
        return
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main...HEAD"], text=True).splitlines()
    forbidden = (
        "services/subtitle",
        "services/subdub",
        "services/music",
        "providers/key4u_provider.py",
        "payos",
        "wallet",
        "pricing",
        "finance",
        "migrations",
    )
    offenders = [path for path in changed if any(term.lower() in path.lower() for term in forbidden)]
    assert offenders == []


def test_no_subdub_guard_exempts_subdub_branch_only():
    assert _is_subdub_scope_branch("hotfix/p0-19m6x-remove-public-srt-fallback")
    assert _is_subdub_scope_branch("hotfix/subdub-output-polish")
    assert not _is_subdub_scope_branch("hotfix/p0-18vroot-video-provider-preflight")
    assert _is_video_preflight_scope_branch("hotfix/p0-18vroot-video-provider-preflight")
    assert not _is_video_preflight_scope_branch("hotfix/p0-23h14k-music-pr173-vocal-lyrics-route-fix")


def test_no_fake_placeholder_success():
    import bot

    source = inspect.getsource(bot.video_render_debug_text) + inspect.getsource(video_provider_router.run_provider_generation)

    assert "placeholder_not_final_video" in source or "placeholder_forbidden" in source
    assert "fake_renderer_allowed\": True" not in source
