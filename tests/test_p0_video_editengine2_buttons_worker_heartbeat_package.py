from __future__ import annotations

from pathlib import Path

import pytest

import local_worker
from services import video_editengine1
from services import video_uifreeze1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")


def _section(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _state() -> dict:
    return {
        "product_type": "video_edit",
        "flow_owner": "video_edit",
        "engine_route": "local_worker_ffmpeg",
        "worker_owner": "local_video_edit",
        "source_file_id": "telegram-source",
        "inspection_complete": True,
        "source_metadata": {
            "ok": True,
            "duration": 4.0,
            "duration_ms": 4_000,
            "has_audio": True,
        },
        "selected_tool": "manual",
        "manual_edit_plan": {
            "source": "source.mp4",
            "trim": {"start_ms": 0, "end_ms": 4_000},
            "brightness_percent": 200,
        },
        "video_tail9": {"audio_config": {}},
    }


def _runtime(**overrides) -> dict:
    runtime = {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "heartbeat_contract_version": 1,
        "worker_id": "video-edit-worker",
        "worker_owner": "local_video_edit",
        "engine_route": "local_worker_ffmpeg",
        "capabilities": ["video_edit"],
        "heartbeat_age_seconds": 1,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "delivery_configured": True,
    }
    runtime.update(overrides)
    return runtime


def test_video_edit_review_has_only_exact_product_buttons() -> None:
    section = _section(
        BOT_SOURCE,
        "def video_tail9_video_edit_review_keyboard",
        "def video_tail9_video_edit_operations_text",
    )
    expected = {
        "video_tail|review|operations",
        "video_tail|review|edit_operation",
        "video_tail|audio|open",
        "video_tail|logo|open",
        "video_tail|review|summary",
        "video_tail|review|source",
        "video_tail|review|back",
        "menu|main",
    }
    assert all(callback in section for callback in expected)
    assert "video_tail|quality|open" not in section
    assert "review|scenes" not in section
    assert "review|prompts" not in section
    assert "review|redo" not in section


def test_brightness_200_routes_directly_to_video_edit_review() -> None:
    section = _section(
        BOT_SOURCE,
        "async def handle_video_editor_callback",
        "async def handle_video_upload_callback",
    )
    route = _section(section, 'if action == "brightness_set":', 'if action == "brightness_custom":')
    assert '"brightness_percent": percent' in route
    assert '"operation": "brightness"' in route
    assert 'current_screen="review"' in route
    assert 'return await video_tail9_render(query, uid, context, "review")' in route
    review = _section(section, 'if action == "review":', 'if action == "start":')
    assert 'video_tail9_render(query, uid, context, "review")' in review


def test_video_intake_preserves_canonical_owner_and_source_state() -> None:
    section = _section(
        BOT_SOURCE,
        "async def handle_video_editor_pending_upload",
        "async def handle_video_editor_invalid_intake_text",
    )
    assert "set_video_editor_pending(" not in section
    assert section.count("update_video_editor_pending(") >= 2
    assert "source_video_id=str(source.get(\"source_file_id\")" in section
    assert "source_has_audio=bool(" in section
    assert 'status="source_ready"' in section
    assert "state_revision=" in section
    assert "revision=" in section


def test_video_edit_owner_gets_exact_review_not_scene3_review() -> None:
    section = _section(BOT_SOURCE, "async def video_tail9_render", "async def handle_video_tail_callback")
    owner_branch = _section(section, 'if owner == "video_edit":', "return await safe_edit_or_send(query, video_tail9_review_text")
    assert "video_tail9_video_edit_review_text" in owner_branch
    assert "video_tail9_video_edit_review_keyboard" in owner_branch
    assert "video_tail9_review_keyboard()" not in owner_branch


def test_shared_tail_has_one_callback_owner_and_claims_each_callback_once() -> None:
    registration = 'CallbackQueryHandler(handle_video_tail_callback, pattern=r"^video_tail\\|", block=True)'
    assert BOT_SOURCE.count(registration) == 1
    handler = _section(BOT_SOURCE, "async def handle_video_tail_callback", "async def handle_video_tail9_pending_text")
    assert "video_tail9.claim_callback" in handler
    assert "if not claimed:" in handler
    assert "return" in handler


def test_stale_worker_never_exposes_quality_selection_or_payable_invoice() -> None:
    render = _section(BOT_SOURCE, "async def video_tail9_render", "async def handle_video_tail_callback")
    assert "selectable=bool(capability.get(\"ok\"))" in render
    handler = _section(BOT_SOURCE, "async def handle_video_tail_callback", "async def handle_video_tail9_pending_text")
    assert 'if not capability.get("ok"):' in handler
    assert "video_tail9_public_blocker_text()" in handler
    assert "video_tail9_public_blocker_keyboard()" in handler


def test_fresh_canonical_heartbeat_admits_video_edit() -> None:
    result = video_editengine1.preflight(_state(), _runtime())
    assert result["ok"] is True
    assert result["reason"] == "ok"
    assert result["checks"]["worker_owner"] is True
    assert result["checks"]["engine_route"] is True
    assert result["checks"]["capability"] is True
    assert result["checks"]["heartbeat_ttl"] is True


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"heartbeat_age_seconds": video_editengine1.HEARTBEAT_TTL_SECONDS + 1}, "local_worker_heartbeat_stale"),
        ({"worker_owner": "local_video_worker"}, "local_worker_owner_mismatch"),
        ({"engine_route": "frame_video_worker"}, "local_worker_route_mismatch"),
        ({"capabilities": []}, "local_worker_capability_missing"),
        ({"connected": False}, "local_worker_heartbeat_stale"),
    ],
)
def test_worker_contract_reports_exact_blocker(overrides: dict, reason: str) -> None:
    result = video_editengine1.preflight(_state(), _runtime(**overrides))
    assert result["ok"] is False
    assert result["reason"] == reason


