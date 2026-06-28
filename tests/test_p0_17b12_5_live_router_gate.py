import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class FakeMessage:
    def __init__(self):
        self.chat_id = 900100
        self.message_id = 42
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, data, user_id=900101):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append({"text": text, "show_alert": show_alert})
        return None


async def _press(monkeypatch, data, uid=900101):
    replies = []

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        item = {"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode}
        replies.append(item)
        return SimpleNamespace(**item)

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    query = FakeQuery(data, uid)
    await bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace())
    return query.message.sent[-1] if query.message.sent else (replies[-1] if replies else {})


def _media_update(uid):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=FakeMessage())


def _fake_media_info(_message):
    return {
        "file_id": "tg-video-file",
        "file_unique_id": "tg-video-unique",
        "file_name": "sample.mp4",
        "mime_type": "video/mp4",
        "file_size": 123456,
        "duration": 12,
        "media_kind": "video",
    }


def _patch_common(monkeypatch, *, admin=False):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "is_translation_admin", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: "video")
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "video_reference_media_info", _fake_media_info)
    monkeypatch.setattr(bot, "video_dubbing_subtitle_document_info", lambda _message: {})


def test_public_voice_video_locked_before_media_processing(monkeypatch):
    _patch_common(monkeypatch, admin=False)
    monkeypatch.setattr(bot, "PUBLIC_VOICE_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)

    calls = {"prepare": 0}

    async def fail_prepare(*_args, **_kwargs):
        calls["prepare"] += 1
        raise AssertionError("public voice video must not run ASR")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fail_prepare)
    uid = 900201
    bot.clear_video_dubbing_pending(uid)

    result = asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_DUB}", uid))
    assert "Lồng tiếng video đang được hoàn thiện" in result["text"]
    assert bot.get_video_dubbing_pending(uid)["step"] == "locked_public"

    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid), SimpleNamespace()))
    assert handled is True
    assert "Lồng tiếng video đang được hoàn thiện" in bot.get_video_dubbing_pending(uid)["step"] or calls["prepare"] == 0
    assert calls["prepare"] == 0


def test_public_subtitle_plus_dub_locked_before_media_processing(monkeypatch):
    _patch_common(monkeypatch, admin=False)
    monkeypatch.setattr(bot, "PUBLIC_SUBTITLE_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)

    calls = {"combo": 0}

    async def fail_combo(*_args, **_kwargs):
        calls["combo"] += 1
        raise AssertionError("public subtitle+dub must not run ASR")

    monkeypatch.setattr(bot, "subtitle_plus_dub_create_original_from_media", fail_combo)
    uid = 900202
    bot.clear_video_dubbing_pending(uid)

    result = asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}", uid))
    assert "Phụ đề + lồng tiếng đang được hoàn thiện" in result["text"]
    assert bot.get_video_dubbing_pending(uid)["step"] == "locked_public"

    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid), SimpleNamespace()))
    assert handled is True
    assert calls["combo"] == 0


def test_public_custom_voice_locked_before_provider(monkeypatch):
    _patch_common(monkeypatch, admin=False)
    monkeypatch.setattr(bot, "PUBLIC_VOICE_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "PUBLIC_CUSTOM_VOICE_ENABLED", False)
    monkeypatch.setattr(bot, "MINIMAX_VOICE_CLONE_PUBLIC_ENABLED", True)

    uid = 900203
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        target_language="English",
        source_file_id="tg-video-file",
    )

    result = asyncio.run(_press(monkeypatch, "videodub|voice_create", uid))
    assert "Voice riêng cho lồng tiếng đang tạm giới hạn" in result["text"]
    assert "provider" not in result["text"].lower()
    assert "api" not in result["text"].lower()


def test_admin_bypass_voice_video_and_subtitle_plus_dub(monkeypatch):
    _patch_common(monkeypatch, admin=True)
    monkeypatch.setattr(bot, "PUBLIC_VOICE_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "PUBLIC_SUBTITLE_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chao"
        subtitle_ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(
            user_id,
            state.get("step") or "creating_original_subtitle",
            subtitle_ref=subtitle_ref,
        )
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chao"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)

    uid_voice = 900204
    bot.clear_video_dubbing_pending(uid_voice)
    voice_screen = asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_DUB}", uid_voice))
    assert "ADMIN TEST MODE" not in voice_screen["text"]
    assert bot.get_video_dubbing_pending(uid_voice)["step"] == "source"

    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid_voice), SimpleNamespace()))
    assert handled is True
    assert bot.get_video_dubbing_pending(uid_voice)["step"] == "original_subtitle_confirm"
    asyncio.run(_press(monkeypatch, "videodub|confirm_original_subtitle", uid_voice))
    assert bot.get_video_dubbing_pending(uid_voice)["step"] == "language"

    uid_combo = 900205
    bot.clear_video_dubbing_pending(uid_combo)
    combo_screen = asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}", uid_combo))
    assert "ADMIN TEST MODE" not in combo_screen["text"]
    assert bot.get_video_dubbing_pending(uid_combo)["step"] == "waiting_media"

    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid_combo), SimpleNamespace()))
    assert handled
    assert bot.get_video_dubbing_pending(uid_combo)["step"] == "original_subtitle_confirm"
    asyncio.run(_press(monkeypatch, "videodub|confirm_original_subtitle", uid_combo))
    assert bot.get_video_dubbing_pending(uid_combo)["step"] == "original_subtitle_ready"


