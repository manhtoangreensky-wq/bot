import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import bot
import local_worker


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.edited = None

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.edited = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup}
        return self.edited


def _video_state(user_id, token="preview-token"):
    pending = {
        "job_type": "video",
        "base_cost": 300,
        "duration_seconds": 18,
        "processing_type": "ai_text_to_video",
        "video_tier": "basic",
        "prompt": "Video giới thiệu sản phẩm sạch và rõ",
        "paid_preview_seen": False,
    }
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token] = dict(pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_confirm_token": token,
        "current_video_duration_seconds": 18,
        "current_video_processing_type": "ai_text_to_video",
        "pending_payload": dict(pending),
    })
    return pending


def _run_video_callback(monkeypatch, user_id, data, context=None):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = _Query(user_id, data)
    context = context or SimpleNamespace(bot=SimpleNamespace())
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), context))
    return query


def test_paid_video_preview_created_when_missing(monkeypatch):
    user_id = 992001
    token = "create-missing"
    bot.clear_video_addon_state(user_id)
    _video_state(user_id, token)
    captured = {}
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    monkeypatch.setattr(bot, "get_local_worker_job", lambda _job_id: {})

    def create_job(**kwargs):
        captured.update(kwargs)
        return 701

    monkeypatch.setattr(bot, "create_local_worker_job", create_job)
    query = _run_video_callback(monkeypatch, user_id, f"videoaddon|preview|{token}")

    assert captured["job_type"] == "paid_video_preview"
    assert captured["xu_cost"] == 0
    payload = json.loads(captured["input_file_id"])
    assert payload["preview_kind"] == "paid_video"
    assert 2 <= payload["preview_seconds"] <= 6
    assert bot.get_video_addon_state(user_id)["paid_preview_local_job_id"] == 701
    assert f"videoaddon|preview_status|{token}|701" in _callbacks(query.edited["reply_markup"])


def test_paid_video_no_fake_preview_file_id_required(monkeypatch):
    user_id = 992002
    token = "no-fake-file"
    pending = _video_state(user_id, token)
    assert "paid_preview_video_file_id" not in pending
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    monkeypatch.setattr(bot, "get_local_worker_job", lambda _job_id: {})
    monkeypatch.setattr(bot, "create_local_worker_job", lambda **_kwargs: 702)
    _run_video_callback(monkeypatch, user_id, f"videoaddon|preview|{token}")
    saved = bot.get_video_addon_state(user_id)
    assert saved["paid_preview_local_job_id"] == 702
    assert not saved.get("paid_preview_video_file_id")


def test_paid_video_missing_preview_does_not_dead_end(monkeypatch):
    user_id = 992003
    token = "worker-busy"
    _video_state(user_id, token)
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: False)
    monkeypatch.setattr(bot, "get_local_worker_job", lambda _job_id: {})
    query = _run_video_callback(monkeypatch, user_id, f"videoaddon|preview|{token}")
    callbacks = _callbacks(query.edited["reply_markup"])
    assert f"videoaddon|preview_locked|{token}" not in callbacks
    assert f"shopai|confirm|{token}" in callbacks
    assert "vfinal|menu" in callbacks
    assert "videoaddon|back" in callbacks
    assert "videoaddon|main" in callbacks


def test_paid_video_final_confirm_visible_after_real_preview(monkeypatch):
    user_id = 992004
    token = "worker-success"
    _video_state(user_id, token)
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    state = bot.get_video_addon_state(user_id)
    state["paid_preview_local_job_id"] = 703
    state["pending_payload"]["paid_preview_local_job_id"] = 703
    bot.set_video_addon_state(user_id, state)
    worker_payload = bot.video_paid_preview_worker_payload(user_id, user_id, state, token)
    job = {
        "id": 703,
        "user_id": str(user_id),
        "status": "succeeded",
        "output_file_id": "worker-generated-preview",
        "input_file_id": json.dumps(worker_payload, ensure_ascii=False),
    }
    monkeypatch.setattr(bot, "get_local_worker_job", lambda _job_id: dict(job))
    async def send_preview(*args, **kwargs):
        return True
    monkeypatch.setattr(bot, "send_video_paid_preview_artifact", send_preview)
    query = _run_video_callback(monkeypatch, user_id, f"videoaddon|preview_status|{token}|703")
    assert f"shopai|confirm|{token}" in _callbacks(query.edited["reply_markup"])
    saved = bot.get_video_addon_state(user_id)
    assert saved["paid_preview_seen"] is True
    assert saved["pending_payload"]["paid_preview_video_file_id"] == "worker-generated-preview"


