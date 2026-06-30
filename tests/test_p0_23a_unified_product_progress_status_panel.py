import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot
from services import product_progress_status


FORBIDDEN_PUBLIC_WORDS = tuple(word.lower() for word in product_progress_status.PUBLIC_TECHNICAL_WORDS)


class CaptureMessage:
    def __init__(self):
        self.chat_id = 230001
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))


class CaptureQuery:
    def __init__(self, data="progress|status|music_bg|job123", user_id=230001):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage()
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.edits))


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _assert_common_panel(text, title):
    assert title in text
    assert "Trạng thái:" in text
    assert "Tiến độ:" in text
    assert "Mã xử lý:" in text
    assert "Các bước:" in text
    assert "Vui lòng không bấm lại nhiều lần." in text or "Anh/chị không cần bấm nhiều lần." in text


def _assert_no_public_technical_words(text):
    lowered = text.lower()
    for forbidden in FORBIDDEN_PUBLIC_WORDS:
        assert forbidden not in lowered


def test_product_progress_status_renders_common_panel():
    text = bot.product_progress_status_text("music_bg", "a23af65f", "generating_music")
    _assert_common_panel(text, "🎵 TOAN AAS đang tạo nhạc nền")
    assert "Tiến độ: 65%" in text
    assert "#A23AF65F" in text


def test_product_progress_status_update_button_no_reprocess(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("update status must not reprocess")

    monkeypatch.setattr(bot, "execute_engine", fail_async)
    monkeypatch.setattr(bot, "poll_music_suno_async_job", fail_async)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {"internal_job_id": job_id, "status": "processing", "progress_percent": 60})
    query = CaptureQuery("progress|status|music_bg|job123")
    update = SimpleNamespace(callback_query=query)
    asyncio.run(bot.handle_product_progress_callback(update, SimpleNamespace()))
    assert query.edits
    assert "TOAN AAS đang tạo nhạc nền" in query.edits[-1]["text"]


def test_product_progress_status_delivered_100_percent():
    text = bot.product_progress_status_text("music_song", "done1", "delivered", terminal_state="delivered")
    assert "Tiến độ: 100%" in text
    assert "Đã gửi file nhạc" in text


def test_product_progress_status_failed_clean_public_copy():
    text = product_progress_status.render_product_progress_panel(
        "video_ai_real",
        "fail1",
        "generating_video",
        terminal_state="failed_no_charge",
        public_note="provider API RuntimeError traceback",
    )
    assert "TOAN AAS chưa trừ Xu" in text
    _assert_no_public_technical_words(text)


def test_product_progress_status_no_technical_words():
    text = "\n".join([
        bot.product_progress_status_text("music_bg", "m1", "generating_music"),
        bot.product_progress_status_text("video_ai_real", "v1", "generating_video"),
        bot.product_progress_status_text("subdub", "s1", "muxing_video"),
    ])
    _assert_no_public_technical_words(text)


def test_music_background_uses_progress_panel():
    text = bot.product_progress_status_text("music_bg", "mbg1", "generating_music")
    _assert_common_panel(text, "🎵 TOAN AAS đang tạo nhạc nền")
    assert "Tạo nhạc nền" in text
    callbacks = _callbacks(bot.product_progress_status_keyboard("music_bg", "mbg1"))
    assert "progress|status|music_bg|mbg1" in callbacks


def test_music_song_uses_progress_panel():
    text = bot.product_progress_status_text("music_song", "msong1", "generating_song")
    _assert_common_panel(text, "🎙 TOAN AAS đang tạo bài hát")
    assert "Tạo bài hát" in text


def test_music_status_does_not_touch_suno_engine(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("status panel must not poll music engine")

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fail_async)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {"internal_job_id": job_id, "status": "submitted"})
    query = CaptureQuery("progress|status|music_song|music-job")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    assert "TOAN AAS đang tạo bài hát" in query.edits[-1]["text"]


def test_music_update_status_does_not_generate_again(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("status update must not create music again")

    monkeypatch.setattr(bot, "execute_engine", fail_async)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {"internal_job_id": job_id, "status": "processing"})
    query = CaptureQuery("progress|status|music_bg|music-job")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits


