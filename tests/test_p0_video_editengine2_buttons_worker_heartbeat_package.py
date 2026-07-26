from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
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
        "video_tail|review|source",
        "video_tail|logo|open",
        "video_tail|summary|open",
        "video_tail|review|back",
        "menu|main",
    }
    assert all(callback in section for callback in expected)
    assert "video_tail|quality|open" not in section
    assert "review|scenes" not in section
    assert "review|prompts" not in section
    assert "review|redo" not in section


def test_video_edit_review_describes_cut_without_claiming_brightness() -> None:
    host = {
        **_state(),
        "brightness_percent": 100,
        "manual_edit_plan": {
            "input_video": "source.mp4",
            "trim": {"start_ms": 5_000, "end_ms": 20_000},
            "brightness_percent": 100,
        },
        "edit_operations": [{"operation": "trim", "label": "Cắt đầu/cuối"}],
    }
    text = bot.video_tail9_video_edit_review_text(
        {"estimated_duration": 15, "video_product_type": "video_edit"},
        host,
    )
    assert "Cắt đầu/cuối" in text
    assert "Điều chỉnh độ sáng" not in text
    assert "Mức sáng" not in text


def test_custom_brightness_200_keeps_video_edit_session_and_opens_review(monkeypatch) -> None:
    uid = 90200
    state = {
        **_state(),
        "step": "await_brightness",
        "edit_mode": "manual_edit",
        "edit_session_id": "edit-brightness-200",
        "state_revision": 3,
        "revision": 3,
        "source_duration_ms": 4_000,
    }
    saved: dict = {}
    rendered: list[tuple[int, str, str]] = []

    class Message:
        text = "200"

        async def reply_text(self, *_args, **_kwargs):
            raise AssertionError("valid brightness must route directly to Video Edit Review")

    def update_pending(_uid: int, step: str = "", **fields) -> dict:
        saved.clear()
        saved.update(state)
        saved.update(fields)
        saved["step"] = step
        return dict(saved)

    async def render(target, user_id: int, _context, screen: str):
        rendered.append((user_id, screen, str(getattr(target, "text", ""))))
        return True

    monkeypatch.setattr(bot, "get_video_editor_pending", lambda _uid: dict(state))
    monkeypatch.setattr(bot, "update_video_editor_pending", update_pending)
    monkeypatch.setattr(bot, "clear_video_editor_competing_video_states", lambda *_args: {})
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_tail9_render", render)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        message=Message(),
    )
    assert asyncio.run(bot.handle_video_editor_pending_text(update, SimpleNamespace(user_data={}))) is True
    assert saved["product_type"] == "video_edit"
    assert saved["flow_owner"] == "video_edit"
    assert saved["edit_session_id"] == "edit-brightness-200"
    assert saved["brightness_percent"] == 200
    assert saved["manual_edit_plan"]["brightness_percent"] == 200
    assert saved["current_screen"] == "review"
    assert saved["return_to"] == "brightness"
    assert rendered == [(uid, "review", "200")]


def test_cut_input_keeps_cut_back_target_instead_of_default_brightness(monkeypatch) -> None:
    uid = 90201
    state = {
        **_state(),
        "step": "await_trim_edges",
        "edit_mode": "manual_edit",
        "edit_session_id": "edit-cut-1",
        "source_duration_ms": 30_000,
        "source_metadata": {
            "ok": True,
            "duration": 30.0,
            "duration_ms": 30_000,
            "has_audio": True,
        },
    }
    saved: dict = {}
    replies: list[str] = []

    class Message:
        text = "00:05-00:20"

        async def reply_text(self, text: str, **_kwargs):
            replies.append(text)
            return True

    def update_pending(_uid: int, step: str = "", **fields) -> dict:
        saved.clear()
        saved.update(state)
        saved.update(fields)
        saved["step"] = step
        return dict(saved)

    monkeypatch.setattr(bot, "get_video_editor_pending", lambda _uid: dict(state))
    monkeypatch.setattr(bot, "update_video_editor_pending", update_pending)
    monkeypatch.setattr(bot, "clear_video_editor_competing_video_states", lambda *_args: {})
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_local_manual_options_text", lambda *_args: "cut-saved")
    monkeypatch.setattr(bot, "video_local_manual_options_keyboard", lambda *_args: "manual-keyboard")

    update = SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=Message())
    assert asyncio.run(bot.handle_video_editor_pending_text(update, SimpleNamespace(user_data={}))) is True
    assert saved["manual_edit_plan"]["trim"] == {"start_ms": 5_000, "end_ms": 20_000}
    assert saved["return_to"] == "manual_cut"
    assert saved["edit_operations"][0]["operation"] == "trim"
    assert replies == ["cut-saved"]


