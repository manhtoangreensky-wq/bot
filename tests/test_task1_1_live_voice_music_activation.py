import asyncio
import inspect
import json
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class _Message:
    chat_id = 88011

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.replies.append({"text": str(text), "reply_markup": reply_markup, "parse_mode": parse_mode, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class _Query:
    def __init__(self):
        self.message = _Message()


def _profile(status="pending_confirm", profile_id=11):
    return {
        "id": profile_id,
        "user_id": "42",
        "display_name": "Giọng live",
        "consent_status": "confirmed",
        "source_file_id": "telegram-source",
        "source_file_ref": "telegram-source",
        "preview_audio_ref": "",
        "provider_voice_id": "",
        "status": status,
        "metadata_json": json.dumps(
            {"confirmation_sample_text": bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT},
            ensure_ascii=False,
        ),
    }


def _install_voice_store(monkeypatch, profile):
    store = dict(profile)
    statuses = []
    monkeypatch.setattr(bot, "get_member_profile", lambda *_args, **_kwargs: {"tier": "silver"})

    def get_profile(_user_id, _profile_id):
        return dict(store)

    def update_profile(_user_id, _profile_id, **fields):
        if "status" in fields:
            statuses.append(fields["status"])
        store.update(fields)
        return True

    monkeypatch.setattr(bot, "get_user_voice_profile", get_profile)
    monkeypatch.setattr(bot, "update_user_voice_profile", update_profile)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {"day": "2026-06-19", "attempts": 0, "latest_at": None})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    return store, statuses


def _install_voice_provider(monkeypatch, calls):
    class TelegramFile:
        async def download_as_bytearray(self):
            return bytearray(b"voice-source-bytes")

    class TelegramBot:
        async def get_file(self, _file_id):
            return TelegramFile()

        async def send_audio(self, **_kwargs):
            calls["send_audio"] = calls.get("send_audio", 0) + 1
            return SimpleNamespace(audio=SimpleNamespace(file_id="telegram-demo-file"))

    async def upload(_audio):
        calls["upload"] = calls.get("upload", 0) + 1
        return "PASS", "provider-file-id", "ok", 200

    async def clone(_file_id, _voice_id):
        calls["clone"] = calls.get("clone", 0) + 1
        return "PASS", {"voice_id": "voice-live-123"}, "ok", 200

    async def tts(_text, voice_id="", voice_style=""):
        calls["tts"] = calls.get("tts", 0) + 1
        calls["tts_voice_id"] = voice_id
        return "PASS", b"preview-audio-bytes", "ok", 200

    async def cap(data, max_seconds):
        calls["cap_seconds"] = max_seconds
        return bytes(data), "ok"

    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "shopaikey_configured": True,
        "key4u_configured": False,
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
        "routes": ["shopaikey_minimax"],
    })
    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", upload)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", clone)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", tts)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", cap)
    return SimpleNamespace(bot=TelegramBot())


def test_voice_confirm_transitions_pending_to_processing(monkeypatch):
    profile = _profile()
    store, statuses = _install_voice_store(monkeypatch, profile)
    context = _install_voice_provider(monkeypatch, {})

    asyncio.run(bot.create_minimax_voice_profile_preview(_Query(), context, 42, profile))

    assert "processing" in statuses
    assert store["status"] == "ready"
    assert store["provider_voice_id"] == "voice-live-123"


def test_voice_confirm_calls_clone_provider(monkeypatch):
    profile = _profile()
    _install_voice_store(monkeypatch, profile)
    calls = {}
    context = _install_voice_provider(monkeypatch, calls)

    asyncio.run(bot.create_minimax_voice_profile_preview(_Query(), context, 42, profile))

    assert calls["upload"] == 1
    assert calls["clone"] == 1
    assert calls["tts_voice_id"] == "voice-live-123"


def test_voice_ready_requires_provider_voice_id():
    assert bot.voice_profile_can_generate_tts({"status": "ready", "provider_voice_id": "voice-1"})
    assert not bot.voice_profile_can_generate_tts({"status": "ready", "provider_voice_id": ""})


def test_voice_failed_not_pending_confirm(monkeypatch):
    profile = _profile()
    store, _statuses = _install_voice_store(monkeypatch, profile)
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": False,
        "public_enabled": False,
        "missing_env": ["ShopAIKey MiniMax upload+clone+TTS"],
        "reason": "Missing ShopAIKey MiniMax upload+clone+TTS",
        "tts_smoke": "NOT_TESTED",
        "clone_smoke": "NOT_TESTED",
        "routes": [],
    })

    query = _Query()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 42, profile))

    assert store["status"] == "failed_provider_not_ready"
    assert store["status"] != "pending_confirm"
    assert bot.VOICE_CLONE_PROVIDER_NOT_READY_PUBLIC_VI in query.message.replies[-1]["text"]