def test_admin_bypass_custom_voice(monkeypatch):
    _patch_common(monkeypatch, admin=True)
    monkeypatch.setattr(bot, "PUBLIC_CUSTOM_VOICE_ENABLED", False)

    uid = 900206
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        entry_surface="admin_test_mode",
        target_language="English",
        source_file_id="tg-video-file",
    )
    result = asyncio.run(_press(monkeypatch, "videodub|voice_create", uid))
    assert "ADMIN TEST MODE" not in result["text"]
    assert "tạm giới hạn" not in result["text"].lower()


def test_public_translate_upload_language_waits_confirm(monkeypatch):
    _patch_common(monkeypatch, admin=False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    calls = {"prepare": 0, "pipeline": 0}

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        calls["prepare"] += 1
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chao"
        subtitle_ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(
            user_id,
            state.get("step") or "creating_original_subtitle",
            subtitle_ref=subtitle_ref,
        )
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chao"}],
            "detected_language": "vi",
        }

    async def fake_execute_engine(_feature, params, _context):
        calls["pipeline"] += 1
        runner_result = await params["runner"]()
        return {"ok": True, "runner_result": runner_result}

    async def fake_pipeline(*_args, **_kwargs):
        return {"ok": True, "has_video": True, "has_subtitle": True, "state": {}}

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    monkeypatch.setattr(bot, "execute_engine", fake_execute_engine)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_pipeline)
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))

    uid = 900207
    bot.clear_video_dubbing_pending(uid)
    asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_TRANSLATE}", uid))
    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid), SimpleNamespace()))
    assert handled is True
    assert calls["prepare"] == 0
    assert bot.get_video_dubbing_pending(uid)["step"] == "original_subtitle_confirm"

    asyncio.run(_press(monkeypatch, "videodub|confirm_original_subtitle", uid))
    assert calls["prepare"] == 1
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"

    language = asyncio.run(_press(monkeypatch, "videodub|language|English", uid))
    assert "Dịch phụ đề video" in language["text"]
    assert "✅ Xuất video phụ đề dịch" in _labels(language["reply_markup"])
    assert calls["prepare"] == 1
    assert bot.get_video_dubbing_pending(uid)["step"] == "confirm"

    confirm = asyncio.run(_press(monkeypatch, "videodub|final", uid))
    assert calls["pipeline"] == 1
    assert "đã tạo video phụ đề dịch" in confirm["text"].lower()


def test_public_auto_subtitle_upload_waits_confirm(monkeypatch):
    _patch_common(monkeypatch, admin=False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)

    calls = {"prepare": 0}

    async def fail_prepare(*_args, **_kwargs):
        calls["prepare"] += 1
        raise AssertionError("auto subtitle upload must not run ASR before confirm")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fail_prepare)

    uid = 900208
    bot.clear_video_dubbing_pending(uid)
    asyncio.run(_press(monkeypatch, f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_CREATE}", uid))
    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_media_update(uid), SimpleNamespace()))
    assert handled is True
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "confirm"
    assert calls["prepare"] == 0


def test_public_translate_menu_hides_manual_editor_and_dub_buttons():
    public_translate = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "entry_surface": "public_type",
    }
    source_labels = _labels(bot.video_dubbing_source_keyboard("vi", public_translate))
    assert "📄 Gửi SRT/VTT/TXT" not in source_labels

    result_labels = _labels(bot.video_dubbing_receipt_keyboard("vi", "translation", {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "final_video_available": "1",
        "final_subtitle_available": "1",
    }))
    assert not any("Lồng tiếng" in label for label in result_labels)
    assert not any("Chỉnh" in label or "Xem 10" in label for label in result_labels)

    auto_labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    for hidden in ["👁 Xem thử", "📝 Chỉnh phụ đề", "Xem 10 dòng đầu", "Tìm và thay thế"]:
        assert hidden not in auto_labels


def test_translation_voice_gate_status_admin_only_registered():
    status = bot.translation_voice_gate_status_text("vi")
    assert "PUBLIC_CUSTOM_VOICE_ENABLED" in status
    assert "PUBLIC_VOICE_VIDEO_ENABLED" in status
    assert "PUBLIC_SUBTITLE_DUB_ENABLED" in status
    assert "Admin bypass active" in status

    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    assert 'CommandHandler("translation_voice_gate_status", cmd_translation_voice_gate_status)' in source
