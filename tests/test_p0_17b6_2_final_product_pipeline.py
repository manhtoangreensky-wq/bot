import asyncio
import inspect
import os
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_document(self, **kwargs):
        self.outputs.append(("document", kwargs))

    async def reply_audio(self, **kwargs):
        self.outputs.append(("audio", kwargs))

    async def reply_video(self, **kwargs):
        self.outputs.append(("video", kwargs))

    async def reply_text(self, text, **kwargs):
        self.outputs.append(("text", {"text": text, **kwargs}))


class DummyQuery:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.edits = []
        self.answers = []
        self.message = SimpleNamespace(chat_id=uid, outputs=[])

        async def reply_text(text, **kwargs):
            self.message.outputs.append({"text": str(text), **kwargs})
            return SimpleNamespace(text=text)

        self.message.reply_text = reply_text

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _callback_update(query):
    return SimpleNamespace(callback_query=query, effective_user=query.from_user)


def test_translation_dub_studio_simple_menu():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels == [
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề",
        "🎙 Lồng tiếng",
        "🎞 Phụ đề + Lồng tiếng",
        "⬅️ Quay lại",
        "🏠 Menu chính",
    ]


def test_no_unrelated_buttons_in_translation_dub_studio():
    text = " ".join(_labels(bot.video_dubbing_menu_keyboard("vi", "translation"))).lower()
    for forbidden in ("tải video từ link", "media", "chỉnh phụ đề", "tắt dịch tự động", "video studio"):
        assert forbidden not in text


def test_tool_source_contracts():
    file_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE,
    }
    transcript_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "active_flow": bot.VIDEO_DUBBING_FLOW_TRANSCRIPT,
    }
    dub_state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}
    assert _callbacks(bot.video_dubbing_source_keyboard("vi", file_state)) == [
        "videodub|source_upload",
        "videodub|back_type",
        "menu|main",
    ]
    assert "videodub|source_recent_subtitle" not in _callbacks(
        bot.video_dubbing_source_keyboard("vi", transcript_state)
    )
    assert "videodub|source_recent_subtitle" not in _callbacks(
        bot.video_dubbing_source_keyboard("vi", dub_state)
    )
    assert "videodub|path|has_subtitle" in _callbacks(bot.video_dubbing_source_keyboard("vi", dub_state))
    assert bot.video_dubbing_mode_needs_asr_provider(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE, file_state
    ) is False


def test_subtitle_plus_dub_stepwise_only():
    uid = 917620
    bot.clear_video_dubbing_pending(uid)
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "source_file_id": "source",
        "video_file_id": "source",
        "active_flow": "subtitle_plus_dub",
    }
    next_state, text, markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    assert next_state["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert next_state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert next_state["step"] == "language"
    assert "Chọn ngôn ngữ" in text or "ngôn ngữ" in text.lower()
    assert "videodub|final" not in _callbacks(markup)
    bot.clear_video_dubbing_pending(uid)


def test_subtitle_qc_line_length_duration_and_reading_speed():
    result = bot.video_dubbing_qc_segments([
        {
            "start": 0,
            "end": 10,
            "text": "Đây là một câu rất dài cần được chia thành nhiều phần để phụ đề dễ đọc và không chạy quá nhanh trên màn hình.",
        }
    ])
    assert result
    for segment in result:
        assert 0.1 <= segment["end"] - segment["start"] <= 7.01
        lines = segment["text"].splitlines()
        assert len(lines) <= 2
        assert all(len(line) <= 42 for line in lines)


def test_translation_qc_splits_long_translation_inside_original_timing():
    result = bot.video_dubbing_qc_segments([
        {
            "start": 5,
            "end": 12,
            "text": "This translated sentence is intentionally long so the subtitle quality control has to split it across multiple timed captions while staying inside the original speaking window.",
        }
    ], preserve_timestamps=True)
    assert len(result) > 1
    assert result[0]["start"] == 5
    assert result[-1]["end"] == 12
    assert len({(item["start"], item["end"]) for item in result}) == len(result)


def test_receipt_next_actions_stay_final_only(monkeypatch):
    uid = 917621
    bot.clear_video_dubbing_pending(uid)
    state = bot.set_video_dubbing_pending(
        uid,
        "completed",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        active_flow="auto_subtitle",
        source_file_id="source",
        subtitle_ref="video_dubbing_artifact:917621:source_subtitle",
        final_video_available="1",
        final_subtitle_available="1",
    )
    callbacks = _callbacks(bot.video_dubbing_receipt_keyboard("vi", "translation", state))
    assert "videodub|download_final_video" in callbacks
    assert "videodub|download_final_subtitle" in callbacks
    assert "videodub|result_translate" not in callbacks
    assert "videodub|result_dub_original" not in callbacks
    assert "videodub|result_translate_dub" not in callbacks

    bot.clear_video_dubbing_pending(uid)


def test_translated_receipt_can_continue_to_dub_without_file_translate_leak():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "active_flow": "subtitle_translate",
        "target_language": "English",
        "translated_subtitle_ref": "video_dubbing_artifact:917622:translated",
    }
    callbacks = _callbacks(bot.video_dubbing_receipt_keyboard("vi", "translation", state))
    assert "videodub|result_dub_translated" not in callbacks
    assert "videodub|result_translate" in callbacks

    file_state = {**state, "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE}
    assert "videodub|result_dub_translated" not in _callbacks(
        bot.video_dubbing_receipt_keyboard("vi", "translation", file_state)
    )


def test_public_output_matches_tool():
    subtitle_items = [
        {"output_type": "srt", "bytes": b"srt", "filename": "result.srt"},
        {"output_type": "vtt", "bytes": b"vtt", "filename": "result.vtt"},
        {"output_type": "txt", "bytes": b"txt", "filename": "result.txt"},
    ]
    auto = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        auto,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        active_flow="auto_subtitle",
        subtitle_items=subtitle_items,
    ))
    assert result == {"documents": 1, "audio": 0, "video": 0}
    assert [kind for kind, _ in auto.outputs] == ["document"]

    transcript = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        transcript,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        active_flow=bot.VIDEO_DUBBING_FLOW_TRANSCRIPT,
        subtitle_items=subtitle_items,
    ))
    assert result == {"documents": 1, "audio": 0, "video": 0}
    assert transcript.outputs[0][1]["filename"].endswith(".txt")

    dub = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        dub,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        audio_bytes=b"audio",
        subtitle_items=subtitle_items,
    ))
    assert result == {"documents": 0, "audio": 1, "video": 0}