def test_video_trend_uses_progress_panel():
    text = bot.video_product_progress_text("video_trend", "trend1", "rendering_video")
    _assert_common_panel(text, "🎬 TOAN AAS đang xử lý video trend")
    assert "Tạo video" in text


def test_script_to_video_uses_progress_panel():
    text = bot.video_product_progress_text("script_to_video", "script1", "rendering_scenes")
    _assert_common_panel(text, "🎬 TOAN AAS đang dựng video từ kịch bản")


def test_frame_video_uses_progress_panel():
    text = bot.frame_video_job_status_text({"job_id": "frame1", "status": "running", "image_count": 3})
    _assert_common_panel(text, "🎞 TOAN AAS đang ghép ảnh thành video")
    assert "Số ảnh" in text


def test_multiscene_video_uses_progress_panel():
    text = bot.video_product_progress_text("multiscene_video", "multi1", "rendering_scenes")
    _assert_common_panel(text, "🎬 TOAN AAS đang dựng video nhiều cảnh")


def test_video_ai_real_uses_progress_panel():
    text = bot.video_product_progress_text("video_ai_real", "real1", "generating_video")
    _assert_common_panel(text, "🎥 TOAN AAS đang tạo video AI")


def test_video_status_does_not_start_new_render(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("status update must not start render")

    monkeypatch.setattr(bot, "execute_engine", fail_async)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: {"internal_job_id": job_id, "status": "processing", "progress_percent": 55})
    query = CaptureQuery("progress|status|multiscene_video|video-job")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    assert "TOAN AAS đang dựng video nhiều cảnh" in query.edits[-1]["text"]


def test_addon_voice_render_uses_progress_panel():
    text = bot.addon_product_progress_text("addon_voice", "voice1", "rendering_voice")
    _assert_common_panel(text, "🎙 TOAN AAS đang tạo giọng đọc cho video")


def test_addon_music_render_uses_progress_panel():
    text = bot.addon_product_progress_text("addon_music", "music1", "rendering_music")
    _assert_common_panel(text, "🎵 TOAN AAS đang tạo nhạc cho video")


def test_addon_subtitle_render_uses_progress_panel():
    text = bot.addon_product_progress_text("addon_subtitle", "sub1", "creating_subtitles")
    _assert_common_panel(text, "💬 TOAN AAS đang tạo phụ đề cho video")


def test_addon_logo_config_only_does_not_show_processing_panel():
    text = bot.addon_logo_config_saved_text("vi")
    assert text == "✅ Đã lưu cấu hình."
    assert "Các bước:" not in text
    assert "Tiến độ:" not in text


def test_subdub_existing_progress_panel_preserved():
    text = bot.subdub_progress_text("generating_voice", "abc123", "vi")
    assert "TOAN AAS đang xử lý video" in text
    assert "Tiến độ: 65%" in text
    assert "Tạo giọng lồng tiếng" in text
    assert "#ABC123" in text
    callbacks = _callbacks(bot.subdub_progress_keyboard("job123", "vi"))
    assert "videodub|subdub_status|job123" in callbacks


def test_subdub_progress_helper_no_engine_regression():
    source = inspect.getsource(bot.subdub_progress_text)
    assert "product_progress_status_text" in source
    assert "run_ffmpeg_command" not in source


def test_progress_no_payos_wallet_touch():
    source = Path(product_progress_status.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("payos", "wallet", "topup", "spend_fixed_credit", "refund_charged_credit"):
        assert forbidden not in source


def test_progress_no_provider_call_on_update():
    source = inspect.getsource(bot.handle_product_progress_callback)
    for forbidden in ("execute_engine", "poll_music_suno_async_job", "create_music_suno_async_job", "video_b14_start"):
        assert forbidden not in source


def test_progress_callback_has_product_context():
    callback = product_progress_status.product_progress_update_callback("music_bg", "job123")
    assert callback == "progress|status|music_bg|job123"


def test_progress_terminal_state_single():
    assert product_progress_status.product_progress_single_terminal_state("delivered", "failed_no_charge") == "delivered"
    assert product_progress_status.product_progress_single_terminal_state("", "failed_no_charge") == "failed_no_charge"
