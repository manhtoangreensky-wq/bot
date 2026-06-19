from pathlib import Path

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _source_between(start_marker: str, end_marker: str) -> str:
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_translation_gateway_is_exact_two_column_business_menu():
    rows = _rows(bot.translation_menu_keyboard("vi"))
    assert rows[0] == ["🌐 Dịch ngôn ngữ", "🎬 Dịch video"]
    assert len(rows[1]) == 2


def test_language_menu_is_compact_and_keeps_old_language_translation():
    rows = _rows(bot.translation_language_hub_keyboard("vi"))
    assert rows[:3] == [
        ["📝 Văn bản", "📄 Tài liệu"],
        ["🖼 Chữ trong ảnh", "🎧 Audio"],
        ["⚙️ Ngôn ngữ", "⬅️ Trung tâm"],
    ]
    assert "menu|translation_text" in _callbacks(bot.translation_language_hub_keyboard("vi"))
    assert "menu|translation_document" in _callbacks(bot.translation_language_hub_keyboard("vi"))


def test_video_factory_has_no_forced_combo_on_first_screen():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels[:6] == [
        "📝 Tạo phụ đề",
        "🌐 Dịch phụ đề",
        "🗣 Lồng tiếng",
        "🔗 Tải từ link",
        "📂 Media của tôi",
        "✏️ Chỉnh phụ đề",
    ]
    assert not any("Dịch + lồng tiếng" in label for label in labels)


def test_subtitle_output_is_export_first_and_dubbing_optional():
    markup = bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE})
    rows = _rows(markup)
    assert rows[0] == ["👁 Xem thử bản dịch", "🗣 Lồng tiếng"]
    assert rows[1] == ["📄 Xuất SRT", "🎞 Gắn vào video"]
    assert rows[2] == ["📦 Xuất cả hai", "⬅️ Quay lại"]
    assert not any("giọng" in label.lower() for label in _labels(markup))


def test_subtitle_full_export_does_not_require_preview():
    handler = _source_between("async def handle_video_dubbing_callback", "def marketing_pending_key")
    assert "Hãy đi qua bước bản thử ngắn trước" not in handler
    assert 'InlineKeyboardButton(full_label if is_vi else "✅ Full output", callback_data="videodub|final")' in Path(bot.__file__).read_text(encoding="utf-8")


def test_continue_dubbing_records_exact_return_screen():
    handler = _source_between("async def handle_video_dubbing_callback", "def marketing_pending_key")
    assert 'return_screen="output"' in handler
    assert 'dubbing_from_output="1"' in handler
    assert 'next_step = "language_strategy" if next_mode == VIDEO_SUBTITLE_MODE_DUB' in handler
    assert 'if str(state.get("return_screen") or "") == "output"' in handler


def test_language_strategy_back_returns_to_subtitle_output():
    state = {"return_screen": "output", "dubbing_from_output": "1"}
    callbacks = _callbacks(bot.video_dubbing_language_strategy_keyboard("vi", state))
    assert "videodub|back_voice" in callbacks


def test_video_business_backstack_is_explicit_not_stack_first():
    handler = _source_between("async def handle_video_finalization_callback", "async def handle_video_finalization_pending_text")
    confirm_index = handler.index('if current_step == "confirm":')
    tier_index = handler.index('if current_step == "tier":')
    menu_index = handler.index('if current_step == "menu":')
    stack_index = handler.index('target_screen = pop_video_screen')
    assert confirm_index < tier_index < menu_index < stack_index


def test_200_preview_locked_but_full_export_remains_available():
    state = {"video_tier": "low", "pending_payload": {"video_tier": "low", "duration_seconds": 18, "scene_count": 3}}
    callbacks = _callbacks(bot.video_addon_confirm_keyboard("token", "low", "vi", state))
    assert "videoaddon|preview_locked|token" in callbacks
    assert "shopai|confirm|token" in callbacks
    assert bot.validate_video_tier_selection({
        "video_tier": "low",
        "current_video_music_option": "none",
        "current_video_voice_choice": "none",
        "current_video_subtitle_option": "none",
        "current_video_dubbing_option": "none",
    }, "low")["ok"] is True


def test_video_outputs_guard_when_worker_route_is_not_real(monkeypatch):
    monkeypatch.setattr(
        bot,
        "video_pipeline_status_payload",
        lambda: {"subtitle_burn_in": "configured/waiting_worker", "ffmpeg_mux": "configured/waiting_worker"},
    )
    source = _source_between("async def execute_video_dubbing_pipeline", "async def handle_video_dubbing_pending_upload")
    assert "worker xuất file thật" in source
    assert "TOAN AAS chưa xử lý và chưa trừ Xu" in source


def test_admin_provider_status_distinguishes_config_from_live_smoke(monkeypatch):
    monkeypatch.setattr(
        bot,
        "video_pipeline_status_payload",
        lambda: {
            "asr_provider": "deepgram",
            "asr_test": "NOT_TESTED",
            "translation_provider": "route",
            "translation_test": "NOT_TESTED",
            "tts_provider": "minimax",
            "tts_test": "NOT_TESTED",
            "ffmpeg_mux": "disabled",
            "subtitle_burn_in": "disabled",
            "local_worker_connected": False,
        },
    )
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *args, **kwargs: {"ok": True, "missing": [], "reason": "ready"})
    monkeypatch.setattr(bot, "video_translation_admin_blockers", lambda *args, **kwargs: [])
    text = bot.translation_provider_status_text()
    assert "CONFIGURED_NOT_SMOKED" in text
    assert "LIVE_SMOKE_PASS" in text


def test_video_factory_status_command_registered():
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    assert 'CommandHandler("video_factory_status", cmd_subtitle_dub_status)' in source