def test_paid_video_worker_completion_unlocks_confirmation_state():
    user_id = 992006
    token = "worker-hook-success"
    _video_state(user_id, token)
    state = bot.get_video_addon_state(user_id)
    worker_payload = bot.video_paid_preview_worker_payload(user_id, user_id, state, token)
    previous = {"id": 705, "job_type": "paid_video_preview", "status": "running"}
    updated = {
        "id": 705,
        "job_type": "paid_video_preview",
        "status": "succeeded",
        "user_id": str(user_id),
        "output_file_id": "worker-hook-preview",
        "input_file_id": json.dumps(worker_payload, ensure_ascii=False),
    }
    bot.handle_paid_video_preview_worker_job_update(previous, updated)
    saved = bot.get_video_addon_state(user_id)
    assert saved["paid_preview_seen"] is True
    assert bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token]["paid_preview_seen"] is True
    assert bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token]["paid_preview_video_file_id"] == "worker-hook-preview"


def test_paid_video_stale_worker_job_cannot_unlock_new_order():
    user_id = 992007
    active_token = "active-order-token"
    _video_state(user_id, active_token)
    stale_payload = bot.video_paid_preview_worker_payload(user_id, user_id, bot.get_video_addon_state(user_id), "stale-order-token")
    bot.handle_paid_video_preview_worker_job_update(
        {"id": 707, "job_type": "paid_video_preview", "status": "running"},
        {
            "id": 707,
            "job_type": "paid_video_preview",
            "status": "succeeded",
            "user_id": str(user_id),
            "output_file_id": "stale-preview",
            "input_file_id": json.dumps(stale_payload, ensure_ascii=False),
        },
    )
    saved = bot.get_video_addon_state(user_id)
    assert not saved.get("paid_preview_seen")
    assert not saved.get("paid_preview_video_file_id")
    assert not bot.SHOPAIKEY_PENDING_CONFIRMATIONS[active_token].get("paid_preview_seen")


