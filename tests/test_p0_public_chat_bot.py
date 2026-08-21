"""Source-level contract for the narrow Telegram public-chat wiring.

The monolithic bot module is intentionally not imported here: importing it
starts a large legacy dependency graph.  These assertions protect routing
order and menu/callback ownership without making Telegram or provider calls.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace

import pytest

from services import public_chat_media


BOT_SOURCE = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(start: str, end: str) -> str:
    begin = BOT_SOURCE.index(start)
    finish = BOT_SOURCE.index(end, begin)
    return BOT_SOURCE[begin:finish]


def _public_chat_attachment_handler(calls: dict[str, int] | None = None):
    async def handled(*_args, **kwargs):
        if calls is not None:
            calls["runtime_delegation"] += 1
            calls["runtime_kwargs"] = kwargs
        return True

    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": object,
        "InlineKeyboardMarkup": object,
        "Path": Path,
        "Update": object,
        "ensure_user_modes": lambda _uid: {"chat_mode": "normal"},
        "handle_public_chat_text": handled,
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        "normalize_chat_tier": lambda value: value,
        "os": os,
        "public_chat_media": public_chat_media,
        "tempfile": tempfile,
    }
    exec(
        _function_source("async def handle_public_chat_attachment", "def main_menu_keyboard"),
        namespace,
    )
    return namespace["handle_public_chat_attachment"]


def _public_chat_sender(store, chunks):
    namespace = {
        "public_chat_runtime": SimpleNamespace(
            split_public_chat_text=lambda _text: list(chunks)
        ),
        "public_chat_store": store,
    }
    exec(
        _function_source("async def send_public_chat_text", "async def handle_public_chat_text"),
        namespace,
    )
    return namespace["send_public_chat_text"]


def _assert_public_chat_follows_every_specialized_handler(
    source: str,
    *,
    generic_markers: tuple[str, ...],
) -> list[str]:
    fallback = "await handle_public_chat_attachment(update, context)"
    fallback_index = source.index(fallback)
    specialized_calls = [
        (match.group(1), match.start())
        for match in re.finditer(r"await (handle_[a-z0-9_]+)\(", source)
        if match.group(1) != "handle_public_chat_attachment"
    ]
    assert specialized_calls
    late_handlers = [name for name, call_index in specialized_calls if call_index > fallback_index]
    assert late_handlers == []
    for generic_marker in generic_markers:
        assert fallback_index < source.index(generic_marker)
    return [name for name, _call_index in specialized_calls]


def test_public_chat_services_are_initialized_without_replacing_legacy_db_logic():
    assert "from services import public_chat_media, public_chat_runtime, public_chat_store" in BOT_SOURCE
    init_source = _function_source("def init_db():", "def now_text")
    assert "public_chat_store.ensure_schema(conn)" in init_source


def test_public_chat_menu_puts_free_first_and_pro_next_to_account():
    assert '[InlineKeyboardButton("🆓 Công cụ miễn phí", callback_data="freehub|main")]' in BOT_SOURCE
    assert 'InlineKeyboardButton(f"💎 Chat Pro • {public_chat_runtime.CHAT_PRO_RATE_LABEL}", callback_data="menu|chat_pro")' in BOT_SOURCE
    assert 'InlineKeyboardButton("👤 Tài khoản", callback_data="menu|main_profile")' in BOT_SOURCE
    assert 'toggle_action = "menu|chat_pro_off" if pro else "menu|chat_pro_on"' in BOT_SOURCE
    assert 'if action in {"chat_pro_on", "chat_pro_off", "chat_pro_toggle"}:' in BOT_SOURCE
    assert "resolve_public_chat_mode_action(action, current)" in BOT_SOURCE
    assert 'if action == "chat_free":' in BOT_SOURCE


def test_public_chat_runtime_copy_has_one_price_authority_and_no_legacy_fixed_price():
    assert "Chat Pro • 4.5/22.5 Xu/1K" not in BOT_SOURCE
    assert BOT_SOURCE.count('f"💎 Chat Pro • {public_chat_runtime.CHAT_PRO_RATE_LABEL}"') == 4

    visible_sections = (
        _function_source("def public_chat_menu_text", "def public_chat_menu_keyboard"),
        _function_source("def chat_pro_usage_text", "def build_chat_pro_prompt"),
        _function_source("async def cmd_mode", "async def set_chat_mode_command"),
        _function_source("async def set_chat_mode_command", "async def cmd_chat_pro_on"),
        _function_source("async def cmd_models", "async def cmd_payos_test_plan"),
    )
    for source in visible_sections:
        assert "public_chat_runtime.CHAT_PRO_RATE_LABEL" in source
        assert "CHAT_COST_PRO" not in source
        assert "CHAT_COST_DEEP_BASE" not in source
    combined = "\n".join(visible_sections)
    assert "20 câu trả lời thành công/ngày Việt Nam" in combined
    assert "usage thực tế" in combined
    assert "không giới hạn" in combined
    assert "Owner/Admin" in combined


def test_public_chat_exposes_only_free_and_pro_modes():
    pro = _function_source("async def cmd_chat_pro(", "async def run_one_shot_chat_command")
    assert "handle_public_chat_text" in pro
    assert "Chat Deep" not in BOT_SOURCE
    assert "/chat_deep" not in BOT_SOURCE
    assert 'CommandHandler("chat_deep' not in BOT_SOURCE
    assert 'mode = "pro" if raw_mode in {"pro", "deep"} else "normal"' in BOT_SOURCE


def test_ordinary_text_public_chat_is_last_resort_after_protected_owners():
    source = _function_source("async def handle_message", "# ─── FASTAPI + LIFESPAN")
    fallback = "if not detected_video_url:\n        return await handle_public_chat_text(update, context)"
    assert fallback in source
    fallback_index = source.index(fallback)
    for marker in (
        "handle_support_pending_input",
        "pending_text_owner_active",
        "handle_cskh_continuity_message",
        "handle_support_persona_message",
        "handle_aichat_message",
    ):
        assert source.index(marker) < fallback_index
    assert fallback_index < source.index("route = {\"action\": \"download\"", fallback_index)


@pytest.mark.parametrize(
    ("start", "end", "generic_markers", "required_handler_counts"),
    [
        (
            "async def handle_photo",
            "async def handle_translation_media_pending_upload",
            ("image_upload_outside_flow_text",),
            {"handle_developing_video_pending_image": 1, "handle_frame_video_photo": 2},
        ),
        (
            "async def handle_document_cache_only",
            "async def handle_caption_admin_tool_test_media",
            ('if update.effective_user and getattr(update.message, "document", None):',),
            {},
        ),
        (
            "async def handle_media(",
            "VIDEO_DUBBING_TTL_SECONDS",
            ("media_kind = cache_recent_media_state(update)", "remember_last_media(update)"),
            {"handle_video_finalization_pending_media": 1},
        ),
        (
            "async def handle_media_cache_only",
            "async def handle_feedback_pending_text",
            ("media_kind = cache_recent_media_state(update)", "remember_last_media(update)"),
            {},
        ),
    ],
    ids=("photo", "document", "media", "media-cache"),
)
def test_attachments_enter_public_chat_only_after_specialized_handlers(
    start,
    end,
    generic_markers,
    required_handler_counts,
):
    handlers = _assert_public_chat_follows_every_specialized_handler(
        _function_source(start, end),
        generic_markers=generic_markers,
    )
    for handler, expected_count in required_handler_counts.items():
        assert handlers.count(handler) == expected_count


def test_public_chat_does_not_reuse_legacy_fixed_chat_quota_authority():
    source = _function_source("async def handle_public_chat_text", "def main_menu_keyboard")
    assert "run_public_chat_request" in source
    assert "consume_free_chat" not in source
    assert "spend_fixed_credit_info" not in source


def test_public_chat_delivery_resumes_at_cursor_and_checkpoints_each_sent_chunk():
    advances = []

    class Store:
        @staticmethod
        def advance_public_chat_delivery(conn, request_id, *, next_cursor, total_chunks):
            advances.append((conn, request_id, next_cursor, total_chunks))
            return {"updated": True, "delivered": next_cursor == total_chunks}

    class Connection:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

    class Target:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text):
            self.sent.append(text)

    conn = Connection()
    target = Target()
    sender = _public_chat_sender(Store, ("one", "two", "three"))

    asyncio.run(
        sender(
            target,
            "ignored",
            "footer",
            conn=conn,
            request_id="request-1",
            start_index=1,
        )
    )

    assert target.sent == ["two", "three\n\nfooter"]
    assert advances == [
        (conn, "request-1", 2, 3),
        (conn, "request-1", 3, 3),
    ]
    assert conn.commits == 2


def test_public_chat_delivery_does_not_advance_failed_chunk():
    advances = []

    class Store:
        @staticmethod
        def advance_public_chat_delivery(conn, request_id, *, next_cursor, total_chunks):
            advances.append((request_id, next_cursor, total_chunks))
            return {"updated": True, "delivered": next_cursor == total_chunks}

    class Connection:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

    class Target:
        def __init__(self):
            self.calls = 0

        async def reply_text(self, _text):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("telegram delivery failed")

    conn = Connection()
    sender = _public_chat_sender(Store, ("one", "two", "three"))

    with pytest.raises(RuntimeError, match="telegram delivery failed"):
        asyncio.run(
            sender(
                Target(),
                "ignored",
                conn=conn,
                request_id="request-2",
                start_index=0,
            )
        )

    assert advances == [("request-2", 1, 3)]
    assert conn.commits == 1


def test_public_chat_delivery_stops_when_checkpoint_is_not_confirmed():
    class Store:
        @staticmethod
        def advance_public_chat_delivery(*_args, **_kwargs):
            return {"updated": False, "delivered": False, "reason": "missing"}

    class Connection:
        def commit(self):
            return None

    class Target:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text):
            self.sent.append(text)

    target = Target()
    sender = _public_chat_sender(Store, ("one", "two"))

    with pytest.raises(RuntimeError, match="delivery checkpoint failed"):
        asyncio.run(
            sender(
                target,
                "ignored",
                conn=Connection(),
                request_id="request-3",
            )
        )

    assert target.sent == ["one"]


def test_public_chat_flushes_pending_delivery_before_a_new_provider_request():
    source = _function_source("async def handle_public_chat_text", "async def handle_public_chat_attachment")
    pending_index = source.index("load_pending_public_chat_delivery")
    provider_index = source.index("run_public_chat_request")
    assert pending_index < provider_index
    assert "delivery_cursor" in source
    assert "source_message_id" in source


def test_text_attachment_rejects_actual_oversize_after_download():
    limit = 1 * 1024 * 1024
    calls = {"get_file": 0, "download": 0, "runtime_delegation": 0}
    replies = []

    class TelegramFile:
        async def download_to_drive(self, *, custom_path):
            calls["download"] += 1
            Path(custom_path).write_bytes(b"x" * (limit + 1))

    class Bot:
        async def get_file(self, _file_id):
            calls["get_file"] += 1
            return TelegramFile()

    async def reply_text(text, **_kwargs):
        replies.append(text)

    media = SimpleNamespace(
        file_id="telegram-file-id",
        file_size=100,
        mime_type="text/plain",
        file_name="notes.txt",
        duration=0,
    )
    message = SimpleNamespace(
        photo=None,
        voice=None,
        audio=None,
        video=None,
        document=media,
        caption="Tóm tắt file",
        reply_text=reply_text,
    )
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))

    handled = asyncio.run(
        _public_chat_attachment_handler(calls)(update, SimpleNamespace(bot=Bot()))
    )

    assert handled is True
    assert calls["get_file"] == 1
    assert calls["download"] == 1
    assert calls["runtime_delegation"] == 0
    assert replies and "không đọc được file" in replies[-1].casefold()


def test_text_attachment_creation_words_in_file_do_not_override_caption_intent():
    payload = "Tạo ảnh sản phẩm ở phần nội dung tài liệu".encode("utf-8")
    calls = {"get_file": 0, "download": 0, "runtime_delegation": 0}

    class TelegramFile:
        async def download_to_drive(self, *, custom_path):
            calls["download"] += 1
            Path(custom_path).write_bytes(payload)

    class Bot:
        async def get_file(self, _file_id):
            calls["get_file"] += 1
            return TelegramFile()

    async def reply_text(_text, **_kwargs):
        return None

    media = SimpleNamespace(
        file_id="telegram-file-id",
        file_size=len(payload),
        mime_type="text/plain",
        file_name="notes.txt",
        duration=0,
    )
    message = SimpleNamespace(
        photo=None,
        voice=None,
        audio=None,
        video=None,
        document=media,
        caption="Hãy tóm tắt tài liệu này",
        reply_text=reply_text,
    )
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))

    handled = asyncio.run(
        _public_chat_attachment_handler(calls)(update, SimpleNamespace(bot=Bot()))
    )

    assert handled is True
    assert calls["runtime_delegation"] == 1
    assert calls["runtime_kwargs"]["creation_intent_override"] == message.caption


@pytest.mark.parametrize(
    ("slot", "mime_type", "file_name", "limit"),
    [
        ("document", "text/plain", "notes.txt", 1 * 1024 * 1024),
        ("document", "application/octet-stream", "notes.txt", 1 * 1024 * 1024),
        ("photo", "image/jpeg", "photo.jpg", public_chat_media.PUBLIC_ATTACHMENT_LIMITS["image"]),
        ("audio", "audio/mpeg", "audio.mp3", public_chat_media.PUBLIC_ATTACHMENT_LIMITS["audio"]),
        ("video", "video/mp4", "video.mp4", public_chat_media.PUBLIC_ATTACHMENT_LIMITS["video"]),
        ("document", "application/pdf", "document.pdf", public_chat_media.PUBLIC_ATTACHMENT_LIMITS["pdf"]),
    ],
    ids=("text-mime", "text-suffix", "image", "audio", "video", "pdf"),
)
def test_public_chat_rejects_declared_oversize_before_telegram_download(slot, mime_type, file_name, limit):
    calls = {"get_file": 0, "download": 0, "runtime_delegation": 0}
    replies: list[str] = []

    class TelegramFile:
        async def download_to_drive(self, *, custom_path):
            calls["download"] += 1
            Path(custom_path).write_bytes(b"oversize")

    class Bot:
        async def get_file(self, _file_id):
            calls["get_file"] += 1
            return TelegramFile()

    async def reply_text(text, **_kwargs):
        replies.append(text)

    media = SimpleNamespace(
        file_id="telegram-file-id",
        file_size=limit + 1,
        mime_type=mime_type,
        file_name=file_name,
        duration=1,
    )
    message = SimpleNamespace(
        photo=None,
        voice=None,
        audio=None,
        video=None,
        document=None,
        caption="Summarize this attachment",
        reply_text=reply_text,
    )
    setattr(message, slot, [media] if slot == "photo" else media)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(bot=Bot())

    handled = asyncio.run(_public_chat_attachment_handler(calls)(update, context))

    assert handled is True
    assert calls == {"get_file": 0, "download": 0, "runtime_delegation": 0}
    assert replies and "chưa tải file" in replies[-1]


@pytest.mark.parametrize(
    ("slot", "mime_type", "file_name"),
    [
        ("document", "text/plain", "notes.txt"),
        ("photo", "image/jpeg", "photo.jpg"),
        ("audio", "audio/mpeg", "audio.mp3"),
        ("video", "video/mp4", "video.mp4"),
        ("document", "application/pdf", "document.pdf"),
    ],
    ids=("text", "image", "audio", "video", "pdf"),
)
@pytest.mark.parametrize("include_file_size", (True, False), ids=("declared-zero", "declared-absent"))
def test_public_chat_rejects_unverifiable_declared_size_before_side_effects(
    slot,
    mime_type,
    file_name,
    include_file_size,
):
    calls = {"get_file": 0, "download": 0, "runtime_delegation": 0}
    replies: list[str] = []

    class TelegramFile:
        async def download_to_drive(self, *, custom_path):
            calls["download"] += 1
            Path(custom_path).write_bytes(b"must-not-download")

    class Bot:
        async def get_file(self, _file_id):
            calls["get_file"] += 1
            return TelegramFile()

    async def reply_text(text, **_kwargs):
        replies.append(text)

    media_fields = {
        "file_id": "telegram-file-id",
        "mime_type": mime_type,
        "file_name": file_name,
        "duration": 1,
    }
    if include_file_size:
        media_fields["file_size"] = 0
    media = SimpleNamespace(**media_fields)
    message = SimpleNamespace(
        photo=None,
        voice=None,
        audio=None,
        video=None,
        document=None,
        caption="Summarize this attachment",
        reply_text=reply_text,
    )
    setattr(message, slot, [media] if slot == "photo" else media)
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(bot=Bot())

    handled = asyncio.run(_public_chat_attachment_handler(calls)(update, context))

    assert handled is True
    assert calls == {"get_file": 0, "download": 0, "runtime_delegation": 0}
    assert replies
