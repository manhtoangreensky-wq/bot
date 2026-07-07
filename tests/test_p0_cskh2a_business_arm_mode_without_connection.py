import asyncio
import subprocess
from types import SimpleNamespace

from services import telegram_business_support as cskh


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


def _business_message_update(
    text="cho em xin bang gia nap Xu",
    *,
    connection_id="business-connection-abcdef123456",
    chat_id=222,
    message_id=10,
    from_user_id=111,
    from_is_bot=False,
):
    message = _obj(
        business_connection_id=connection_id,
        chat=_obj(id=chat_id),
        from_user=_obj(id=from_user_id, is_bot=from_is_bot),
        text=text,
        caption="",
        message_id=message_id,
        date=1000,
    )
    return _obj(business_message=message)


def _event(**kwargs):
    update = _business_message_update(**kwargs)
    return cskh.extract_business_message(update)


def _install_state(monkeypatch, bot, state):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)

    def save(next_state):
        state.clear()
        state.update(next_state)
        return state

    monkeypatch.setattr(bot, "save_cskh_business_state", save)


def _admin_update():
    return _obj(effective_user=_obj(id=1), message=FakeMessage())


def _run(coro):
    return asyncio.run(coro)


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _current_branch_name() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        check=False,
        text=True,
        capture_output=True,
    )
    return (result.stdout or "").strip().lower()


def _is_img2vid_branch() -> bool:
    return "img2vid" in _current_branch_name() or "image-to-video" in _current_branch_name()


def test_cskh2a_on_allows_armed_mode_without_existing_connection(monkeypatch):
    import bot

    state = cskh.default_state()
    _install_state(monkeypatch, bot, state)
    update = _admin_update()
    context = _obj(args=[], bot=FakeBot())

    _run(bot.cmd_cskh_on(update, context))

    assert state["enabled"] is True
    assert state["connections"] == {}
    assert "chế độ chờ Business chat" in update.message.replies[-1][0]


def test_cskh2a_on_blocks_if_bot_cannot_connect_business(monkeypatch):
    import bot

    state = cskh.default_state()
    _install_state(monkeypatch, bot, state)
    update = _admin_update()
    context = _obj(args=[], bot=FakeBot(can_connect_to_business=False))

    _run(bot.cmd_cskh_on(update, context))

    assert state["enabled"] is False
    assert "chưa có quyền kết nối Telegram Business" in update.message.replies[-1][0]


def test_cskh2a_on_blocks_if_allowed_updates_missing_business(monkeypatch):
    import bot

    state = cskh.default_state()
    _install_state(monkeypatch, bot, state)
    update = _admin_update()
    context = _obj(args=[], bot=FakeBot(allowed_updates=["message"]))

    _run(bot.cmd_cskh_on(update, context))

    assert state["enabled"] is False
    assert "allowed_updates" in update.message.replies[-1][0]


def test_cskh2a_status_shows_armed_waiting_for_first_message():
    state = {**cskh.default_state(), "enabled": True}

    payload = cskh.status_payload(
        state,
        bot_status={"can_connect_to_business": True},
        allowed_updates=cskh.BUSINESS_UPDATE_TYPES,
    )

    assert payload["auto_reply_mode"] == "armed"
    assert payload["waiting_for_first_business_message"] is True
    assert payload["active_connection_count"] == 0


def test_cskh2a_first_business_message_registers_connection(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_business_message_update(), _obj(bot=fake_bot)))

    assert "business-connection-abcdef123456" in state["connections"]
    payload = cskh.status_payload(state, bot_status={"can_connect_to_business": True}, allowed_updates=cskh.BUSINESS_UPDATE_TYPES)
    assert payload["active_connection_count"] == 1
    assert payload["receiving_business_messages"] is True
    assert payload["auto_reply_mode"] == "on"