def test_paid_video_new_invoice_invalidates_old_preview(monkeypatch):
    user_id = 992008
    old_token = "old-invoice-token"
    bot.clear_video_addon_state(user_id)
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS[old_token] = {"job_type": "video", "base_cost": 300}
    state = bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_confirm_token": old_token,
        "paid_preview_seen": True,
        "paid_preview_video_file_id": "old-preview",
        "paid_preview_seconds": 6,
        "paid_preview_local_job_id": 700,
        "pending_payload": {
            "job_type": "video",
            "video_tier": "basic",
            "video_finalization_confirmed": True,
            "paid_preview_video_file_id": "old-preview",
            "paid_preview_seconds": 6,
            "paid_preview_local_job_id": 700,
        },
    })
    monkeypatch.setattr(bot, "get_user", lambda *_args, **_kwargs: (5000, None, None))
    monkeypatch.setattr(bot, "record_shopaikey_billing_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "set_shopaikey_pending_confirmation", lambda *_args, **_kwargs: "new-invoice-token")
    monkeypatch.setattr(bot, "active_package_item_for_user", lambda *_args, **_kwargs: None)
    query = _Query(user_id, "videoaddon|none")
    asyncio.run(bot.finalize_video_addon_confirmation(query, user_id, state, "vi"))
    saved = bot.get_video_addon_state(user_id)
    assert saved["paid_preview_seen"] is False
    assert "paid_preview_video_file_id" not in saved
    assert "paid_preview_local_job_id" not in saved
    assert "paid_preview_video_file_id" not in saved["pending_payload"]
    assert old_token not in bot.SHOPAIKEY_PENDING_CONFIRMATIONS


def test_paid_video_worker_sends_final_confirmation_buttons(monkeypatch, tmp_path):
    ffmpeg_path = tmp_path / "ffmpeg.exe"
    ffmpeg_path.write_bytes(b"stub")
    monkeypatch.setattr(local_worker, "LOCAL_FFMPEG_PATH", str(ffmpeg_path))
    captured = {}

    def run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"preview-mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def send(_chat_id, _path, _caption, reply_markup=None):
        captured["reply_markup"] = reply_markup
        return "telegram-worker-preview"

    def update(_job_id, status, error_short="", output_url="", output_file_id=""):
        captured["status"] = status
        captured["output_file_id"] = output_file_id

    monkeypatch.setattr(local_worker.subprocess, "run", run)
    monkeypatch.setattr(local_worker, "telegram_send_video", send)
    monkeypatch.setattr(local_worker, "update_job", update)
    payload = {
        "chat_id": "1",
        "user_id": "1",
        "confirm_token": "worker-button-token",
        "source_kind": "storyboard",
        "preview_seconds": 6,
        "width": 360,
        "height": 640,
        "caption": "Bản xem thử ngắn",
    }
    local_worker.run_paid_video_preview({"id": 706, "input_file_id": json.dumps(payload)})
    callbacks = [
        button["callback_data"]
        for row in captured["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert "shopai|confirm|worker-button-token" in callbacks
    assert captured["status"] == "succeeded"
    assert captured["output_file_id"] == "telegram-worker-preview"


def test_paid_video_preview_max_6_seconds():
    payload = bot.video_paid_preview_worker_payload(
        1,
        1,
        {"current_video_duration_seconds": 999, "pending_payload": {"duration_seconds": 999}},
        "tok",
    )
    assert payload["preview_seconds"] == 6
    command = local_worker.paid_video_preview_ffmpeg_command(payload, "", "preview.mp4")
    assert int(command[command.index("-t") + 1]) == 6
    assert "-an" in command


def test_paid_video_no_full_output_before_final_confirm(monkeypatch):
    user_id = 992005
    token = "no-full-before-confirm"
    _video_state(user_id, token)
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    monkeypatch.setattr(bot, "get_local_worker_job", lambda _job_id: {})
    monkeypatch.setattr(bot, "create_local_worker_job", lambda **kwargs: 704 if kwargs["xu_cost"] == 0 else 0)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Xu charged during preview")))
    query = _run_video_callback(monkeypatch, user_id, f"videoaddon|preview|{token}")
    callbacks = _callbacks(query.edited["reply_markup"])
    assert f"shopai|confirm|{token}" not in callbacks


class _VoiceMessage:
    def __init__(self, chat_id=1):
        self.chat_id = chat_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": str(text), **kwargs})
        return self.replies[-1]


class _VoiceQuery:
    def __init__(self, chat_id=1):
        self.message = _VoiceMessage(chat_id)


def _voice_profile(profile_id=1, status="pending_name", metadata=None, preview_ref=""):
    metadata = {
        "confirmation_sample_text": bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT,
        **(metadata or {}),
    }
    return {
        "id": profile_id,
        "user_id": "1",
        "display_name": "Giọng thử",
        "consent_status": "confirmed",
        "source_file_id": "voice-source",
        "source_file_ref": "voice-source",
        "preview_audio_ref": preview_ref,
        "provider_voice_id": "",
        "status": status,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


def _install_voice_store(monkeypatch, profile):
    store = dict(profile)

    def get_profile(_user_id, _profile_id):
        return dict(store)

    def update_profile(_user_id, _profile_id, **fields):
        store.update(fields)
        return True

    monkeypatch.setattr(bot, "get_user_voice_profile", get_profile)
    monkeypatch.setattr(bot, "update_user_voice_profile", update_profile)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {"day": "2026-06-18", "attempts": 0, "latest_at": None})
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "shopaikey_configured": True,
        "key4u_configured": False,
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
        "routes": ["shopaikey_minimax"],
    })
    return store


def _install_voice_provider_success(monkeypatch, calls):
    class TelegramFile:
        async def download_as_bytearray(self):
            return bytearray(b"voice-source")

    class TelegramBot:
        async def get_file(self, _file_id):
            return TelegramFile()

        async def send_audio(self, **_kwargs):
            calls["send"] += 1
            return SimpleNamespace(audio=SimpleNamespace(file_id="cached-preview-file"))

    async def upload(_audio):
        calls["upload"] += 1
        return "PASS", "uploaded", "", 200

    async def clone(_file_id, _voice_id):
        calls["clone"] += 1
        return "PASS", {"voice_id": "voice-id"}, "", 200

    async def tts(text, voice_id=""):
        calls["tts"] += 1
        calls["text"] = text
        return "PASS", b"preview-audio", "", 200

    async def cap(data, max_seconds):
        calls["cap_seconds"] = max_seconds
        return b"capped-preview-audio", "ok"

    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "shopaikey_configured": True,
        "key4u_configured": False,
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
        "routes": ["shopaikey_minimax"],
    })
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", upload)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", clone)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", tts)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", cap)
    return SimpleNamespace(bot=TelegramBot())


