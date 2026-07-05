import asyncio
from types import SimpleNamespace

import bot


SOURCE_SRT = "1\n00:00:00,000 --> 00:00:02,000\n你好\n"
STALE_SRT = "1\n00:00:00,000 --> 00:00:02,000\nSTALE OLD TEXT\n"
TRANSLATED_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"


def test_subdub_translate_ignores_stale_default_translated_artifact(monkeypatch):
    translate_calls = []

    def fake_get_artifact(_user_id, ref_or_kind):
        if ref_or_kind == "source-ref":
            return SOURCE_SRT
        if ref_or_kind == "translated_subtitle":
            return STALE_SRT
        return ""

    async def fake_translate(segments, target_language, **_kwargs):
        translate_calls.append((segments, target_language))
        return {
            "segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            "provider": "fake_translate",
            "srt": TRANSLATED_SRT,
        }

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", fake_get_artifact)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda _uid, kind, _value: f"new-{kind}-ref")
    monkeypatch.setattr(bot, "translate_subtitle_segments", fake_translate)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            SimpleNamespace(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "process_type": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "source_subtitle_ref": "source-ref",
                "target_language": "vi",
            },
            919900,
            allow_admin=True,
        )
    )

    assert translate_calls, "upload moi phai dich lai, khong duoc an stale translated_subtitle"
    assert prepared["output_subtitle"] == TRANSLATED_SRT.strip()
    assert "STALE OLD TEXT" not in prepared["output_subtitle"]


def test_subdub_translate_uses_explicit_translated_ref_only(monkeypatch):
    async def fail_translate(*_args, **_kwargs):
        raise AssertionError("explicit translated_subtitle_ref should be reused")

    def fake_get_artifact(_user_id, ref_or_kind):
        if ref_or_kind == "source-ref":
            return SOURCE_SRT
        if ref_or_kind == "translated-ref":
            return TRANSLATED_SRT
        if ref_or_kind == "translated_subtitle":
            return STALE_SRT
        return ""

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", fake_get_artifact)
    monkeypatch.setattr(bot, "translate_subtitle_segments", fail_translate)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            SimpleNamespace(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "process_type": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "source_subtitle_ref": "source-ref",
                "translated_subtitle_ref": "translated-ref",
                "target_language": "vi",
            },
            919900,
            allow_admin=True,
        )
    )

    assert prepared["output_subtitle"] == TRANSLATED_SRT
