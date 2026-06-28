import asyncio
import inspect
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, *, chat_id=919700, video=None):
        self.chat_id = chat_id
        self.message_id = 7
        self.video = video
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, **kwargs):
        item = {"audio": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_document(self, **kwargs):
        item = {"document": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_video(self, **kwargs):
        item = {"video": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


class CaptureQuery:
    def __init__(self, user_id, data):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = CaptureMessage(chat_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


def _query_update(query):
    return SimpleNamespace(callback_query=query)


def _message_update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _video_info():
    return {
        "file_id": "tg-video-19b7",
        "file_unique_id": "unique-video-19b7",
        "file_name": "clip.mp4",
        "mime_type": "video/mp4",
        "file_type": "video",
        "duration": 12,
        "file_size": 2048,
    }


def _patch_video_upload(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_subtitle_document_info", lambda _message: None)
    monkeypatch.setattr(bot, "video_reference_media_info", lambda _message: _video_info())
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(
        bot,
        "video_dubbing_source_fields_from_upload",
        lambda _info, subtitle_file=False: {
            "source_file_id": "tg-video-19b7",
            "video_file_id": "tg-video-19b7",
            "source_file_name": "clip.mp4",
            "source_mime_type": "video/mp4",
            "media_kind": "video",
            "source_duration": "12",
            "video_duration": "12",
        },
    )


def _combo_state(uid, *, flow_type="", combo_subpath=""):
    bot.clear_video_dubbing_pending(uid)
    return bot.set_video_dubbing_pending(
        uid,
        "source",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        origin="translation",
        flow_type=flow_type,
        combo_subpath=combo_subpath,
    )


def test_subtitle_plus_dub_entry_shows_has_subtitle_and_no_subtitle():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    callbacks = _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    assert "🎞 Video đã có phụ đề" in labels
    assert "🎧 Video chưa có phụ đề" in labels
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE}" in callbacks
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in callbacks


def test_no_subtitle_path_shows_two_choices(monkeypatch):
    uid = 919701
    _combo_state(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = CaptureQuery(uid, f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    labels = _labels(query.outputs[-1]["reply_markup"])
    callbacks = _callbacks(query.outputs[-1]["reply_markup"])
    assert "🎬 Tạo phụ đề rồi lồng tiếng" in labels
    assert "🎙 Lồng tiếng trực tiếp" in labels
    assert f"videodub|no_subtitle_flow|{bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB}" in callbacks
    assert f"videodub|no_subtitle_flow|{bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB}" in callbacks
    assert bot.get_video_dubbing_pending(uid)["step"] == "no_subtitle_menu"


def test_no_subtitle_create_subtitle_then_dub_flow_order(monkeypatch):
    uid = 919702
    _combo_state(uid, flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = CaptureQuery(uid, f"videodub|no_subtitle_flow|{bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB}")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "await_video"
    assert state["combo_subpath"] == bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB
    assert "tạo phụ đề gốc trước" in query.outputs[-1]["text"]
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(query.outputs[-1]["reply_markup"])

    _patch_video_upload(monkeypatch)
    message = CaptureMessage(video=SimpleNamespace(file_id="tg-video-19b7"))
    asyncio.run(bot.handle_video_dubbing_pending_upload(_message_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "original_subtitle_confirm"
    assert state["output_type"] == "video_subtitle"
    assert "Tạo phụ đề gốc" in message.outputs[-1]["text"]
    assert "videodub|confirm_original_subtitle" in _callbacks(message.outputs[-1]["reply_markup"])


def test_no_subtitle_direct_dub_flow_order(monkeypatch):
    uid = 919703
    _combo_state(uid, flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = CaptureQuery(uid, f"videodub|no_subtitle_flow|{bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB}")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "await_video"
    assert state["combo_subpath"] == bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB
    assert state["output_type"] == "video"
    assert "Lồng tiếng trực tiếp" not in query.outputs[-1]["text"]
    assert "lồng tiếng" in query.outputs[-1]["text"].lower()

    _patch_video_upload(monkeypatch)
    message = CaptureMessage(video=SimpleNamespace(file_id="tg-video-19b7"))
    asyncio.run(bot.handle_video_dubbing_pending_upload(_message_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["output_type"] == "video"
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(message.outputs[-1]["reply_markup"])


def test_no_subtitle_direct_dub_goes_language_voice_confirm(monkeypatch):
    uid = 919704
    _combo_state(
        uid,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
    )
    bot.set_video_dubbing_pending(
        uid,
        "language",
        source_file_id="tg-video-19b7",
        video_file_id="tg-video-19b7",
        source_file_name="clip.mp4",
        source_mime_type="video/mp4",
        media_kind="video",
        output_type="video",
        output_format="video",
        translate_requested="1",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = CaptureQuery(uid, "videodub|language|English")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "voice"
    assert state["target_language"] == "English"

    query = CaptureQuery(uid, "videodub|voice|default_female")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "confirm"
    assert state["output_type"] == "video"
    assert "Lồng tiếng trực tiếp" in query.outputs[-1]["text"]


def test_direct_dub_partial_audio_does_not_send_subtitle_document():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            subtitle_items=[{"output_type": "srt", "bytes": b"1\n00:00:00,000 --> 00:00:01,000\nHi", "filename": "sub.srt"}],
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nHi",
            audio_bytes=b"audio",
            video_bytes=b"",
            include_subtitle_outputs=False,
            lang="vi",
        )
    )
    assert sent == {"documents": 0, "audio": 1, "video": 0}
    assert not any(item.get("document") for item in message.outputs)


def test_product_failure_copy_clean_for_admin_guard(monkeypatch):
    async def forbidden_process(*_args, **_kwargs):
        raise AssertionError("engine must not run when guard blocks")

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(
        bot,
        "video_dubbing_engine_access_decision",
        lambda *_args, **_kwargs: {
            "allowed": False,
            "status": "blocked_admin",
            "message": "Admin test adapter_missing provider ASR TTS mux FFmpeg <code>asr_adapter_missing</code>",
        },
    )
    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", forbidden_process)
    query = SimpleNamespace(from_user=SimpleNamespace(id=919705), message=CaptureMessage())
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            query,
            SimpleNamespace(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "process_type": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            },
            "vi",
        )
    )
    lowered = result["text"].lower()
    for forbidden in ("admin", "adapter_missing", "provider", "asr", "tts", "mux", "ffmpeg", "<code>", "api", "debug"):
        assert forbidden not in lowered


def test_pr38_subtitle_dub_engine_wiring_restored_or_equivalent():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.process_subtitle_dub_job" in source
    assert "video_dubbing_prepare_subtitles" in source
    assert "synthesize_dub_segment_chunks" in source
    assert "video_dubbing_render_video" in source


def test_no_provider_before_confirm_on_no_subtitle_upload(monkeypatch):
    uid = 919706
    _combo_state(
        uid,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
    )
    bot.set_video_dubbing_pending(uid, "await_video")
    _patch_video_upload(monkeypatch)

    async def forbidden_prepare(*_args, **_kwargs):
        raise AssertionError("subtitle creation must wait for confirm")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", forbidden_prepare)
    message = CaptureMessage(video=SimpleNamespace(file_id="tg-video-19b7"))
    asyncio.run(bot.handle_video_dubbing_pending_upload(_message_update(uid, message), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "original_subtitle_confirm"


def test_back_routing_for_subtitle_plus_dub_no_subtitle_branch():
    create_upload = bot.video_dubbing_upload_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
            "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
        },
    )
    direct_language = bot.video_dubbing_language_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
            "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
        },
    )
    has_upload = bot.video_dubbing_upload_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            "flow_type": bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
        },
    )
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(create_upload)
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(direct_language)
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in _callbacks(has_upload)


def test_no_cross_jump_to_voice_music_or_video_worker():
    callbacks = set(_callbacks(bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")))
    callbacks.update(
        _callbacks(
            bot.video_dubbing_upload_keyboard(
                "vi",
                {
                    "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                    "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                    "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                    "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
                },
            )
        )
    )
    assert not any(value.startswith(("voice|", "music|", "vfinal|", "videoaddon|")) for value in callbacks)


def test_has_subtitle_path_kept():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "flow_type": bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
    }
    upload = bot.video_dubbing_upload_text(state, "vi")
    keyboard = bot.video_dubbing_upload_keyboard("vi", state)
    assert "video đã có phụ đề" in upload
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in _callbacks(keyboard)
    assert "videodub|path|no_subtitle" not in _callbacks(keyboard)


def test_no_subtitle_direct_dub_does_not_require_visible_subtitle():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
        "target_language": "English",
        "voice_style": "Nữ mặc định",
        "billing_chars": 100,
        "output_type": "video",
    }
    assert "phụ đề hiển thị" not in bot.video_dubbing_confirm_text(state, "vi").lower()
    assert "Xuất video MP4 lồng tiếng" in bot.video_dubbing_confirm_text(state, "vi")


def test_subtitle_plus_dub_uses_real_pipeline_not_admin_test_path():
    source = inspect.getsource(bot.execute_subtitle_plus_dub_full_from_callback)
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "execute_video_dubbing_pipeline" in source
    assert "subtitle_dub_product_pipeline.process_subtitle_dub_job" in core_source
    assert "admin_smoke" not in source.lower()
    assert "cmd_tool_test" not in source


def test_subtitle_plus_dub_no_public_admin_test_copy():
    texts = [
        bot.subtitle_plus_dub_clean_failure_text("vi"),
        bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "vi"),
    ]
    lowered = "\n".join(texts).lower()
    assert "admin" not in lowered
    assert "test" not in lowered


def test_subtitle_plus_dub_no_public_adapter_missing_code():
    lowered = bot.subtitle_plus_dub_clean_failure_text("vi").lower()
    for forbidden in ("adapter", "adapter_missing", "code", "<code>", "provider", "asr", "tts", "mux", "ffmpeg"):
        assert forbidden not in lowered


def test_product_failure_copy_clean():
    lowered = bot.subtitle_plus_dub_clean_failure_text("vi").lower()
    for forbidden in ("admin", "test", "provider", "api", "asr", "tts", "mux", "ffmpeg", "adapter", "component", "code", "debug", "traceback", "config", "kỹ thuật"):
        assert forbidden not in lowered
    assert "Hệ thống chưa trừ Xu" in bot.subtitle_plus_dub_clean_failure_text("vi")


def test_no_provider_before_confirm_subtitle_plus_dub(monkeypatch):
    uid = 919707
    _combo_state(uid, flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")

    async def forbidden_pipeline(*_args, **_kwargs):
        raise AssertionError("pipeline must wait for final confirmation")

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", forbidden_pipeline)
    query = CaptureQuery(uid, f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}")
    asyncio.run(bot.handle_video_dubbing_callback(_query_update(query), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "no_subtitle_menu"


def test_no_charge_before_valid_final_artifact(monkeypatch):
    uid = 919708
    calls = {"charge": 0}
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": False, "status": "blocked"})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: calls.__setitem__("charge", calls["charge"] + 1))
    query = SimpleNamespace(from_user=SimpleNamespace(id=uid), message=CaptureMessage())
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            query,
            SimpleNamespace(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "process_type": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            },
            "vi",
        )
    )
    assert result["ok"] is False
    assert calls["charge"] == 0


def test_back_from_has_subtitle_returns_subtitle_plus_dub():
    keyboard = bot.video_dubbing_upload_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            "flow_type": bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
        },
    )
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in _callbacks(keyboard)


def test_back_from_no_subtitle_returns_subtitle_plus_dub():
    keyboard = bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in _callbacks(keyboard)


def test_back_from_no_subtitle_subpaths_returns_no_subtitle_menu():
    for subpath in (bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB, bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB):
        keyboard = bot.video_dubbing_upload_keyboard(
            "vi",
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                "combo_subpath": subpath,
            },
        )
        assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(keyboard)


def test_translation_center_back_routing_full_matrix():
    assert "menu|translate" in _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        assert "videodub|back_type" in _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": mode, "origin": "translation"}))
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in _callbacks(bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi"))
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(
        bot.video_dubbing_upload_keyboard(
            "vi",
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
            },
        )
    )
