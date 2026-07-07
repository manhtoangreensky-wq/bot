import asyncio
import subprocess
from types import SimpleNamespace

from services import telegram_business_support as cskh


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


def _event(text="alo", *, message_id=1, chat_id=222, connection_id="business-connection-abcdef123456", from_user_id=111):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id=connection_id,
        chat_id=str(chat_id),
        from_user_id=str(from_user_id),
        from_is_bot=False,
        text=text,
        caption="",
        message_id=str(message_id),
        timestamp=1000 + int(message_id),
        media_type="",
    )


def _update(text="alo", *, message_id=1, chat_id=222, connection_id="business-connection-abcdef123456", from_user_id=111):
    message = _obj(
        business_connection_id=connection_id,
        chat=_obj(id=chat_id),
        from_user=_obj(id=from_user_id, is_bot=False),
        text=text,
        caption="",
        message_id=message_id,
        date=1000 + int(message_id),
    )
    return _obj(business_message=message)


def _run(coro):
    return asyncio.run(coro)


def _install_state(monkeypatch, bot, state):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)

    def save(next_state):
        state.clear()
        state.update(next_state)
        return state

    monkeypatch.setattr(bot, "save_cskh_business_state", save)


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_cskh3_conversation_memory_tracks_last_messages():
    state = cskh.default_state()
    for index, text in enumerate(["alo", "cho mình hỏi", "tạo video giá sao", "shop ơi", "có hỗ trợ không", "video bao nhiêu Xu"], 1):
        state = cskh.update_conversation_memory(state, _event(text, message_id=index), cskh.classify_cskh_message(text), now=1000 + index)

    memory = cskh.get_conversation_memory(state, "222", now=1010)

    assert len(memory["last_messages"]) == 5
    assert memory["last_messages"][-1]["text"] == "video bao nhiêu Xu"


def test_cskh3_memory_tracks_last_intent_product_stage():
    classification = cskh.classify_cskh_message("tạo video giá như nào em")
    state = cskh.update_conversation_memory(cskh.default_state(), _event("tạo video giá như nào em"), classification, reply=classification["reply"], now=1000)

    memory = cskh.get_conversation_memory(state, "222", now=1001)

    assert memory["last_intent"] == "product_video_pricing"
    assert memory["last_product"] == "product_video"
    assert memory["conversation_stage"] == "pricing"


def test_cskh3_memory_ttl_expires():
    state = cskh.update_conversation_memory(cskh.default_state(), _event("alo"), cskh.classify_cskh_message("alo"), now=1000, ttl_seconds=60)

    assert cskh.get_conversation_memory(state, "222", now=1070, ttl_seconds=60) == {}


def test_cskh3_memory_no_secret_storage():
    state = cskh.update_conversation_memory(
        cskh.default_state(),
        _event("token abc123 password hunter2 1234567890123456"),
        cskh.classify_cskh_message("không hiểu"),
        now=1000,
    )

    memory_text = memory_join(state)

    assert "abc123" not in memory_text
    assert "hunter2" not in memory_text
    assert "1234567890123456" not in memory_text


def test_cskh3_buffers_alo_then_question():
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.append_message_buffer(state, _event("alo", message_id=1), now=1000, debounce_seconds=3)
    state = cskh.append_message_buffer(state, _event("tạo video giá sao em", message_id=2), now=1001, debounce_seconds=3)
    state, buffer = cskh.pop_message_buffer(state, "222", now=1005)

    assert cskh.combined_text_from_buffer(buffer) == "alo\ntạo video giá sao em"


def test_cskh3_combined_message_classifies_video_pricing():
    result = cskh.classify_thread_messages(["alo", "cho mình hỏi với", "tạo video giá sao em"])

    assert result["intent_id"] == "product_video_pricing"
    assert result["conversation_stage"] == "pricing"


def test_cskh3_no_spam_multiple_replies_for_quick_messages(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, state)
    monkeypatch.setattr(bot, "cskh_schedule_buffer_flush", lambda *_args, **_kwargs: None)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_update("alo", message_id=1), _obj(bot=fake_bot)))
    _run(bot.process_cskh_business_message(_update("tạo video giá sao em", message_id=2), _obj(bot=fake_bot)))

    assert fake_bot.sent_messages == []
    state, buffer = cskh.pop_message_buffer(state, "222", force=True)
    buffered_event = cskh.event_from_buffer(buffer)
    _run(bot.process_cskh_business_event(buffered_event, _obj(bot=fake_bot), allow_debounce=False, state=state))

    assert len(fake_bot.sent_messages) == 1
    assert "video" in fake_bot.sent_messages[0]["text"].lower()


