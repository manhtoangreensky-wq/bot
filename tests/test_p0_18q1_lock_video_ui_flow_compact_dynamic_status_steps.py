import subprocess

import bot


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def _session(addons=None):
    return {
        "product_id": "video_trend",
        "video_flow": "video_trend",
        "current_step": "b14_queue_status",
        "draft": {
            "b14_invoice": {
                "scene_count": 3,
                "duration_seconds": 18,
                "quality_xu": 300,
                "package_label": "⭐ 300 Xu — Cơ bản",
            },
            "b14_addon_plan": dict(addons or {}),
            "b14_scene_count": 3,
        },
    }


def _status_text(status="queued", progress=5, *, final=False, addons=None):
    job = {"id": 987101, "status": status, "progress_percent": progress}
    project = {}
    if final:
        job["final_video_file_id"] = "telegram-file-id"
        project["final_video_file_id"] = "telegram-file-id"
    return bot.video_b14_queue_status_text(
        _session(addons),
        {"job": job, "project": project},
        user_id=0,
        lang="vi",
    )


def test_video_status_panel_has_dynamic_steps():
    text = _status_text()
    assert "<b>Tiến trình:</b>" in text
    for label in bot.VIDEO_B14_STATUS_STEP_LABELS:
        assert label in text


def test_video_status_panel_compact_no_long_debug_lines():
    text = _status_text()
    assert "🎬 <b>Trạng thái tạo video</b>" in text
    assert "Mã xử lý: <b>#987101</b>" in text
    assert "• Hậu kỳ:" in text
    forbidden = (
        "Giai đoạn",
        "Cập nhật lần cuối",
        "Kết quả",
        "Tùy chọn thêm",
        "Thời gian chờ",
        "Voice:",
        "Nhạc:",
        "Phụ đề:",
        "Lồng tiếng:",
        "tốc độ",
        "provider",
        "artifact",
        "payload",
        "debug",
        "worker",
        "chưa có file thành phẩm",
    )
    assert not [term for term in forbidden if term in text]


def test_video_status_addons_grouped_compactly():
    text = _status_text(
        addons={
            "music_enabled": True,
            "subtitle_enabled": True,
            "logo_enabled": True,
            "logo_source": "text",
            "logo_text": "TOAN AAS",
        }
    )
    assert "• Hậu kỳ: <b>Nhạc nền, phụ đề, logo</b>" in text
    assert "Logo:" not in text
    assert "Nhạc:" not in text


def test_video_status_5_percent_steps_received_and_preparing():
    text = _status_text("queued", 5)
    assert "Tiến độ: <b>5%</b>" in text
    assert "✅ Nhận yêu cầu" in text
    assert "⏳ Chuẩn bị dựng" in text
    assert "⬜ Dựng video" in text


def test_video_status_50_percent_steps_rendering():
    text = _status_text("processing", 50)
    assert "Tiến độ: <b>50%</b>" in text
    assert "✅ Nhận yêu cầu" in text
    assert "✅ Chuẩn bị dựng" in text
    assert "⏳ Dựng video" in text
    assert "⬜ Kiểm tra file" in text


def test_video_status_90_percent_steps_checking_file():
    text = _status_text("processing", 90, final=True)
    assert "Tiến độ: <b>90%</b>" in text
    assert "✅ Dựng video" in text
    assert "⏳ Kiểm tra file" in text
    assert "⬜ Gửi kết quả" in text


def test_video_status_100_percent_all_steps_done():
    text = _status_text("completed", 100, final=True)
    assert "Tiến độ: <b>100%</b>" in text
    assert "✅ Nhận yêu cầu" in text
    assert "✅ Chuẩn bị dựng" in text
    assert "✅ Dựng video" in text
    assert "✅ Kiểm tra file" in text
    assert "✅ Gửi kết quả" in text
    assert "✅ Video đã sẵn sàng." in text


