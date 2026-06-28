import inspect
import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot
from services import dubbing_pipeline as dp


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_auto_subtitle_outputs_final_video_not_editor():
    markup = bot.video_dubbing_output_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
            "active_flow": "auto_subtitle",
            "subtitle_ref": "video_dubbing_artifact:1:source",
            "output_type": "burn",
        },
    )
    labels = _labels(markup)
    callbacks = _callbacks(markup)

    assert "📹 Tải video phụ đề" in labels
    assert "📄 Tải SRT" in labels
    assert "videodub|final" in callbacks
    assert not any("Xem thử" in label or "Chỉnh phụ đề" in label for label in labels)
    assert not {"videodub|subtitle_preview_lines", "videodub|subtitle_editor"}.intersection(callbacks)


def test_subtitle_translate_outputs_final_video_without_dub_or_editor():
    markup = bot.video_dubbing_output_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "active_flow": "subtitle_translate",
            "target_language": "English",
            "translated_subtitle_ref": "video_dubbing_artifact:1:translated",
            "output_type": "burn",
        },
    )
    labels = _labels(markup)
    callbacks = _callbacks(markup)

    assert "📹 Tải video phụ đề dịch" in labels
    assert "📄 Tải SRT dịch" in labels
    assert "videodub|final" in callbacks
    assert not any("Lồng tiếng" in label or "Xem thử" in label or "Chỉnh phụ đề" in label for label in labels)
    assert not {"videodub|subtitle_preview_lines", "videodub|subtitle_editor", "videodub|result_dub_translated"}.intersection(callbacks)


def test_confirm_keyboards_hide_preview_for_public_product_flows():
    expected = {
        bot.VIDEO_SUBTITLE_MODE_CREATE: "✅ Tạo phụ đề gốc",
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE: "✅ Xác nhận dịch",
        bot.VIDEO_SUBTITLE_MODE_DUB: "✅ Xác nhận lồng tiếng",
    }
    for mode, first_label in expected.items():
        markup = bot.video_dubbing_confirm_keyboard("vi", {"mode": mode, "video_processing_mode": mode})
        labels = _labels(markup)
        callbacks = _callbacks(markup)
        assert labels[0] == first_label
        if mode != bot.VIDEO_SUBTITLE_MODE_CREATE:
            assert "❌ Hủy" in labels
        assert not any("Xem thử" in label or "Nghe thử" in label for label in labels)
        assert callbacks[0] == "videodub|final"


def test_subtitle_plus_dub_full_flow_targets_final_video():
    markup = bot.subtitle_plus_dub_confirm_keyboard("vi")
    assert _labels(markup)[0] == "✅ Tạo video hoàn chỉnh"
    assert "videodub|combo_full_dub" in _callbacks(markup)
    assert not any("Nghe thử" in label or "Xem thử" in label for label in _labels(markup))


class CaptureMessage:
    def __init__(self):
        self.video = []
        self.audio = []
        self.documents = []

    async def reply_video(self, **kwargs):
        self.video.append(kwargs)

    async def reply_audio(self, **kwargs):
        self.audio.append(kwargs)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)


def test_final_outputs_send_mp4_first_for_all_video_product_modes():
    async def run_case(mode):
        message = CaptureMessage()
        sent = await bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=mode,
            subtitle_items=[{"output_type": "srt", "filename": "x.srt", "bytes": b"1\n00:00:00,000 --> 00:00:01,000\nXin chao\n"}],
            audio_bytes=b"audio",
            video_bytes=b"mp4",
            lang="vi",
        )
        return message, sent

    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        message, sent = asyncio.run(run_case(mode))
        assert sent == {"documents": 0, "audio": 0, "video": 1}
        assert len(message.video) == 1
        assert message.audio == []
        assert message.documents == []


def test_voice_video_sends_audio_fallback_only_when_mp4_missing():
    async def run_case():
        message = CaptureMessage()
        sent = await bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=b"",
            lang="vi",
        )
        return message, sent

    message, sent = asyncio.run(run_case())

    assert sent == {"documents": 0, "audio": 1, "video": 0}
    assert message.video == []
    assert len(message.audio) == 1
    assert "chưa ghép được thành video hoàn chỉnh" in message.audio[0]["caption"]


def test_b12_4_confirm_texts_have_price_and_final_product_contract():
    auto_text = bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_duration": 30}, "vi")
    translate_text = bot.video_dubbing_confirm_text({
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "target_language": "English",
        "source_duration": 30,
    }, "vi")
    dub_text = bot.video_dubbing_confirm_text({
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "target_language": "English",
        "voice_style": "giọng nữ mặc định",
        "voice_speed": "1.0",
        "source_duration": 30,
    }, "vi")

    assert "Chi phí:" in auto_text and "Xuất video MP4 có phụ đề" in auto_text
    assert "Tổng:" in translate_text and "Xuất video MP4 có phụ đề dịch" in translate_text
    assert "Tổng:" in dub_text and "Xuất video MP4 lồng tiếng" in dub_text
    assert "xem thử" not in (auto_text + translate_text + dub_text).lower()


