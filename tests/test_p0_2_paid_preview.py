from pathlib import Path

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _source_between(start_marker: str, end_marker: str) -> str:
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _assert_preview_buttons(markup):
    labels = _labels(markup)
    assert "✅ Xác nhận tạo bản đầy đủ" in labels
    assert "🔁 Đổi giọng hoặc nhạc" in labels
    assert "✏️ Sửa nội dung" in labels
    assert any("Quay lại" in label for label in labels)
    assert "🏠 Menu chính" in labels


def _assert_public_copy_safe(text: str):
    lowered = text.lower()
    for term in ["provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "smoke", "gate", "raw error"]:
        assert term not in lowered


def test_paid_voice_requires_preview_before_final_confirm():
    assert bot.paid_task_requires_preview("voice_clone", {"price_xu": 120})
    text = bot.paid_preview_friendly_guard_text("voice_clone", "vi")
    assert "Nghe thử voice riêng" in text
    assert "chưa xuất bản đầy đủ" in text
    _assert_public_copy_safe(text)
    entry_callbacks = _callbacks(bot.voice_clone_preview_entry_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "music_quick|showroom|voice_clone_confirmed:1" in entry_callbacks
    assert "music_quick|showroom|voice_profile_save:1" not in entry_callbacks
    _assert_preview_buttons(bot.voice_clone_preview_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert len(bot.VOICE_PROFILE_PREVIEW_TEXT.split()) <= 12

    block = _source_between('if action.startswith("voice_clone_confirm:")', 'if action == "voice_clone_guard":')
    assert "paid_preview_friendly_guard_text" in block
    assert "voice_clone_confirmed" in block
    assert block.index("paid_preview_friendly_guard_text") < block.index("create_minimax_voice_profile_preview")
    preview_function = _source_between("async def create_minimax_voice_profile_preview", "async def handle_music_quick_callback")
    assert "spend_fixed_credit_info" not in preview_function
    save_block = _source_between('if action.startswith("voice_profile_save:")', 'if action.startswith("voice_clone_confirm:")')
    assert "spend_fixed_credit_info" in save_block


def test_paid_music_requires_preview_before_final_confirm():
    assert bot.paid_task_requires_preview("ai_music", {"price_xu": 180})
    text = bot.suno_user_guard_text("vi")
    assert "nghe thử nhạc" in text
    assert "TOAN AAS chưa xuất bản đầy đủ" in text
    _assert_public_copy_safe(text)


def test_paid_dubbing_requires_preview_before_final_confirm():
    assert bot.paid_task_requires_preview("dubbing", {"price_xu": 250})
    text = bot.video_paid_preview_text({
        "pending_payload": {
            "job_type": "video",
            "base_cost": 600,
            "duration_seconds": 18,
            "dubbing_option": "dub_original",
        }
    }, "vi")
    assert "Lồng tiếng" in text
    assert "tối đa 6 giây" in text
    _assert_public_copy_safe(text)


def test_paid_subtitle_translation_preview_before_final_confirm():
    assert bot.paid_task_requires_preview("subtitle_translation", {"price_xu": 150})
    assert bot.paid_task_requires_preview("subtitle_plus_dubbing", {"price_xu": 350})
    text = bot.video_paid_preview_text({
        "pending_payload": {
            "job_type": "video",
            "base_cost": 600,
            "duration_seconds": 15,
            "subtitle_option": "subtitle_translated",
            "translation_enabled": True,
        }
    }, "vi")
    assert "Phụ đề:" in text
    assert "vài dòng đầu" in text
    _assert_public_copy_safe(text)


def test_paid_video_preview_max_6_seconds():
    assert not bot.video_paid_preview_required({"job_type": "video", "base_cost": 300})
    assert bot.video_paid_preview_required({"job_type": "video", "base_cost": 300, "preview_required": True})
    text = bot.video_paid_preview_text({"pending_payload": {"job_type": "video", "base_cost": 300, "duration_seconds": 120}}, "vi")
    assert "tối đa 6 giây" in text
    assert not bot.video_paid_preview_artifact({"pending_payload": {"paid_preview_video_file_id": "full-file", "paid_preview_seconds": 7}})
    assert bot.video_paid_preview_artifact({
        "pending_payload": {
            "paid_preview_video_file_id": "short-preview",
            "paid_preview_seconds": 6,
        }
    })["value"] == "short-preview"


def test_short_video_preview_2_to_3_seconds():
    assert 2 <= bot.paid_preview_seconds(1) <= 3
    assert 2 <= bot.paid_preview_seconds(6) <= 3


def test_long_video_preview_max_6_seconds():
    assert bot.paid_preview_seconds(18) == 6
    assert bot.paid_preview_seconds(120) == 6


def test_preview_optional_full_output_stays_active(monkeypatch):
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    callbacks = _callbacks(bot.video_addon_confirm_keyboard("tok", "basic", "vi"))
    assert "videoaddon|preview|tok" in callbacks
    assert callbacks.index("videoaddon|preview|tok") < callbacks.index("shopai|confirm|tok")
    entry_callbacks = _callbacks(bot.video_paid_preview_entry_keyboard("tok", "vi"))
    assert "videoaddon|preview|tok" in entry_callbacks
    assert "shopai|confirm|tok" not in entry_callbacks
    assert "shopai|confirm|tok" in _callbacks(bot.video_paid_preview_keyboard("tok", "vi"))
    assert "framevideo|confirm" not in _callbacks(bot.frame_video_confirm_keyboard({}))
    assert "framevideo|confirm" in _callbacks(bot.frame_video_confirm_keyboard({"paid_preview_seen": True}))


def test_preview_does_not_deduct_final_xu():
    handler = _source_between("async def handle_video_addon_callback", "async def cmd_video_price_test")
    preview_start = handler.index('if action in {"preview", "preview_retry", "preview_status"}:')
    preview_end = handler.index('if action == "back":', preview_start)
    preview_block = handler[preview_start:preview_end]
    assert "spend_fixed_credit_info" not in preview_block
    assert "deduct_dynamic_credit" not in preview_block
    assert preview_block.index("send_video_paid_preview_artifact") < preview_block.index('pending_payload["paid_preview_seen"] = True')
    assert "apply_video_paid_preview_job_result" in preview_block
    assert 'job_type="paid_video_preview"' in preview_block

    confirm_block = _source_between("async def handle_shopaikey_public_callback", "async def cmd_video_price_test")
    assert confirm_block.index("video_paid_preview_required(pending)") < confirm_block.index("spend_fixed_credit_info")
    frame_handler = _source_between("async def handle_frame_video_callback", "async def cmd_storyboard_video")
    frame_preview = frame_handler[frame_handler.index('if action == "preview":'):frame_handler.index('if action == "mode_frame":')]
    assert "spend_fixed_credit_info" not in frame_preview
    frame_confirm = frame_handler[frame_handler.index('if action == "confirm":'):]
    assert frame_confirm.index("paid_preview_seen") < frame_confirm.index("spend_fixed_credit_info")


def test_preview_public_copy_no_provider_names():
    texts = [
        bot.video_paid_preview_text({"pending_payload": {"job_type": "video", "base_cost": 600, "duration_seconds": 42, "music_option": "ai_music"}}, "vi"),
        bot.paid_preview_friendly_guard_text("voice_clone", "vi"),
        bot.paid_preview_friendly_guard_text("dubbing", "vi"),
        bot.suno_user_guard_text("vi"),
        bot.video_paid_preview_unavailable_text({"current_video_duration_seconds": 60}, "vi"),
        bot.frame_video_preview_text({"photos": [{"file_id": "1"}, {"file_id": "2"}], "duration": "slow"}, ready=False),
    ]
    for text in texts:
        _assert_public_copy_safe(text)