def test_video_edit_review_back_uses_explicit_operation_owner() -> None:
    resolver = getattr(bot, "video_edit_review_return_action", None)
    assert callable(resolver)
    default_plan = {"brightness_percent": 100}
    assert resolver({"manual_edit_plan": default_plan, "return_to": "manual_cut"}) == "manual_cut"
    assert resolver({"manual_edit_plan": default_plan, "return_to": "brightness"}) == "brightness"
    assert resolver({"manual_edit_plan": default_plan, "return_to": "manual_join"}) == "manual_join"
    assert resolver({"manual_edit_plan": default_plan}) == "options"

    editor = _section(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    review = _section(editor, 'if action == "review":', 'if action == "start":')
    assert "video_edit_review_return_action(state)" in review
    tail = _section(BOT_SOURCE, "async def handle_video_tail_callback", "async def handle_video_tail9_pending_text")
    assert "video_edit_review_return_action(current)" in tail
    assert 'if "brightness_percent" in plan:' not in tail


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
    assert 'owner != "video_edit" or capability.get("runtime_ready")' in render
    handler = _section(BOT_SOURCE, "async def handle_video_tail_callback", "async def handle_video_tail9_pending_text")
    assert 'owner != "video_edit" or capability.get("runtime_ready")' in handler
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
    assert payload["capabilities"] == ["video_edit", "frame_video_render"]
    assert payload["instance_id"]
    assert payload["process_id"] > 0
    assert payload["timestamp_utc"].endswith("Z")
    assert payload["queue_depth"] == 2


def test_frame_video_requires_the_worker_render_capability() -> None:
    section = _section(
        BOT_SOURCE,
        "def local_worker_supports_capability",
        "def frame_video_maintenance_text",
    )
    assert 'local_worker_supports_capability("frame_video_render")' in section
    assert "heartbeat_contract_version" in section
    assert "worker_owner" in section
    assert "engine_route" in section
    preflight = _section(
        BOT_SOURCE,
        "def frame_video_commercial_preflight",
        "def frame_video_runtime_guard",
    )
    assert 'local_worker_supports_capability("frame_video_render")' in preflight


def test_worker_dispatch_supports_each_advertised_video_capability(monkeypatch) -> None:
    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        local_worker,
        "run_frame_video_render",
        lambda job: dispatched.append(("frame", str(job["id"]))),
    )
    monkeypatch.setattr(
        local_worker,
        "run_video_local_edit",
        lambda job: dispatched.append(("edit", str(job["id"]))),
    )

    local_worker.process_job({"id": "frame-1", "job_type": "frame_video_render"})
    local_worker.process_job({"id": "edit-1", "job_type": "video_local_edit"})

    assert dispatched == [("frame", "frame-1"), ("edit", "edit-1")]


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
    assert report["tier_ids"][0] == 200
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


def test_create_job_stamps_worker_contract_even_when_caller_omits_it(tmp_path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "video-edit.db"))
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, command TEXT, job_type TEXT, status TEXT, provider TEXT,
            input_file_id TEXT, created_at TEXT, xu_cost INTEGER, admin_only INTEGER,
            updated_at TEXT
        )"""
    )
    created = video_editengine1.create_job(
        conn,
        user_id=7,
        chat_id=8,
        edit_session_id="edit-contract-1",
        source_file_id="telegram-source",
        source_metadata={"ok": True, "duration_ms": 4_000, "has_audio": True},
        plan={"input_video": "source.mp4", "brightness_percent": 120},
        tail={"quality_tier_id": "200"},
        quality_tier_id="200",
        price_xu=200,
        worker_payload={"local1_contract": 1, "source_file_id": "telegram-source"},
    )
    payload = json.loads(
        conn.execute(
            "SELECT input_file_id FROM local_worker_jobs WHERE id=?",
            (created["local_worker_job_id"],),
        ).fetchone()[0]
    )
    assert payload["product_type"] == "video_edit"
    assert payload["engine_route"] == "local_worker_ffmpeg"
    assert payload["worker_owner"] == "local_video_edit"
    assert payload["worker_capability"] == "video_edit"
    conn.close()


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