def test_cskh3_urgent_payment_can_reply_fast(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_update("em đã thanh toán nhưng chưa cộng Xu", message_id=3), _obj(bot=fake_bot)))

    customer_replies = [item for item in fake_bot.sent_messages if item.get("business_connection_id")]
    assert len(customer_replies) == 1
    assert "bill" in customer_replies[0]["text"].lower() or "giao dịch" in customer_replies[0]["text"].lower()


def test_cskh3_video_gia_classifies_product_video_pricing():
    assert cskh.classify_cskh_message("tạo video giá như nào em")["intent_id"] == "product_video_pricing"


def test_cskh3_greeting_plus_video_price_uses_video_pricing():
    result = cskh.classify_cskh_message("alo\ncho mình hỏi với\ntạo video giá như nào em")

    assert result["intent_id"] == "product_video_pricing"


def test_cskh3_vague_message_asks_clarifying_question():
    result = cskh.classify_cskh_message("ủa lỗi rồi")

    assert result["intent_id"] == "vague_or_unclear"
    assert "phần nào" in result["reply"] or "nói rõ" in result["reply"] or "ngữ cảnh" in result["reply"]


def test_cskh3_repeated_ping_responds_naturally():
    result = cskh.classify_cskh_message("alo alo có ai không vậy")

    assert result["intent_id"] == "repeated_ping"
    assert "xin lỗi" in result["reply"].lower() or "em đây" in result["reply"].lower()


def test_cskh3_reply_video_pricing_more_helpful():
    reply = cskh.classify_cskh_message("tạo video giá như nào em")["reply"]

    assert "video" in reply.lower()
    assert "gói" in reply.lower() or "xu" in reply.lower()
    assert "mục đích" in reply.lower() or "độ dài" in reply.lower() or "sản phẩm" in reply.lower()


def test_cskh3_reply_vague_more_natural():
    reply = cskh.classify_cskh_message("không được")["reply"]

    assert "nạp Xu" in reply or "tạo video" in reply or "mã xử lý" in reply


def test_cskh3_reply_repeated_ping_apologizes_lightly():
    reply = cskh.classify_cskh_message("sao không trả lời")["reply"].lower()

    assert "xin lỗi" in reply or "em đây" in reply


def test_cskh3_reply_no_internal_terms():
    replies = [
        cskh.classify_cskh_message("tạo video giá sao")["reply"],
        cskh.classify_cskh_message("lỗi rồi")["reply"],
        cskh.classify_cskh_message("alo alo")["reply"],
    ]

    assert all(cskh.public_reply_is_safe(reply) for reply in replies)


def test_cskh3_reply_no_auto_refund_or_topup_promise():
    joined = " ".join(
        cskh.classify_cskh_message(text)["reply"]
        for text in ["hoàn Xu đi", "em đã thanh toán nhưng chưa cộng Xu", "video lỗi trả Xu"]
    ).lower()

    assert "đã hoàn" not in joined
    assert "đã cộng xu" not in joined


def test_cskh3_low_confidence_added_to_learning_queue():
    result = cskh.classify_cskh_message("asdasd qweqwe zzz")
    state, item = cskh.add_learning_candidate(cskh.default_state(), _event("asdasd qweqwe zzz"), result, text="asdasd qweqwe zzz")

    assert item["id"] in state["learning_queue"]
    assert item["why_queued"] == "low_confidence"


def test_cskh3_vague_added_to_learning_queue():
    result = cskh.classify_cskh_message("ủa")
    state, item = cskh.add_learning_candidate(cskh.default_state(), _event("ủa"), result, text="ủa")

    assert item["why_queued"] == "unclear_or_unanswered"


