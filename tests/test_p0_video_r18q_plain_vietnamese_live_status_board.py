from pathlib import Path

from services import product_progress_status, video_project_queue


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PUBLIC_TERMS = (
    "shopaikey",
    "key4u",
    "provider",
    "mp4",
    "result_url",
    "artifact",
    "concat",
    "scene coverage",
    "worker",
    "polling",
    "fallback",
    "terminal",
    "canonical",
)


def _job120_payload(now_epoch: int = 1_800_000_000, elapsed: int = 214) -> dict:
    started = now_epoch - elapsed
    return {
        "_panel_now_epoch": now_epoch,
        "provider_task_alive": True,
        "continue_polling": True,
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "IN_PROGRESS",
        "shopaikey_raw_status": "IN_PROGRESS",
        "shopaikey_data_progress_raw": "30",
        "provider_progress_raw": "30",
        "provider_progress_source": "shopaikey.data.progress",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "provider_progress_last_changed_elapsed_seconds": elapsed,
        "status_panel_message_id": 777,
        "auto_refresh_interval_seconds": 10,
        "scene_count": 2,
        "scene_coverage_count": 0,
        "concat_attempted": False,
        "charged_xu": 0,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "provider_task_id": "shop-task-120-1",
                "status": "provider_running",
                "provider_status_payload_source": "shopaikey.data.status",
                "shopaikey_data_status": "IN_PROGRESS",
                "provider_progress_raw": "30",
                "started_at_epoch": started,
            },
            {
                "scene_index": 2,
                "provider": "key4u_video",
                "provider_task_id": "key-task-120-2",
                "status": "provider_running",
                "provider_status_payload_source": "shopaikey.data.status",
                "shopaikey_data_status": "IN_PROGRESS",
                "provider_progress_raw": "30",
                "started_at_epoch": started,
            },
        ],
    }


def _board(payload: dict) -> tuple[dict, str]:
    telemetry = video_project_queue.reconcile_provider_progress_telemetry(
        {"id": 120, "status": "processing", "progress_percent": 39},
        payload,
        refresh_source="r18q_fixture",
    )
    merged = {**payload, **telemetry}
    board = product_progress_status.video_per_scene_progress_board(merged)
    text = product_progress_status.video_per_scene_progress_board_text(merged)
    return board, text


def test_job120_public_board_plain_vietnamese_no_technical_terms():
    board, text = _board(_job120_payload())

    lowered = text.lower()
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term not in lowered
    assert "Cảnh 1/2: Đang tạo" in text
    assert "Cảnh 2/2: Đang tạo" in text
    assert "đã chờ 3 phút 34 giây" in text
    assert "Hoàn tất: 0/2 cảnh" in text
    assert "Ghép video: Chưa bắt đầu" in text
    assert "Gửi kết quả: Chưa bắt đầu" in text
    assert "Hệ thống sẽ tự kiểm tra lại sau 10 giây" in text
    assert board["public_progress_mode"] == "scene_and_elapsed"
    assert board["public_progress_percent_visible"] is False


def test_elapsed_recomputed_between_two_panel_renders():
    first, _ = _board(_job120_payload(now_epoch=1_800_000_000, elapsed=214))
    second, text = _board(_job120_payload(now_epoch=1_800_000_010, elapsed=224))

    assert first["elapsed_seconds_by_scene"]["1"] == 214
    assert second["elapsed_seconds_by_scene"]["1"] == 224
    assert "đã chờ 3 phút 44 giây" in text
    assert second["elapsed_live_tick_enabled"] is True
    assert second["elapsed_source"] == "persisted_started_at"


def test_one_scene_done_and_waiting_for_remaining_scene():
    payload = _job120_payload()
    payload["scene_coverage_count"] = 1
    payload["scene_tasks"][0].update({"status": "clip_downloaded", "clip_valid": True, "result_url": "https://example.test/scene1"})

    _board_data, text = _board(payload)

    assert "Cảnh 1/2: Đã xong" in text
    assert "Cảnh 2/2: Đang tạo" in text
    assert "Hoàn tất: 1/2 cảnh" in text
    assert "Ghép video: Chờ cảnh còn lại" in text


def test_full_scene_coverage_moves_to_video_joining_copy():
    payload = _job120_payload()
    payload["scene_coverage_count"] = 2
    for item in payload["scene_tasks"]:
        item.update({"status": "clip_downloaded", "clip_valid": True, "result_url": f"https://example.test/scene{item['scene_index']}"})

    _board_data, text = _board(payload)

    assert "Hoàn tất: 2/2 cảnh" in text
    assert "Ghép video: Đang thực hiện" in text
    assert "Gửi kết quả: Chưa bắt đầu" in text


def test_final_delivered_public_copy_is_100_percent_semantics_without_technical_terms():
    payload = _job120_payload()
    payload.update({"scene_coverage_count": 2, "final_delivered": True, "delivery_succeeded": True})
    for item in payload["scene_tasks"]:
        item.update({"status": "clip_downloaded", "clip_valid": True, "result_url": f"https://example.test/scene{item['scene_index']}"})

    board, text = _board(payload)

    assert "Video đã hoàn tất" in text
    assert "Đã gửi kết quả" in text
    assert board["public_progress_percent_visible"] is True
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term not in text.lower()


def test_progress_source_fixed_30_uses_scene_and_elapsed_not_public_percent():
    payload = _job120_payload()
    telemetry = video_project_queue.reconcile_provider_progress_telemetry(
        {"id": 120, "status": "processing", "progress_percent": 39},
        payload,
        refresh_source="r18q_fixture",
    )

    assert telemetry["public_progress_mode"] == "scene_and_elapsed"
    assert telemetry["public_progress_percent_visible"] is False
    assert telemetry["final_progress_after_reconcile"] > 39
    assert telemetry["elapsed_live_tick_enabled"] is True


def test_auto_refresh_10s_recovery_rebind_and_same_message_source_contract():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "VIDEO_PUBLIC_STATUS_REFRESH_SECONDS" in source
    assert "auto_refresh_interval_seconds" in source
    assert "status_panel_message_id" in source
    assert "auto_refresh_recovered_from_db" in source
    assert "rebind_after_edit_failed" in source
    assert "auto_refresh_rebind_attempted" in source
    assert "auto_refresh_lease_until_epoch" in source
    assert "edit_message_text" in source
    assert "send_message" in source


def test_admin_debug_provider_fields_preserved_but_public_helper_hides_them():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "ShopAIKey exact status endpoint" in source
    assert "provider_task_id" in source
    _board_data, text = _board(_job120_payload())
    assert "ShopAIKey" not in text
    assert "Key4U" not in text


def test_pending_public_copy_and_final_guard_avoid_mp4_wording():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    start = source.index("def product_video_provider_pending_public_copy")
    end = source.index("\n\n", source.index("return \"Hệ thống đang dựng video", start))
    segment = source[start:end]

    assert "MP4" not in segment
    assert "video cuối" in segment
    assert "TOAN AAS không báo hoàn tất khi chưa có video cuối (MP4)." not in source