def test_mux_unavailable_no_fake_mp4():
    message = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"audio",
        subtitle_items=[{"output_type": "srt", "bytes": b"srt", "filename": "result.srt"}],
        video_bytes=b"",
    ))
    assert result == {"documents": 1, "audio": 1, "video": 0}
    assert "video" not in [kind for kind, _ in message.outputs]
    assert "document" in [kind for kind, _ in message.outputs]
    assert "text" not in [kind for kind, _ in message.outputs]


def test_no_duplicate_job():
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    state = {
        "source_file_unique_id": "unique",
        "active_flow": "auto_subtitle",
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
    }
    key = bot.subtitle_dub_pipeline_job_key(1, 2, state)
    first, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=2)
    second, duplicate = bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=2)
    assert first is True
    assert second is False
    assert duplicate["job_id"] == job["job_id"]
    assert duplicate["duplicate_count"] == 1


def test_temp_workspace_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(tmp_path / "toan_aas_pipeline"))
    workspace = bot.create_subtitle_dub_pipeline_workspace("job-1")
    manifest = bot.write_subtitle_dub_pipeline_manifest(workspace, {"ok": True})
    assert os.path.exists(manifest)
    assert bot.cleanup_subtitle_dub_pipeline_workspace(workspace) is True
    assert not os.path.exists(workspace)


def test_media_handler_checks_active_flow_first():
    document_source = inspect.getsource(bot.handle_document_cache_only)
    video_source = inspect.getsource(bot.handle_media_cache_only)
    for source in (document_source, video_source):
        assert source.index("handle_video_dubbing_pending_upload") < source.index(
            "handle_video_product_pending_media"
        )


def test_no_global_15mb_limit():
    assert bot.PIPELINE_MAX_INPUT_MB_PUBLIC == 50
    assert bot.PIPELINE_MAX_INPUT_MB_ADMIN == 100
    assert bot.PIPELINE_MAX_DURATION_SECONDS_PUBLIC == 90
    assert bot.PIPELINE_MAX_DURATION_SECONDS_ADMIN == 180


def test_public_no_technical_terms():
    samples = [
        bot.video_dubbing_source_text(
            {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "active_flow": "auto_subtitle"}, "vi"
        ),
        bot.video_dubbing_source_text(
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "active_flow": "subtitle_translate"}, "vi"
        ),
        bot.video_dubbing_source_text(
            {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "active_flow": "dub_audio"}, "vi"
        ),
        bot.video_dubbing_source_text(
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE,
            },
            "vi",
        ),
    ]
    forbidden = (
        "asr",
        "tts segment",
        "timeline audio",
        "mux",
        "smoke",
        "provider",
        "mode_disabled",
        "asr_adapter_missing",
        "traceback",
        "bearer",
        "api key",
    )
    for sample in samples:
        lowered = sample.lower()
        assert all(term not in lowered for term in forbidden)