def test_voice_preview_idempotency_reuses_existing_preview(monkeypatch):
    profile = _voice_profile()
    key = bot.voice_preview_idempotency_key(1, profile, bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT)
    profile["metadata_json"] = json.dumps({
        "preview_key": key,
        "confirmation_sample_text": bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT,
    })
    profile["preview_audio_ref"] = "cached-preview-file"
    _install_voice_store(monkeypatch, profile)
    sent = {"count": 0}

    class TelegramBot:
        async def send_audio(self, **_kwargs):
            sent["count"] += 1

    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=TelegramBot()), 1, profile))
    assert sent["count"] == 1
    assert "dùng lại" in query.message.replies[-1]["text"]


def test_voice_preview_inflight_lock_blocks_duplicate_provider_call(monkeypatch):
    profile = _voice_profile(status="preview_generating")
    _install_voice_store(monkeypatch, profile)
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 1, profile))
    assert "đang tạo bản nghe thử" in query.message.replies[-1]["text"]


def test_voice_preview_cooldown_blocks_repeated_clicks(monkeypatch):
    profile = _voice_profile()
    _install_voice_store(monkeypatch, profile)
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {"day": "2026-06-18", "attempts": 1, "latest_at": datetime.now()})
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 1, profile))
    assert "giây" in query.message.replies[-1]["text"]


def test_voice_preview_daily_quota_blocks_provider_call(monkeypatch):
    profile = _voice_profile()
    _install_voice_store(monkeypatch, profile)
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {"day": "2026-06-18", "attempts": bot.VOICE_PREVIEW_FREE_PER_DAY, "latest_at": None})
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 1, profile))
    assert "hết lượt nghe thử miễn phí" in query.message.replies[-1]["text"]


def test_voice_preview_truncates_long_text():
    text = "Câu đầu tiên rất dài để thử giới hạn. " + ("nội dung tiếp theo " * 80)
    capped = bot.capped_voice_preview_text(text)
    assert len(capped) <= bot.VOICE_PREVIEW_MAX_CHARACTERS <= 160
    assert len(capped.split()) <= bot.VOICE_PREVIEW_MAX_WORDS


