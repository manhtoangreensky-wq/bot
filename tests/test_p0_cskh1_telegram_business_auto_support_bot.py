import asyncio
import subprocess
from types import SimpleNamespace

from services import telegram_business_support as cskh


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


def _business_message_update(text="xin bang gia nap Xu", message_id=10, from_user_id=111, from_is_bot=False):
    message = _obj(
        business_connection_id="business-connection-abcdef123456",
        chat=_obj(id=222),
        from_user=_obj(id=from_user_id, is_bot=from_is_bot),
        text=text,
        caption="",
        message_id=message_id,
        date=1000,
    )
    return _obj(business_message=message)


def test_business_connection_stored_and_masked_in_status():
    state = cskh.default_state()
    connection = _obj(
        id="business-connection-abcdef123456",
        user=_obj(id=111, username="toanaas"),
        user_chat_id=222,
        is_enabled=True,
    )
    state = cskh.upsert_business_connection(state, connection)
    payload = cskh.status_payload(state, bot_status={"can_connect_to_business": True}, allowed_updates=cskh.BUSINESS_UPDATE_TYPES)

    assert payload["active_connection_count"] == 1
    assert payload["latest_connection_id_masked"] != "business-connection-abcdef123456"
    assert "..." in payload["latest_connection_id_masked"]


def test_business_message_normalized():
    event = cskh.extract_business_message(_business_message_update("chao TOAN AAS", 77))

    assert event.business_connection_id == "business-connection-abcdef123456"
    assert event.chat_id == "222"
    assert event.from_user_id == "111"
    assert event.message_id == "77"
    assert event.text == "chao TOAN AAS"


def test_rules_classify_pricing_nap_xu():
    result = cskh.classify_cskh_message("Cho mình hỏi bảng giá nạp Xu")

    assert result["intent_id"] == "pricing"
    assert result["handoff"] is False


def test_rules_classify_payment_refund_as_handoff_ticket_no_false_promise():
    payment = cskh.classify_cskh_message("Mình nạp rồi nhưng chưa nhận Xu")
    refund = cskh.classify_cskh_message("Tôi muốn hoàn Xu")

    assert payment["handoff"] is True
    assert payment["ticket"] is True
    assert refund["handoff"] is True
    assert refund["ticket"] is True
    joined = (payment["reply"] + " " + refund["reply"]).lower()
    assert "tự hứa" in joined or "chưa tự động" in joined or "không tự" in joined


def test_rules_classify_technical_error_asks_for_ma_xu_ly():
    result = cskh.classify_cskh_message("Video bị lỗi không chạy")

    assert result["intent_id"] == "technical_error"
    assert "mã xử lý" in result["reply"]
    assert result["handoff"] is True


def test_admin_cskh_on_enables(monkeypatch):
    import bot

    state = cskh.default_state()
    state = cskh.upsert_business_connection(
        state,
        _obj(id="business-connection-abcdef123456", user=_obj(id=111), is_enabled=True),
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)

    def save(next_state):
        state.clear()
        state.update(next_state)
        return state

    monkeypatch.setattr(bot, "save_cskh_business_state", save)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=[], bot=FakeBot())

    asyncio.run(bot.cmd_cskh_on(update, context))

    assert state["enabled"] is True
    assert update.message.replies


def test_admin_cskh_off_disables(monkeypatch):
    import bot

    state = {**cskh.default_state(), "enabled": True}
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)

    def save(next_state):
        state.clear()
        state.update(next_state)
        return state

    monkeypatch.setattr(bot, "save_cskh_business_state", save)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=[])

    asyncio.run(bot.cmd_cskh_off(update, context))

    assert state["enabled"] is False


def test_non_admin_cannot_control_cskh(monkeypatch):
    import bot

    state = cskh.default_state()
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)
    update = _obj(effective_user=_obj(id=2), message=FakeMessage())
    context = _obj(args=[])

    asyncio.run(bot.cmd_cskh_on(update, context))

    assert state["enabled"] is False
    assert "admin" in update.message.replies[-1][0].lower()


def test_duplicate_business_message_suppressed():
    event = cskh.extract_business_message(_business_message_update(message_id=99))
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.record_auto_reply(state, event, {"intent_id": "greeting"}, {"payload": {"business_connection_id": event.business_connection_id}})

    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000)

    assert guard["duplicate_suppressed"] is True
    assert guard["allowed"] is False


def test_cooldown_suppresses_repeated_replies():
    event = cskh.extract_business_message(_business_message_update(text="alo", message_id=100))
    state = {**cskh.default_state(), "enabled": True}
    state["last_auto_reply_at"][event.chat_id] = 1990

    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000, cooldown_seconds=60)

    assert guard["cooldown_suppressed"] is True


def test_handoff_suppresses_auto_reply():
    event = cskh.extract_business_message(_business_message_update(message_id=101))
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.set_handoff(state, event.chat_id, True, "admin_manual")

    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000)

    assert guard["handoff_suppressed"] is True


def test_own_self_messages_ignored():
    event = cskh.extract_business_message(_business_message_update(message_id=102, from_user_id=999))
    state = {**cskh.default_state(), "enabled": True}

    guard = cskh.evaluate_auto_reply_guard(state, event, bot_user_id=999, now=2000)

    assert guard["self_message_suppressed"] is True