def test_cskh2a_first_business_message_triggers_reply_when_armed(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_business_message_update("cho mình xin bảng giá"), _obj(bot=fake_bot)))

    assert fake_bot.sent_messages
    sent = fake_bot.sent_messages[-1]
    assert sent["business_connection_id"] == "business-connection-abcdef123456"
    assert sent["chat_id"] == "222"


def test_cskh2a_no_reply_when_off_even_if_business_message(monkeypatch):
    import bot

    state = cskh.default_state()
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_business_message_update(), _obj(bot=fake_bot)))

    assert fake_bot.sent_messages == []
    assert state["connections"] == {}
    assert state["last_debug"]["disabled_suppressed"] is True


def test_cskh2a_handoff_still_suppresses_reply(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    state = cskh.set_handoff(state, "222", True, "admin_manual")
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()

    _run(bot.process_cskh_business_message(_business_message_update(), _obj(bot=fake_bot)))

    assert fake_bot.sent_messages == []
    assert state["last_debug"]["handoff_suppressed"] is True
    assert state["last_debug"]["block_reason"] == "handoff"


def test_cskh2a_duplicate_guard_preserved(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, state)
    fake_bot = FakeBot()
    update = _business_message_update(message_id=44)

    _run(bot.process_cskh_business_message(update, _obj(bot=fake_bot)))
    _run(bot.process_cskh_business_message(update, _obj(bot=fake_bot)))

    assert len(fake_bot.sent_messages) == 1
    assert state["last_debug"]["duplicate_suppressed"] is True


def test_cskh2a_self_admin_deleted_guards_preserved(monkeypatch):
    import bot

    self_state = {**cskh.default_state(), "enabled": True}
    _install_state(monkeypatch, bot, self_state)
    self_bot = FakeBot(bot_id=999)
    _run(bot.process_cskh_business_message(_business_message_update(from_user_id=999), _obj(bot=self_bot)))
    assert self_bot.sent_messages == []
    assert self_state["last_debug"]["self_message_suppressed"] is True

    admin_state = {**cskh.default_state(), "enabled": True}
    admin_state = cskh.upsert_business_connection(
        admin_state,
        _obj(id="business-connection-abcdef123456", user=_obj(id=111), is_enabled=True),
    )
    _install_state(monkeypatch, bot, admin_state)
    admin_bot = FakeBot()
    _run(bot.process_cskh_business_message(_business_message_update(from_user_id=111), _obj(bot=admin_bot)))
    assert admin_bot.sent_messages == []
    assert admin_state["last_debug"]["admin_manual_suppressed"] is True

    deleted_state = {**cskh.default_state(), "enabled": True}
    deleted_state = cskh.mark_deleted_business_messages(
        deleted_state,
        {"business_connection_id": "business-connection-abcdef123456", "chat_id": "222", "message_ids": ["55"]},
    )
    _install_state(monkeypatch, bot, deleted_state)
    deleted_bot = FakeBot()
    _run(bot.process_cskh_business_message(_business_message_update(message_id=55), _obj(bot=deleted_bot)))
    assert deleted_bot.sent_messages == []
    assert deleted_state["last_debug"]["deleted_suppressed"] is True


def test_cskh2a_status_armed_copy_clear():
    import bot

    payload = cskh.status_payload(
        {**cskh.default_state(), "enabled": True},
        bot_status={"can_connect_to_business": True},
        allowed_updates=cskh.BUSINESS_UPDATE_TYPES,
    )

    text = "\n".join(bot.cskh_status_lines(payload, {"username": "toanaasbot"}))

    assert "Auto-reply mode: <code>armed</code>" in text
    assert "Waiting for first selected Business message: <code>yes</code>" in text
    assert "Đã bật chế độ chờ" in text


def test_cskh2a_status_last_block_reason():
    state = {**cskh.default_state(), "enabled": True}
    guard = cskh.evaluate_auto_reply_guard(state, _event(connection_id=""), now=2000)
    state = cskh.record_suppressed(state, _event(connection_id=""), {"intent_id": "pricing"}, guard)

    payload = cskh.status_payload(state, bot_status={"can_connect_to_business": True}, allowed_updates=cskh.BUSINESS_UPDATE_TYPES)

    assert payload["last_block_reason"] == "missing_business_connection_id"


def test_cskh2a_status_masks_connection_id():
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.upsert_business_connection_from_message(state, _event())

    payload = cskh.status_payload(state, bot_status={"can_connect_to_business": True}, allowed_updates=cskh.BUSINESS_UPDATE_TYPES)

    assert payload["latest_connection_id_masked"] != "business-connection-abcdef123456"
    assert "..." in payload["latest_connection_id_masked"]


def test_cskh2a_cskh_test_payment_xu_still_works(monkeypatch):
    text = _run_cskh_test(monkeypatch, "em đã thanh toán PayOS thành công nhưng chưa cộng Xu")

    assert "Would send: <code>no</code>" in text
    assert "Training data:" in text
    assert "payment" in text.lower()
    assert "Ticket preview" in text


def test_cskh2a_cskh_test_pricing_still_works(monkeypatch):
    text = _run_cskh_test(monkeypatch, "cho mình xin bảng giá và gói phù hợp")

    assert "Would send: <code>no</code>" in text
    assert "Intent: <code>pricing_general</code>" in text


def test_cskh2a_cskh_test_video_no_file_priority_if_existing(monkeypatch):
    text = _run_cskh_test(monkeypatch, "video AI bị kẹt không ra file, mã xử lý A123")

    assert "Would send: <code>no</code>" in text
    assert "video" in text.lower()
    assert "technical_error" not in text


def test_cskh2a_no_public_internal_terms():
    replies = [
        cskh.classify_cskh_message("video bị kẹt không ra file")["reply"],
        cskh.classify_cskh_message("nạp xu rồi chưa thấy cộng")["reply"],
        cskh.classify_cskh_message("cho mình xin bảng giá")["reply"],
    ]

    assert all(cskh.public_reply_is_safe(reply) for reply in replies)


def test_cskh2a_no_music_runtime_changes():
    changed = _changed_files()
    assert not any(("music" in path.lower() and not path.startswith("tests/")) for path in changed)


def test_cskh2a_no_product_video_runtime_changes():
    changed = _changed_files()
    forbidden = ("video_real_render", "video_provider", "video_project", "product_video", "video_product")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh2a_no_img2vid_runtime_changes():
    if _is_img2vid_branch():
        return
    changed = _changed_files()
    forbidden = ("img2vid", "image_to_video", "ghép ảnh", "ghep_anh", "storyboard")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh2a_no_subdub_runtime_changes():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_cskh2a_no_payos_pricing_db_webhook_changes():
    changed = " ".join(_changed_files()).lower()
    for forbidden in ("payos", "pricing", "migration", "webhook"):
        assert forbidden not in changed


def _run_cskh_test(monkeypatch, text):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _admin_update()
    context = _obj(args=text.split(), bot=FakeBot())

    _run(bot.cmd_cskh_test(update, context))

    assert update.message.replies
    return update.message.replies[-1][0]


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self, *, can_connect_to_business=True, allowed_updates=None, bot_id=999):
        self.id = bot_id
        self.token = "123:test-token"
        self.can_connect_to_business = can_connect_to_business
        self.allowed_updates = list(allowed_updates or cskh.BUSINESS_UPDATE_TYPES)
        self.sent_messages = []

    async def get_me(self):
        return _obj(id=self.id, username="toanaasbot", can_connect_to_business=self.can_connect_to_business)

    async def get_webhook_info(self):
        return _obj(allowed_updates=self.allowed_updates)

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return _obj(message_id=999)

    async def raw_bot_api_request(self, method, payload):
        self.sent_messages.append(payload)
        return {"ok": True, "method": method, "result": {"message_id": 999}}