def test_voice_preview_max_6_seconds(monkeypatch):
    captured = {}
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def run(command, timeout=0):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"capped")
        return True, "ok"

    monkeypatch.setattr(bot, "run_ffmpeg_command", run)
    data, detail = asyncio.run(bot.cap_voice_preview_audio_bytes(b"audio", 99))
    assert data == b"capped"
    assert detail == "ok"
    assert int(captured["command"][captured["command"].index("-t") + 1]) == 6


def test_voice_preview_no_provider_call_before_guards_pass(monkeypatch):
    profile = _voice_profile(status="preview_generating")
    _install_voice_store(monkeypatch, profile)
    calls = {"provider": 0}

    async def forbidden(*args, **kwargs):
        calls["provider"] += 1
        raise AssertionError("provider called before guard")

    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", forbidden)
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 1, profile))
    assert calls["provider"] == 0


def test_voice_preview_usage_guard_fails_closed(monkeypatch):
    profile = _voice_profile()
    _install_voice_store(monkeypatch, profile)
    monkeypatch.setattr(bot, "voice_preview_usage_snapshot", lambda _uid, now=None: {"available": False, "attempts": 0, "latest_at": None})
    calls = {"provider": 0}

    async def forbidden(*args, **kwargs):
        calls["provider"] += 1
        raise AssertionError("provider called while usage guard unavailable")

    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", forbidden)
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 1, profile))
    assert calls["provider"] == 0
    assert "chưa kiểm tra được lượt nghe thử" in query.message.replies[-1]["text"]


def test_voice_preview_no_final_xu_deducted(monkeypatch):
    profile = _voice_profile()
    _install_voice_store(monkeypatch, profile)
    calls = {"upload": 0, "clone": 0, "tts": 0, "send": 0}
    context = _install_voice_provider_success(monkeypatch, calls)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Xu deducted")))
    asyncio.run(bot.create_minimax_voice_profile_preview(_VoiceQuery(), context, 1, profile))
    assert calls["upload"] == calls["clone"] == calls["tts"] == 1


def test_repeated_voice_preview_callback_single_provider_call(monkeypatch):
    profile = _voice_profile()
    store = _install_voice_store(monkeypatch, profile)
    calls = {"upload": 0, "clone": 0, "tts": 0, "send": 0}
    context = _install_voice_provider_success(monkeypatch, calls)
    query = _VoiceQuery()
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, 1, profile))
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, 1, profile))
    assert calls["upload"] == 1
    assert calls["clone"] == 1
    assert calls["tts"] == 1
    assert calls["send"] == 2
    assert store["status"] == "ready"


def test_no_payos_changes():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    block = source[source.index("def video_paid_preview_retry_keyboard"):source.index("def public_video_tier_keyboard")]
    assert "PAYOS" not in block.upper()
    assert "naptien" not in block.lower()


def test_no_db_destructive():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    block = source[source.index("def capped_voice_preview_text"):source.index("async def handle_music_quick_callback")]
    for term in ("DROP TABLE", "TRUNCATE", "DELETE FROM USERS", "UPDATE USERS SET CREDITS"):
        assert term not in block.upper()


def test_no_xu_before_final_confirm():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    handler = source[source.index("async def handle_video_addon_callback"):source.index("async def cmd_video_price_test")]
    preview = handler[handler.index('if action in {"preview", "preview_retry", "preview_status"}'):handler.index('if action == "back"')]
    assert "spend_fixed_credit_info" not in preview
    assert "deduct_dynamic_credit" not in preview
    voice = source[source.index("async def create_minimax_voice_profile_preview"):source.index("async def handle_music_quick_callback")]
    assert "spend_fixed_credit_info" not in voice


def test_public_copy_no_provider_vendor_names():
    texts = [
        bot.voice_preview_guard_message("inflight"),
        bot.voice_preview_guard_message("cooldown", 30),
        bot.voice_preview_guard_message("quota"),
        bot.video_paid_preview_unavailable_text({"current_video_duration_seconds": 30}, "vi"),
    ]
    for text in texts:
        lowered = text.lower()
        for term in ("provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "raw error"):
            assert term not in lowered