def test_voice_vault_ready_buttons():
    labels = _labels(bot.voice_profile_actions_keyboard(
        7,
        "vi",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        {"id": 7, "status": "ready", "provider_voice_id": "voice-7", "preview_audio_ref": "demo-file"},
    ))
    for label in ["▶️ Nghe demo", "✍️ Đọc thử", "⭐ Đặt mặc định", "🎬 Dùng cho video", "⬇️ Tải demo"]:
        assert label in labels


def test_voice_vault_pending_buttons_no_download_primary(monkeypatch):
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {"public_enabled": False})
    labels = _labels(bot.voice_profile_actions_keyboard(
        8,
        "vi",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        {"id": 8, "status": "failed_provider_not_ready", "provider_voice_id": "", "preview_audio_ref": ""},
    ))
    assert "🔁 Tạo/nghe thử lại" in labels
    assert "✏️ Đổi tên" in labels
    assert "🗑 Xóa" in labels
    assert not any("Tải" in label for label in labels)


def test_preview_quota_exhausted_offers_full_generation():
    labels = _labels(bot.voice_preview_quota_exhausted_keyboard(9, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.voice_preview_quota_exhausted_keyboard(9, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert ["✅ Tạo bản đầy đủ", "✏️ Sửa nội dung"] == labels[:2]
    assert "music_quick|showroom|voice_clone_full:9" in callbacks


def test_full_generation_available_after_preview_quota(monkeypatch):
    profile = _profile(profile_id=12)
    store, _statuses = _install_voice_store(monkeypatch, profile)
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {
        "day": "2026-06-19",
        "attempts": bot.VOICE_PREVIEW_FREE_PER_DAY,
        "latest_at": None,
    })
    context = _install_voice_provider(monkeypatch, {})

    asyncio.run(bot.create_minimax_voice_profile_preview(_Query(), context, 42, profile, full_generation=True))

    assert store["status"] == "ready"
    assert store["provider_voice_id"] == "voice-live-123"


def test_music_song_lyrics_flow_shows_three_option_buttons():
    result = {"song_product": "full", "music_ai_kind": "lyrics"}
    labels = _labels(bot.music_prompt_result_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, result))
    assert labels == ["1️⃣ Chọn PA1", "2️⃣ Chọn PA2", "3️⃣ Chọn PA3", "🔁 Gợi ý lại", "✏️ Sửa chủ đề", "⬅️ Quay lại"]


def test_song_seconds_asks_topic_genre_mood_vocal():
    duration_callbacks = _callbacks(bot.music_song_duration_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    genre_labels = _labels(bot.music_song_options_keyboard("genre", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    mood_labels = _labels(bot.music_song_options_keyboard("mood", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    vocal_labels = _labels(bot.music_song_options_keyboard("vocal", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "music_quick|showroom|song_duration_18" in duration_callbacks
    assert "Bạn muốn bài hát nói về điều gì" in bot.music_song_step_text("topic", {"song_product": "seconds"}, "vi")
    assert {"Pop", "Ballad", "Rap", "EDM", "Acoustic", "Bolero", "Tự nhập thể loại"}.issubset(set(genre_labels))
    assert {"Vui", "Buồn", "Truyền cảm hứng", "Sang trọng", "Hài hước", "Tự nhập cảm xúc"}.issubset(set(mood_labels))
    assert {"Giọng nam", "Giọng nữ", "Song ca", "Không lời", "Tự nhập giọng hát"}.issubset(set(vocal_labels))


def test_song_seconds_generates_three_options_before_invoice():
    result = {"song_product": "seconds", "music_ai_kind": "lyrics"}
    suggestions = bot.music_prompt_suggestions("Tạo đoạn có lời 18 giây về thương hiệu", 0, "vi", "lyrics")
    labels = _labels(bot.music_prompt_result_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, result))
    assert len(suggestions) == 3
    assert "1️⃣ Chọn PA1" in labels
    assert "✅ Tạo bài hát" not in labels
    assert "▶️ Nghe thử" not in labels


def test_music_song_options_include_lyric_direction():
    text = bot.music_prompt_suggestions_text("Tạo một bài hát có lời về thương hiệu", 0, "vi", "lyrics")
    assert "Hướng lời" in text
    assert "Prompt" in text


def test_song_option_selected_then_invoice():
    result = {"song_product": "seconds", "guided_duration_seconds": 18, "selected_prompt": "bài hát có lời"}
    labels = _labels(bot.music_ai_preview_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    text = bot.music_ai_preview_text(result, "vi")
    assert "Thời lượng bản đầy đủ: <b>18 giây</b>" in text
    assert "Preview: <b>12 giây đầu</b>" in text
    assert "✅ Dùng bản đầy đủ" in labels


def test_music_song_select_option_shows_confirmation_price():
    result = {"song_product": "half", "guided_duration_seconds": 60, "selected_prompt": "bài hát có lời"}
    text = bot.music_ai_preview_text(result, "vi")
    labels = _labels(bot.music_ai_preview_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    assert "Nghe thử bài hát có lời AI" in text
    assert "Bản đầy đủ bài hát có lời AI: <b>800 Xu</b>" in text
    assert "1 lần trong 15 ngày" in text
    assert "Thời lượng bản đầy đủ" not in text
    assert "▶️ Nghe thử 12 giây" in labels
    assert "✅ Dùng bản đầy đủ 800 Xu" in labels


def test_music_song_half_full_provider_prompt_structure():
    full_prompt = bot.music_provider_prompt_for_result({"song_product": "full", "selected_prompt": "bài hát"}, preview=True)
    half_prompt = bot.music_provider_prompt_for_result({"song_product": "half", "selected_prompt": "bài hát"}, preview=True)
    assert "intro, verse, chorus, bridge and outro" in full_prompt
    assert "verified short song" not in half_prompt
    assert "clip only the first 12 seconds" in full_prompt


def test_song_preview_guard_reports_provider_not_ready(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": False,
        "public_enabled": False,
        "missing_env": ["KEY4U_SUNO_CREATE_ENDPOINT"],
        "reason": "Missing KEY4U_SUNO_CREATE_ENDPOINT",
    })
    result = asyncio.run(bot.submit_music_generation_job(
        {"song_product": "seconds", "guided_duration_seconds": 15, "selected_prompt": "lyrics prompt"},
        preview=True,
    ))
    assert result["status"] == "NOT_READY"
    assert "KEY4U_SUNO_CREATE_ENDPOINT" in result["detail"]


def test_song_preview_calls_provider_when_ready(monkeypatch):
    captured = {}

    class Key4U:
        async def suno_create(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": "preview-task", "http_status": 200}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Key4U())
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "full_result_ok": True,
        "cost_gate_ok": True,
        "preferred_provider": "key4u_suno",
        "providers": {"key4u_suno": {"configured": True, "smoke": "PASS"}},
    })
    result = asyncio.run(bot.submit_music_generation_job(
        {"song_product": "seconds", "guided_duration_seconds": 60, "selected_prompt": "lyrics prompt"},
        preview=True,
    ))
    assert result["ok"] is True
    assert captured["duration_seconds"] == 60
    assert "clip only the first 12 seconds" in captured["prompt"]


def test_song_full_create_calls_provider_when_ready(monkeypatch):
    captured = {}

    class Key4U:
        async def suno_create(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": "full-task", "http_status": 200}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Key4U())
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "full_result_ok": True,
        "cost_gate_ok": True,
        "preferred_provider": "key4u_suno",
        "providers": {"key4u_suno": {"configured": True, "smoke": "PASS"}},
    })
    result = asyncio.run(bot.submit_music_generation_job(
        {"song_product": "full", "guided_duration_seconds": 120, "selected_prompt": "lyrics prompt"},
        preview=False,
    ))
    assert result["ok"] is True
    assert captured["duration_seconds"] == 120
    assert captured["instrumental"] is False


def test_music_provider_status_has_submit_fetch_download():
    status = bot.music_status_text()
    assert "Last submit smoke" in status
    assert "Last fetch smoke" in status
    assert "Last download smoke" in status
    assert "Last sanitized error" in status


def test_music_provider_not_ready_reason_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": False,
        "public_enabled": False,
        "missing_env": ["SHOPAIKEY_MUSIC_ENDPOINT"],
        "reason": "Missing SHOPAIKEY_MUSIC_ENDPOINT",
    })
    result = asyncio.run(bot.submit_music_generation_job(
        {"song_product": "seconds", "guided_duration_seconds": 15, "selected_prompt": "lyrics prompt"},
        preview=True,
    ))
    public_guard = bot.music_ai_public_guard_text("vi").lower()
    assert "SHOPAIKEY_MUSIC_ENDPOINT" in result["detail"]
    assert "shopaikey" not in public_guard
    assert "provider" not in public_guard


def test_no_provider_terms_in_public_voice_music_guards():
    surfaces = "\n".join([
        bot.voice_clone_public_guard_text("vi"),
        bot.voice_clone_provider_not_ready_public_text("vi"),
        bot.music_ai_public_guard_text("vi"),
    ]).lower()
    for term in ("provider", "api", "key4u", "shopaikey", "minimax", "suno", "env", "ready=false"):
        assert term not in surfaces