def test_video_render_step_not_done_without_final_artifact():
    text = _status_text("processing", 90, final=False)
    assert "✅ Dựng video" not in text
    assert "⏳ Dựng video" in text


def test_video_no_95_percent_without_artifact():
    text = _status_text("processing", 99, final=False)
    assert "Tiến độ: <b>95%</b>" not in text
    assert "Tiến độ: <b>85%</b>" in text
    assert "⏳ Dựng video" in text
    assert "⏳ Kiểm tra file" not in text


def test_video_buttons_unchanged_after_lock():
    rows = _rows(bot.video_b14_queue_status_keyboard("vi"))
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard("vi"))
    assert rows == [["🔄 Cập nhật trạng thái", "🧾 Xem hóa đơn"], ["⬅️ Menu video", "🏠 Menu chính"]]
    assert callbacks == [["vproduct|b14_job_status", "vproduct|b14_invoice_screen"], ["menu|main_video", "menu|main"]]


def test_video_suggestion_1_to_5_layout_unchanged():
    options = bot.video_microflow_build_options("prompt", "demo", "video_ai_real", 5)
    rows = _rows(bot.video_microflow_options_keyboard("video_ai_real", "vi", options, "prompt"))
    assert rows[0] == ["1", "2", "3", "4", "5"]
    assert rows[1] == ["🔄 Gợi ý lại", "✍️ Nhập chủ đề riêng"]


def test_video_back_routing_unchanged():
    assert bot.video_back_matrix_target({}) == bot.VIDEO_BACK_MENU_TARGET
    assert bot.video_back_matrix_target(
        {
            "product_id": "video_trend",
            "video_flow": "video_trend",
            "current_step": "b14_invoice",
            "draft": {"b14_invoice_return_step": "b14_queue_status"},
        }
    ) == "b14_queue_status"


def test_video_ui_audit_dynamic_steps_ok():
    payload = bot.video_ui_audit_payload()
    checks = {item["name"]: item for item in payload["checks"]}
    assert payload["ok"] is True
    assert checks["status_panel_compact"]["ok"] is True
    assert checks["dynamic_steps_enabled"]["ok"] is True
    assert checks["long_addon_details_public"]["ok"] is True
    assert checks["refresh_button_label"]["ok"] is True
    assert checks["flow_locked"]["ok"] is True
    assert checks["engine_touched"]["ok"] is True
    assert checks["engine_touched"]["value"] is False


def _local_worker_change_is_img2vid_only() -> bool:
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", "origin/main", "--", "local_worker.py"],
        text=True,
        encoding="utf-8",
    ).lower()
    changed_lines = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    forbidden = ("music", "suno", "subdub", "subtitle", "dub", "payos", "wallet", "provider", "video_provider")
    return (
        "run_frame_video_render" in diff
        and "len(photos) < 2" in diff
        and "len(photos) < 1" in diff
        and not any(marker in changed_lines for marker in forbidden)
    )


def test_no_video_engine_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True, encoding="utf-8").splitlines()
    p0_18r_engine_files = {
        "remote_worker.py",
        "services/video_final_output.py",
        "services/video_real_render_connector.py",
        "services/video_project_queue.py",
        "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py",
    }
    forbidden = {
        "services/multiscene_video_pipeline.py",
        "local_worker.py",
        "providers/key4u_provider.py",
    }
    if "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py" in changed:
        changed = [item for item in changed if item not in p0_18r_engine_files]
    if "local_worker.py" in changed and _local_worker_change_is_img2vid_only():
        changed = [item for item in changed if item != "local_worker.py"]
    assert not forbidden.intersection(changed)


def test_no_payos_music_subdub_voice_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True, encoding="utf-8").splitlines()
    forbidden_prefixes = (
        "services/minimax_voice_adapter.py",
        "services/subtitle_dub_pipeline.py",
        "services/payos",
        "music/",
        "providers/suno",
        "wallet",
    )
    assert not [path for path in changed if path.startswith(forbidden_prefixes)]