def test_deleted_business_message_does_not_reply():
    event = cskh.extract_business_message(_business_message_update(message_id=103))
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.mark_deleted_business_messages(
        state,
        {
            "business_connection_id": event.business_connection_id,
            "chat_id": event.chat_id,
            "message_ids": [event.message_id],
        },
    )

    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000)

    assert guard["deleted_suppressed"] is True


def test_send_business_message_includes_business_connection_id():
    fake_bot = FakeBot()

    result = asyncio.run(cskh.send_business_message(fake_bot, "bcid-123", 222, "hello", reply_to_message_id=10))

    assert result["method"] == "ptb"
    assert fake_bot.sent["business_connection_id"] == "bcid-123"
    assert fake_bot.sent["chat_id"] == 222


def test_fallback_raw_bot_api_wrapper_if_library_lacks_parameter():
    fake_bot = FakeBot(raise_type_error=True)

    result = asyncio.run(cskh.send_business_message(fake_bot, "bcid-raw", 222, "hello"))

    assert result["method"] == "raw"
    assert fake_bot.raw_payload["business_connection_id"] == "bcid-raw"


def test_support_menu_back_exact_previous_screen():
    import bot

    labels = [button.text for row in bot.human_support_keyboard().inline_keyboard for button in row]
    callbacks = [button.callback_data for row in bot.support_cskh_auto_keyboard().inline_keyboard for button in row if button.callback_data]

    assert "🤖 CSKH tự động" in labels
    assert "support|start" in callbacks


def test_no_music_product_video_subdub_runtime_touched():
    changed = _changed_files()
    if _is_subdub_scope(changed):
        return
    allowed = {
        "bot.py",
        "services/telegram_business_support.py",
        "config/cskh_knowledge_base.json",
        "config/cskh_training_data.json",
        "docs/cskh_telegram_business_setup.md",
        "docs/cskh_toan_aas_playbook.md",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_19m6ae_subdub_subtitle_polish_and_dub_known_good_restore.py",
    }
    img2vid_scope = {
        "bot.py",
        "local_worker.py",
        "video_image_to_video_flow.py",
        "tests/test_p0_17b7_2_image_to_video_dedupe_flow.py",
        "tests/test_p0_free1_refresh_free_tools_menu_existing_zero_cost_shortcuts.py",
        "tests/test_p0_video_img2vid_lock1_two_path_flow.py",
        "tests/test_p0_18f_video_menu_route_audit_fix_only.py",
        "tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py",
        "tests/test_p0_18m_restore_canonical_video_product_flows_from_backup.py",
        "tests/test_p0_18n_hard_lock_video_ui_ux_router_state_machine_back_matrix.py",
        "tests/test_p0_18n1_unify_video_product_entry_ui_flow_matrix.py",
        "tests/test_p0_18n2_restore_video_product_semantics_trend_flow_ui.py",
        "tests/test_p0_18q_video_ui_polish_back_routing_5_option_buttons.py",
        "tests/test_p0_18q1_lock_video_ui_flow_compact_dynamic_status_steps.py",
        "tests/test_p0_18q2_video_auto_refresh_status_like_subdub_only.py",
        "tests/test_p0_23h14f_music_voice_preset_duet_progress_single_track_fix.py",
        "tests/test_p0_23h14g_music_expose_custom_lyrics_button_on_idea_screen.py",
        "tests/test_p0_23h14h_music_compact_idea_menu_restore_female_voice_pr173.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
    }
    if "tests/test_p0_video_img2vid_lock1_two_path_flow.py" in changed:
        assert set(changed) <= img2vid_scope
        return

    assert set(changed) <= allowed


def test_no_payos_pricing_db_destructive_change():
    changed = " ".join(_changed_files()).lower()

    assert "payos" not in changed
    assert "pricing" not in changed
    assert "migration" not in changed


def test_public_replies_contain_no_provider_api_internal_terms():
    kb = cskh.load_knowledge_base()

    for intent in kb["intents"]:
        assert cskh.public_reply_is_safe(intent["reply"]), intent["id"]


def test_cskh_test_does_not_send_real_reply(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=["nạp", "rồi", "chưa", "nhận", "Xu"], bot=FakeBot())

    asyncio.run(bot.cmd_cskh_test(update, context))

    assert update.message.replies
    assert context.bot.sent is None
    assert "Would send: <code>no</code>" in update.message.replies[-1][0]


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self, raise_type_error=False):
        self.raise_type_error = raise_type_error
        self.sent = None
        self.raw_payload = None
        self.id = 999
        self.token = "123:test-token"

    async def send_message(self, **kwargs):
        if self.raise_type_error:
            raise TypeError("unexpected keyword argument 'business_connection_id'")
        self.sent = kwargs
        return _obj(message_id=1)

    async def get_me(self):
        return _obj(id=self.id, username="toanaasbot", can_connect_to_business=True)

    async def get_webhook_info(self):
        return _obj(allowed_updates=cskh.BUSINESS_UPDATE_TYPES)

    async def raw_bot_api_request(self, method, payload):
        self.raw_payload = payload
        return {"ok": True, "method": method, "result": {"message_id": 2}}


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _is_subdub_scope(changed):
    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        check=False,
        text=True,
        capture_output=True,
    )
    branch = branch_result.stdout.strip().lower() if branch_result.returncode == 0 else ""
    tokens = ("p0-19m", "subdub", "subtitle-dub", "subtitle_dub")
    return any(token in branch for token in tokens) or any(
        any(token in path.lower() for token in tokens)
        for path in changed
    )
