import asyncio
import inspect
import pathlib
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat_id = 170690
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_audio(self, **kwargs):
        self.outputs.append({"audio": True, **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id="audio-id"))


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def test_tts_provider_readiness_contract_has_default_voice_ids():
    readiness = bot.get_tts_provider_readiness(public=False)

    assert set(readiness) >= {
        "ready",
        "provider",
        "model",
        "supported_voices",
        "default_female_voice_id",
        "default_male_voice_id",
        "reason",
    }
    assert readiness["default_female_voice_id"]
    assert readiness["default_male_voice_id"]
    assert readiness["default_female_voice_id"] != readiness["default_male_voice_id"]


def test_voice_engine_readiness_uses_tts_contract():
    readiness = bot._product_engine_readiness("voice_tts")

    assert "default_female_voice_id" in readiness
    assert "default_male_voice_id" in readiness
    assert "supported_voices" in readiness


def test_tts_public_guard_and_failure_copy():
    assert bot.tts_provider_guard_text("vi") == (
        "Giọng đọc AI đang được chuẩn bị. TOAN AAS chưa gọi provider và chưa trừ Xu. "
        "Anh/chị có thể thử lại sau hoặc dùng công cụ khác trước."
    )
    assert bot.tts_failure_text("vi") == (
        "TOAN AAS chưa tạo được giọng đọc lúc này. Hệ thống chưa trừ Xu. "
        "Anh/chị có thể thử lại hoặc đổi giọng khác."
    )


def test_tts_failure_keyboard_has_required_actions():
    labels = _labels(bot.tts_failure_keyboard("vi"))
    callbacks = _callbacks(bot.tts_failure_keyboard("vi"))

    assert labels == ["🔁 Thử lại", "🎙 Đổi giọng", "✏️ Sửa nội dung", "⬅️ Quay lại", "🏠 Menu chính"]
    assert any(callback.endswith("|voice_tts_guard") for callback in callbacks)
    assert any(callback.endswith("|voice_hub") for callback in callbacks)
    assert any(callback.endswith("|voice_tts_text") for callback in callbacks)
    assert "menu|main" in callbacks


def test_asr_failure_keyboard_offers_dialogue_text():
    labels = _labels(bot.video_dubbing_asr_failure_keyboard("vi"))
    callbacks = _callbacks(bot.video_dubbing_asr_failure_keyboard("vi"))

    assert labels == ["🔁 Thử lại", "📄 Gửi file phụ đề", "✍️ Nhập lời thoại", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "videodub|enter_dialogue_text" in callbacks


def test_manual_dialogue_text_routes_translate_without_asr(monkeypatch):
    uid = 176901
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "dialogue_text_input",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        active_flow="subtitle_translate",
        video_duration=8,
    )
    message = CaptureMessage("Xin chào TOAN AAS. Đây là lời thoại để dịch phụ đề.")

    assert asyncio.run(bot.handle_video_dubbing_pending_text(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["subtitle_ref"]
    assert state["source_subtitle_ref"] == state["subtitle_ref"]
    assert int(state["subtitle_segment_count"]) > 0
    assert "-->" in bot.get_video_dubbing_artifact(uid, state["subtitle_ref"])
    assert "Dịch phụ đề sang ngôn ngữ nào" in message.outputs[-1]["text"]


def test_manual_dialogue_text_routes_subtitle_plus_dub_to_original_ready(monkeypatch):
    uid = 176902
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_dubbing_pending(
        uid,
        "dialogue_text_input",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        video_duration=8,
    )
    message = CaptureMessage("Đoạn một. Đoạn hai để lồng tiếng theo phụ đề.")

    assert asyncio.run(bot.handle_video_dubbing_pending_text(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "original_subtitle_ready"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB
    assert state["source_subtitle_ref"] == state["subtitle_ref"]
    assert "Đã tạo phụ đề gốc" in message.outputs[-1]["text"]


def test_sample_subtitle_file_parses_to_timed_segments():
    subtitle_path = pathlib.Path(__file__).resolve().parent / "fixtures" / "sample_vi.srt"
    with open(subtitle_path, "r", encoding="utf-8") as handle:
        segments = bot.video_dubbing_segments_from_subtitle(handle.read())

    assert len(segments) == 3
    assert segments[0]["start"] == 0
    assert segments[0]["end"] > segments[0]["start"]
    assert "Xin chào" in segments[0]["text"]


def test_subtitle_plus_dub_preview_tts_receives_segments_not_whole_srt(monkeypatch):
    uid = 176903
    bot.clear_video_dubbing_pending(uid)
    srt = (
        "1\n00:00:00,000 --> 00:00:02,000\nXin chào\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nTOAN AAS\n"
    )
    ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", srt)
    state = bot.set_video_dubbing_pending(
        uid,
        "dub_confirmation",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        subtitle_ref=ref,
        source_subtitle_ref=ref,
        dub_source="original_subtitle",
        voice_kind="default_female",
        voice_style="Nữ mặc định",
        voice_speed="1.0",
    )
    seen_texts = []

    async def fake_synthesize(segments, **_kwargs):
        seen_texts.extend(item["text"] for item in segments)
        return {"provider": "unit", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"raw"}]}

    async def fake_timeline(_chunks, _duration):
        return b"timeline-audio", "ok"

    async def fake_normalize(audio):
        return audio, "ok"

    async def fake_cap(audio, _seconds):
        return audio, "ok"

    monkeypatch.setattr(bot, "synthesize_dub_segment_chunks", fake_synthesize)
    monkeypatch.setattr(bot, "build_dub_timeline_audio", fake_timeline)
    monkeypatch.setattr(bot, "normalize_dub_audio_bytes", fake_normalize)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", fake_cap)
    query = SimpleNamespace(from_user=SimpleNamespace(id=uid), message=CaptureMessage())

    result = asyncio.run(bot.execute_subtitle_plus_dub_voice_preview(query, SimpleNamespace(), state, "vi"))

    assert result["ok"] is True
    assert seen_texts == ["Xin chào", "TOAN AAS"]
    assert all("-->" not in text for text in seen_texts)


def test_smoke_subtitle_pipeline_has_no_fake_asr_stub():
    source = inspect.getsource(__import__("tools.smoke_subtitle_pipeline", fromlist=["run_smoke"]))

    assert "fake_transcribe" not in source
    assert "smoke_unit_asr" not in source
