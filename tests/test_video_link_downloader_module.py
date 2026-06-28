import inspect

import bot
from providers.video_downloader_provider import VideoDownloaderProvider


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_video_downloader_hidden_from_main_video_menu():
    markup = bot.main_video_keyboard("vi")
    assert "📥 Tải video từ link" not in _labels(markup)
    assert "vdownload|start" not in _callbacks(markup)


def test_video_downloader_not_in_translation_studio():
    translation_labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    translation_callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📥 Tải video từ link" not in translation_labels
    assert "🔗 Tải video từ link" not in translation_labels
    assert "vdownload|start" not in translation_callbacks
    assert "videodub|link_start" not in translation_callbacks


def test_video_downloader_detects_tiktok_link():
    detection = bot.video_downloader_detect_link("https://www.tiktok.com/@toanaas/video/123456789")
    assert detection["ok"] is True
    assert detection["platform"] == "TikTok"


def test_video_downloader_detects_facebook_link():
    detection = bot.video_downloader_detect_link("https://www.facebook.com/reel/123456789")
    assert detection["ok"] is True
    assert detection["platform"] == "Facebook"


def test_video_downloader_direct_mp4():
    detection = bot.video_downloader_detect_link("https://cdn.example.com/public/video-demo.mp4")
    assert detection["ok"] is True
    assert detection["platform"] == "Direct video"
    assert detection["direct_video"] is True


def test_video_downloader_unsupported_link_guard():
    detection = bot.video_downloader_detect_link("https://example.com/articles/post-1")
    assert detection["ok"] is False
    assert detection["reason"] == "unsupported_platform"
    text = bot.video_downloader_guard_text(detection["reason"], "vi", detection)
    assert "chưa hỗ trợ" in text
    assert "chưa trừ Xu" in text


def test_video_downloader_no_ai_provider_call():
    source = "\n".join(
        [
            inspect.getsource(bot.handle_video_downloader_callback),
            inspect.getsource(bot.handle_video_downloader_pending_text),
            inspect.getsource(VideoDownloaderProvider),
        ]
    )
    for forbidden in ("AgentGemini", "gemini_client", "openai_client", "shopaikey", "key4u", "AgentDownloader", "execute_engine("):
        assert forbidden not in source


def test_video_downloader_no_xu_on_fail():
    source = "\n".join(
        [
            inspect.getsource(bot.handle_video_downloader_callback),
            inspect.getsource(bot.handle_video_downloader_pending_text),
            inspect.getsource(VideoDownloaderProvider),
        ]
    )
    for forbidden in ("spend_fixed_credit_info", "deduct_dynamic_credit", "refund_charged_credit", "update_user_credits", "LINK_IMPORT_PRICE_XU"):
        assert forbidden not in source


def test_video_downloader_temp_cleanup(tmp_path):
    temp_file = tmp_path / "toan-aas-temp.mp4"
    temp_file.write_bytes(b"video")
    removed = VideoDownloaderProvider.cleanup_temp_files([temp_file], enabled=True)
    assert removed == 1
    assert not temp_file.exists()


def test_video_downloader_public_guard_private_or_invalid():
    provider = VideoDownloaderProvider()
    private_detection = provider.detect_link("http://127.0.0.1/private/video.mp4")
    assert private_detection["ok"] is False
    assert private_detection["reason"] == "private_or_invalid"
    invalid_detection = provider.detect_link("not-a-public-link")
    assert invalid_detection["ok"] is False
    text = bot.video_downloader_guard_text(private_detection["reason"], "vi", private_detection)
    assert "công khai" in text
    assert "chưa trừ Xu" in text
    assert bot.VIDEO_DOWNLOADER_PUBLIC_ENABLED is False
