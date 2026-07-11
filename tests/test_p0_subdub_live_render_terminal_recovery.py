import asyncio
from pathlib import Path

import bot


ROOT = Path(bot.__file__).resolve().parent


def _delivered_job(mode: str) -> dict:
    return {
        "mode": mode,
        "video_delivery_message_id": "telegram-video-501",
        "delivery_message_id": "telegram-video-501",
        "delivery_success": True,
        "delivery_succeeded": True,
        "final_mp4_delivered": True,
        "terminal_state": "delivered",
        "terminal_public_outcome_sent": True,
        "terminal_public_outcome_type": "success",
    }


def test_runtime_image_installs_unicode_subtitle_fonts():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for package in (
        "fontconfig",
        "fonts-dejavu-core",
        "fonts-noto-core",
        "fonts-noto-cjk",
        "fonts-noto-extra",
    ):
        assert package in dockerfile
    assert "fc-cache -f" in dockerfile


def test_unsupported_deepl_target_uses_next_translation_route(monkeypatch):
    calls = []

    async def forbidden_deepl(*_args, **_kwargs):
        raise AssertionError("Hindi must not be submitted as EN-US to DeepL")

    async def fake_key4u(text, target):
        calls.append((text, target))
        return "नमस्ते दुनिया"

    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "translate_with_deepl", forbidden_deepl)
    monkeypatch.setattr(bot, "key4u_translation_provider_available", lambda: True)
    monkeypatch.setattr(bot, "translate_with_key4u", fake_key4u)

    result = asyncio.run(bot.translate_to_language("Hello world", "Hindi"))

    assert result["provider"] == "key4u"
    assert result["target"] == "hi"
    assert result["text"] == "नमस्ते दुनिया"
    assert calls == [("Hello world", "hi")]


def test_supported_english_target_keeps_deepl_route(monkeypatch):
    calls = []

    async def fake_deepl(text, target):
        calls.append((text, target))
        return "Natural English"

    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "translate_with_deepl", fake_deepl)
    monkeypatch.setattr(bot, "key4u_translation_provider_available", lambda: False)

    result = asyncio.run(bot.translate_to_language("Xin chao", "English"))

    assert result["provider"] == "deepl"
    assert result["target"] == "en"
    assert calls == [("Xin chao", "en")]


def test_subtitle_modes_recover_only_from_real_delivered_video():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        result = bot.subdub_restore_delivered_video_result(
            mode,
            {"ok": False, "status": "LATE_RUNTIME_ERROR"},
            _delivered_job(mode),
            {"mode": mode},
        )
        assert result["ok"] is True
        assert result["has_video"] is True
        assert result["video_delivery_message_id"] == "telegram-video-501"
        assert result["state"]["panel_final_percent"] == 100
        assert "Đã gửi video" in bot.video_dubbing_receipt_text(result["state"], result, "vi")


def test_subtitle_modes_never_fake_success_without_video_message_id():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        original = {"ok": False, "status": "RENDER_FAILED"}
        result = bot.subdub_restore_delivered_video_result(
            mode,
            original,
            {"terminal_state": "delivered", "final_mp4_delivered": True},
            {"mode": mode},
        )
        assert result == original
