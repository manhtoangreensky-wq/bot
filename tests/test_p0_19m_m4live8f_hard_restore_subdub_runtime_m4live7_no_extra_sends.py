import asyncio
import inspect
from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
BASELINE_SHA = "0e06469c9c13d4998886dd8f5115c019ed65f24d"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-m4live8f" + (b"x" * 4096)
SRT_TEXT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"


class CaptureMessage:
    chat_id = 123

    def __init__(self):
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", text, kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()


def _function_source(name: str) -> str:
    return inspect.getsource(getattr(bot, name))


async def _deliver_with_video(mode: str, monkeypatch):
    async def fake_send_generated_video_bytes_for_delivery(*_args, **_kwargs):
        return {
            "sent": True,
            "delivery_method": "video",
            "file_size_mb": 1.0,
            "size_limit_used": 45.0,
            "telegram_message_id": "mp4-message",
        }

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_send_generated_video_bytes_for_delivery)
    message = CaptureMessage()
    result = await bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=mode,
        active_flow="",
        subtitle_items=bot.video_dubbing_subtitle_output_items(SRT_TEXT, "srt", mode),
        srt_text=SRT_TEXT,
        audio_bytes=b"dub" if mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else b"",
        video_bytes=MP4_BYTES,
        lang="vi",
        include_subtitle_outputs=True,
        strict_validation=False,
    )
    return result, message


def test_m4live8f_restores_runtime_functions_to_m4live7_and_removes_m4live8_helpers():
    assert "def subdub_should_suppress_generic_fail_for_active_job" not in BOT_SOURCE
    assert "def subdub_m4live7_subtitle_only_duration_fields" not in BOT_SOURCE
    assert "def subdub_long_video_chunk_plan" not in BOT_SOURCE

    for name in (
        "_execute_video_dubbing_pipeline_core",
        "execute_video_dubbing_pipeline",
        "handle_video_dubbing_callback",
        "send_subdub_fail_once",
        "resolve_video_dub_tts_voice",
        "subdub_duration_gate_payload",
        "video_dubbing_voice_payload",
    ):
        source = _function_source(name)
        assert "subdub_should_suppress_generic_fail_for_active_job" not in source
        assert "subdub_m4live7_subtitle_only_duration_fields" not in source
        assert "subdub_long_video_chunk_plan" not in source


def test_subtitle_translate_mp4_success_does_not_auto_send_srt_or_partial_warning(monkeypatch):
    result, message = asyncio.run(_deliver_with_video(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, monkeypatch))

    assert result["final_mp4_delivered"] is True
    assert result["terminal_public_outcome_type"] == "delivered_success"
    assert result["srt_auto_send_suppressed"] is True
    assert result["srt_suppress_reason"] in {"video_delivered", "video_delivered_terminal"}
    assert result["documents"] == 0
    assert result["srt_delivery_message_id"] == ""
    assert not any(call[0] == "document" for call in message.calls)
    assert "chưa tạo được video hoàn chỉnh" not in str(message.calls)


def test_auto_subtitle_mp4_success_does_not_auto_send_srt_or_partial_warning(monkeypatch):
    result, message = asyncio.run(_deliver_with_video(bot.VIDEO_SUBTITLE_MODE_CREATE, monkeypatch))

    assert result["final_mp4_delivered"] is True
    assert result["terminal_public_outcome_type"] == "delivered_success"
    assert result["srt_auto_send_suppressed"] is True
    assert result["documents"] == 0
    assert not any(call[0] == "document" for call in message.calls)
    assert "chưa tạo được video hoàn chỉnh" not in str(message.calls)


def test_subtitle_dub_mp4_success_does_not_auto_send_audio_srt_or_fail_copy(monkeypatch):
    result, message = asyncio.run(_deliver_with_video(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, monkeypatch))

    assert result["final_mp4_delivered"] is True
    assert result["terminal_public_outcome_type"] == "delivered_success"
    assert result["audio_auto_send_suppressed"] is True
    assert result["srt_auto_send_suppressed"] is True
    assert result["audio"] == 0
    assert result["documents"] == 0
    assert not any(call[0] in {"document", "audio", "text"} for call in message.calls)
    assert "chưa tạo được video hoàn chỉnh" not in str(message.calls)


def test_partial_srt_without_mp4_never_gets_success_receipt():
    message = CaptureMessage()
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="",
            subtitle_items=bot.video_dubbing_subtitle_output_items(SRT_TEXT, "srt", bot.VIDEO_SUBTITLE_MODE_TRANSLATE),
            srt_text=SRT_TEXT,
            video_bytes=b"",
            lang="vi",
            include_subtitle_outputs=True,
            strict_validation=False,
        )
    )

    assert result["final_mp4_delivered"] is False
    assert result["terminal_artifact_type"] != "video"
    assert result["success_blocked_reason"] == "missing_valid_delivered_mp4"
    assert result.get("terminal_public_outcome_type") in {"", "failure"}