def test_worker_heartbeat_payload_registers_exact_adapter_contract() -> None:
    payload = local_worker.local_worker_heartbeat_payload(last_error="", queue_depth=2)
    assert payload["heartbeat_contract_version"] == 1
    assert payload["worker_owner"] == "local_video_edit"
    assert payload["engine_route"] == "local_worker_ffmpeg"
    assert payload["capabilities"] == ["video_edit"]
    assert payload["instance_id"]
    assert payload["process_id"] > 0
    assert payload["timestamp_utc"].endswith("Z")
    assert payload["queue_depth"] == 2


def test_worker_heartbeat_loop_publishes_immediately_and_periodically(monkeypatch) -> None:
    class StopEvent:
        def __init__(self) -> None:
            self.stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def wait(self, _seconds: int) -> bool:
            return self.stopped

    stop = StopEvent()
    calls: list[int] = []

    def publish() -> None:
        calls.append(len(calls) + 1)
        if len(calls) == 2:
            stop.stopped = True

    monkeypatch.setattr(local_worker, "send_heartbeat", publish)
    local_worker.run_heartbeat_loop(stop, interval_seconds=30)
    assert calls == [1, 2]


def test_worker_main_uses_background_heartbeat_during_render() -> None:
    section = _section(WORKER_SOURCE, "def main()", 'if __name__ == "__main__":')
    assert "threading.Thread(" in section
    assert "target=run_heartbeat_loop" in section
    assert "heartbeat_thread.start()" in section
    assert "heartbeat_stop.set()" in section
    assert "heartbeat_thread.join(timeout=2)" in section
    assert "last_heartbeat" not in section


def test_video_edit_keep_ratio_has_compatible_canonical_packages() -> None:
    report = video_uifreeze1.catalog_report(
        "video_edit",
        scene_count=1,
        ratio="keep",
        required_capability="video_to_video",
    )
    assert report["ok"] is True
    assert len(report["offers"]) >= 1
    assert report["uses_canonical_pricing"] is True
    assert report["framevideo_excluded"] is False
    assert all("video_to_video" in offer["capabilities"] for offer in report["offers"])
    assert report["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_video_edit_catalog_adapter_requests_video_to_video_capability() -> None:
    section = _section(BOT_SOURCE, "def video_tail9_catalog_report", "def video_tail9_quality_text")
    assert "video_editengine1.PRODUCT_TYPE" in section
    assert 'required_capability = "video_to_video"' in section
    assert "video_uifreeze1.catalog_report" in section


def test_video_edit_status_has_only_edit_stages() -> None:
    status = _section(BOT_SOURCE, "def video_editor_job_status_text", "VIDEO_PUBLIC_ROUTE_FORBIDDEN_WORDS")
    for label in (
        "Nhận video",
        "Kiểm tra cấu hình",
        "Chuẩn bị file",
        "Chỉnh sửa video",
        "Kiểm tra MP4",
        "Gửi kết quả",
    ):
        assert label in status
    assert "Tạo cảnh" not in status
    assert "Tạo prompt" not in status
    assert "Tạo ảnh" not in status


def test_worker_status_debug_contract_is_persisted_and_exposed() -> None:
    endpoint = _section(BOT_SOURCE, 'async def internal_worker_heartbeat', '@fastapi_app.get("/internal/worker/poll")')
    for key in (
        "worker_owner",
        "engine_route",
        "capabilities_json",
        "instance_id",
        "process_id",
        "queue_depth",
        "last_error",
        "heartbeat_contract_version",
    ):
        assert key in endpoint
    status = _section(BOT_SOURCE, "def video_edit_worker_status_payload", "PROVIDER_ORCHESTRATOR_CAPABILITIES")
    for key in (
        "heartbeat_timestamp",
        "heartbeat_age_seconds",
        "heartbeat_ttl_seconds",
        "worker_status",
        "worker_instance_id",
    ):
        assert key in status