def test_b12_4_receipt_keyboards_final_only_no_tool_jump():
    create_markup = bot.video_dubbing_receipt_keyboard("vi", "translation", {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "active_flow": "auto_subtitle",
        "final_video_available": "1",
        "final_subtitle_available": "1",
    })
    translate_markup = bot.video_dubbing_receipt_keyboard("vi", "translation", {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "active_flow": "subtitle_translate",
        "final_video_available": "1",
        "final_subtitle_available": "1",
        "final_translation_asset_ids": "translation-asset",
    })
    dub_markup = bot.video_dubbing_receipt_keyboard("vi", "translation", {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "active_flow": "dub_audio",
        "final_video_available": "1",
        "final_audio_available": "1",
    })

    create_callbacks = _callbacks(create_markup)
    translate_callbacks = _callbacks(translate_markup)
    dub_callbacks = _callbacks(dub_markup)
    assert "videodub|download_final_video" in create_callbacks
    assert "videodub|download_final_subtitle" in create_callbacks
    assert "videodub|result_dub_original" not in create_callbacks
    assert "videodub|result_translate_dub" not in create_callbacks
    assert "videodub|download_final_video" in translate_callbacks
    assert "videodub|download_final_subtitle" in translate_callbacks
    assert "videodub|result_dub_translated" not in translate_callbacks
    assert "videodub|download_final_video" in dub_callbacks
    assert "videodub|download_final_audio" in dub_callbacks


def test_b12_4_dialogue_unavailable_public_copy():
    text = bot.video_dubbing_dialogue_unavailable_text("vi")
    callbacks = _callbacks(bot.video_dubbing_dialogue_unavailable_keyboard("vi"))
    assert "chưa lấy được lời thoại" in text
    assert "chưa trừ Xu" in text
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_CREATE}" in callbacks
    assert "videodub|retry_media" in callbacks


def test_restore_previous_dub_audio_engine_for_live_pipeline():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "synthesize_dub_segment_chunks" in source
    assert "build_dub_timeline_audio" in source
    assert "video_dubbing_render_video" in source
    assert "process_dubbing_pipeline" not in source


def test_xem_thu_does_not_open_subtitle_editor():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    locked = (
        'if action == "subtitle_preview_lines":\n'
        "        return await safe_edit_or_send(\n"
        "            query,\n"
        "            video_dubbing_preview_locked_text"
    )
    assert locked in source


def _write(path: Path, data: bytes = b"x") -> str:
    path.write_bytes(data)
    return str(path)


def test_render_subtitled_video_outputs_mp4(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    subtitle = _write(tmp_path / "sub.srt", b"1\n00:00:00,000 --> 00:00:01,000\nXin chao\n")
    output = tmp_path / "out.mp4"
    calls = []

    def fake_run(command, *, cwd):
        calls.append(command)
        Path(cwd, "final.mp4").write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(dp, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(dp, "_run_ffmpeg", fake_run)

    assert dp.render_subtitled_video(video, subtitle, str(output)) == str(output.resolve())
    assert output.read_bytes() == b"mp4"
    assert "subtitles=subtitle.srt" in calls[0]


def test_process_final_video_product_translate_subtitle(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    subtitle = _write(tmp_path / "translated.srt", b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    output = tmp_path / "translated.mp4"

    monkeypatch.setattr(dp, "render_subtitled_video", lambda _video, _subtitle, out, style_options=None: _write(Path(out), b"mp4"))

    result = dp.process_final_video_product(
        mode="translated_subtitle_video",
        source_video_path=video,
        translated_subtitle_path=subtitle,
        output_path=str(output),
    )

    assert result["ok"] is True
    assert result["result_type"] == "mp4"
    assert Path(result["video_path"]).read_bytes() == b"mp4"


def test_process_final_video_product_dub_audio_fallback(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    audio = _write(tmp_path / "dub.mp3", b"audio")

    def fail_mux(*_args, **_kwargs):
        raise dp.DubbingPipelineError("mux_failed")

    monkeypatch.setattr(dp, "mux_dubbed_video", fail_mux)

    result = dp.process_final_video_product(
        mode="dubbed_video",
        source_video_path=video,
        dub_audio_path=audio,
        output_path=str(tmp_path / "dubbed.mp4"),
    )

    assert result["ok"] is True
    assert result["result_type"] == "audio_fallback"
    assert result["audio_path"] == str(Path(audio).resolve())