def test_cskh3_learning_queue_admin_only(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    update = _obj(effective_user=_obj(id=2), message=FakeMessage())

    _run(bot.cmd_cskh_learning_queue(update, _obj(args=[])))

    assert "admin" in update.message.replies[-1][0].lower()


def test_cskh3_learning_queue_masks_chat_id():
    result = cskh.classify_cskh_message("không hiểu")
    _state, item = cskh.add_learning_candidate(cskh.default_state(), _event("không hiểu", chat_id=123456789), result, text="không hiểu")

    assert item["chat_id_masked"] != "123456789"
    assert "..." in item["chat_id_masked"]


def test_cskh3_no_unreviewed_auto_learning():
    state, item = cskh.add_learning_candidate(cskh.default_state(), _event("không hiểu"), cskh.classify_cskh_message("không hiểu"), text="không hiểu")

    assert item["status"] == "open"
    assert "intents" not in state


def test_cskh3_test_thread_combines_messages(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=["alo", "|", "cho", "mình", "hỏi", "|", "tạo", "video", "giá", "sao"])

    _run(bot.cmd_cskh_test_thread(update, context))

    assert "Combined text" in update.message.replies[-1][0]
    assert "alo" in update.message.replies[-1][0]


def test_cskh3_test_thread_video_pricing(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=["alo", "|", "tạo", "video", "giá", "như", "nào", "em"])

    _run(bot.cmd_cskh_test_thread(update, context))

    assert "product_video_pricing" in update.message.replies[-1][0]


def test_cskh3_cskh_test_existing_still_works(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())

    _run(bot.cmd_cskh_test(update, _obj(args=["nạp", "Xu", "chưa", "cộng"])))

    assert "Would send: <code>no</code>" in update.message.replies[-1][0]


def test_cskh3_off_suppresses():
    guard = cskh.evaluate_auto_reply_guard(cskh.default_state(), _event("tạo video giá sao"), now=2000)
    assert guard["disabled_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh3_handoff_suppresses():
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.set_handoff(state, "222", True, "admin")
    guard = cskh.evaluate_auto_reply_guard(state, _event("tạo video giá sao"), now=2000)
    assert guard["handoff_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh3_duplicate_guard_still_blocks_exact_duplicate():
    state = {**cskh.default_state(), "enabled": True}
    event = _event("tạo video giá sao", message_id=88)
    state = cskh.record_auto_reply(state, event, {"intent_id": "product_video_pricing"}, {"payload": {"business_connection_id": event.business_connection_id}})
    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000)
    assert guard["duplicate_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh3_cooldown_allows_new_distinct_question():
    state = {**cskh.default_state(), "enabled": True}
    state["last_auto_reply_at"]["222"] = 1990
    guard = cskh.evaluate_auto_reply_guard(state, _event("tạo video giá sao", message_id=89), now=2000, cooldown_seconds=60)
    assert guard["cooldown_suppressed"] is False
    assert guard["allowed"] is True


def test_cskh3_self_admin_deleted_guards_preserved():
    base = {**cskh.default_state(), "enabled": True}
    self_guard = cskh.evaluate_auto_reply_guard(base, _event("alo", from_user_id=999), bot_user_id=999, now=2000)
    assert self_guard["self_message_suppressed"] is True

    admin_state = cskh.upsert_business_connection(base, _obj(id="business-connection-abcdef123456", user=_obj(id=111), is_enabled=True))
    admin_guard = cskh.evaluate_auto_reply_guard(admin_state, _event("alo", from_user_id=111), now=2000)
    assert admin_guard["admin_manual_suppressed"] is True

    deleted_state = cskh.mark_deleted_business_messages(
        base,
        {"business_connection_id": "business-connection-abcdef123456", "chat_id": "222", "message_ids": ["55"]},
    )
    deleted_guard = cskh.evaluate_auto_reply_guard(deleted_state, _event("alo", message_id=55), now=2000)
    assert deleted_guard["deleted_suppressed"] is True


def test_cskh3_armed_mode_preserved():
    payload = cskh.status_payload({**cskh.default_state(), "enabled": True}, bot_status={"can_connect_to_business": True}, allowed_updates=cskh.BUSINESS_UPDATE_TYPES)
    assert payload["auto_reply_mode"] == "armed"
    assert payload["waiting_for_first_business_message"] is True


def test_cskh3_no_music_runtime_changes():
    changed = _changed_files()
    assert not any(("music" in path.lower() and not path.startswith("tests/")) for path in changed)


def test_cskh3_no_product_video_runtime_changes():
    changed = _changed_files()
    forbidden = ("video_real_render", "video_provider", "video_project", "product_video", "video_product")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh3_no_img2vid_runtime_changes():
    changed = _changed_files()
    forbidden = ("img2vid", "image_to_video", "ghep_anh", "storyboard")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh3_no_subdub_runtime_changes():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_cskh3_no_payos_pricing_db_webhook_changes():
    changed = " ".join(_changed_files()).lower()
    for forbidden in ("payos", "pricing", "migration", "webhook"):
        assert forbidden not in changed


def memory_join(state):
    memory = cskh.get_conversation_memory(state, "222", now=1001)
    return " ".join(item.get("text", "") for item in memory.get("last_messages", []))


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.id = 999
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return _obj(message_id=999)

    async def raw_bot_api_request(self, method, payload):
        self.sent_messages.append(payload)
        return {"ok": True, "method": method, "result": {"message_id": 999}}
