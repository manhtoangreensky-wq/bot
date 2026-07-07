import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]
TRAINING_PATH = ROOT / "config" / "cskh_training_data.json"
PLAYBOOK_PATH = ROOT / "docs" / "cskh_toan_aas_playbook.md"


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


def _event(text="xin chào", message_id=1, from_user_id=111, from_is_bot=False):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id="business-connection-abcdef123456",
        chat_id="222",
        from_user_id=str(from_user_id),
        from_is_bot=from_is_bot,
        text=text,
        caption="",
        message_id=str(message_id),
        timestamp=1000,
        media_type="",
    )


def _data():
    return json.loads(TRAINING_PATH.read_text(encoding="utf-8"))


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _classify(text):
    return cskh.classify_cskh_message(text, variation_seed=text)


def test_training_data_json_loads_and_required_keys():
    data = _data()
    required = {
        "version",
        "brand",
        "language",
        "tone_profile",
        "global_rules",
        "safety_rules",
        "intents",
        "conversation_scenarios",
        "ticket_fields",
        "handoff_rules",
        "aftercare_rules",
        "quality_checklist",
        "forbidden_phrases",
        "preferred_phrases",
    }
    assert required <= set(data)
    assert data["brand"].startswith("TOAN AAS")


def test_training_data_has_at_least_24_intents_and_60_scenarios():
    data = _data()
    assert len(data["intents"]) >= 24
    assert len(data["conversation_scenarios"]) >= 60


def test_each_intent_has_examples_and_reply_templates():
    for intent in _data()["intents"]:
        assert len(intent["example_user_messages"]) >= 8, intent["id"]
        assert len(intent["reply_templates"]) >= 4, intent["id"]


def test_each_scenario_references_valid_intent():
    data = _data()
    intents = {intent["id"] for intent in data["intents"]}
    for scenario in data["conversation_scenarios"]:
        assert scenario["detected_intent"] in intents, scenario["scenario_id"]


def test_payment_xu_issue_classifies_high_urgent():
    result = _classify("tôi nạp tiền rồi chưa thấy Xu")
    assert result["intent_id"] == "payment_xu_not_received"
    assert result["confidence"] == "high"
    assert result["severity"] == "urgent"
    assert result["handoff_required"] is True
    assert result["ticket_required"] is True
    assert {"payment_amount", "payment_time", "screenshot_or_bill"} <= set(result["missing_fields"])


def test_angry_scam_classifies_urgent_handoff():
    result = _classify("Bot này scam à, mất tiền rồi")
    assert result["intent_id"] == "angry_scam_accusation"
    assert result["severity"] == "urgent"
    assert result["handoff_required"] is True


def test_product_video_stuck_classifies():
    assert _classify("video kẹt 20% mãi không ra MP4")["intent_id"] == "product_video_stuck"


def test_subdub_subtitle_failed_classifies():
    assert _classify("phụ đề không hiện trong video")["intent_id"] == "subdub_subtitle_error"


def test_subdub_dubbing_failed_classifies():
    assert _classify("lồng tiếng không ra video")["intent_id"] == "subdub_dubbing_error"


def test_music_wrong_voice_or_duplicate_file_classifies():
    assert _classify("nhạc ra hai file giống nhau")["intent_id"] == "music_wrong_voice_or_duplicate_file"


def test_voice_tts_failed_classifies():
    assert _classify("voice không ra file audio")["intent_id"] == "voice_tts_error"


def test_free_tools_question_classifies():
    assert _classify("có công cụ miễn phí viết caption không")["intent_id"] == "free_tools_help"


def test_private_bot_question_classifies():
    assert _classify("mình muốn bot riêng trả lời khách cho shop")["intent_id"] == "premium_private_bot"


def test_vague_error_asks_clarifying_question():
    result = _classify("lỗi rồi")
    assert result["intent_id"] == "out_of_scope"
    assert result["confidence"] == "low"
    assert "đang lỗi ở phần" in result["reply"] or "đang hỏi về công cụ nào" in result["reply"]


def test_out_of_scope_safe_reply():
    result = _classify("hack tài khoản facebook giúp tôi")
    assert result["intent_id"] == "out_of_scope"
    assert cskh.public_reply_is_safe(result["reply"])


def test_reply_has_no_public_internal_terms():
    for intent in _data()["intents"]:
        for reply in intent["reply_templates"]:
            assert cskh.public_reply_is_safe(reply), intent["id"]


def test_no_auto_refund_or_topup_promise():
    unsafe = ("đã hoàn tiền", "đã hoàn xu", "đã cộng xu", "chắc chắn hoàn")
    for intent in _data()["intents"]:
        joined = " ".join(intent["reply_templates"]).lower()
        assert not any(term in joined for term in unsafe), intent["id"]


def test_ticket_preview_generated_for_payment_issue():
    result = _classify("mình nạp 100k rồi chưa thấy Xu")
    ticket = result["ticket_preview"]
    assert ticket["intent"] == "payment_xu_not_received"
    assert ticket["payment_amount"]
    assert ticket["handoff_required"] is True


def test_ticket_preview_generated_for_paid_service_failure():
    result = _classify("bị trừ Xu mà video fail rồi")
    ticket = result["ticket_preview"]
    assert ticket["product"] == "product_video"
    assert ticket["severity"] == "urgent"


def test_cskh_test_includes_intent_confidence_severity_handoff_ticket_reply(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    context = _obj(args=["tôi", "nạp", "tiền", "rồi", "chưa", "thấy", "Xu"], bot=FakeBot())

    asyncio.run(bot.cmd_cskh_test(update, context))

    payload = update.message.replies[-1][0]
    assert "Intent:" in payload
    assert "Confidence:" in payload
    assert "Severity:" in payload
    assert "Handoff required:" in payload
    assert "Ticket required:" in payload
    assert "Reply preview:" in payload
    assert "Ticket preview:" in payload
    assert context.bot.sent is None


def test_cskh_intents_shows_version_and_count(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    asyncio.run(bot.cmd_cskh_intents(update, _obj(args=[])))
    payload = update.message.replies[-1][0]
    assert "Version:" in payload
    assert "Intent count:" in payload
    assert "AI default:" in payload


def test_repeated_responses_vary_for_high_volume_intent():
    first = cskh.classify_cskh_message("tôi nạp tiền rồi chưa thấy Xu")
    second = cskh.classify_cskh_message("tôi nạp tiền rồi chưa thấy Xu")
    assert first["reply_template_id"] != second["reply_template_id"]
    assert first["reply"] != second["reply"]


def test_response_length_bounded():
    for intent in _data()["intents"]:
        for reply in intent["reply_templates"]:
            assert len(reply) <= 1200, intent["id"]


def test_ai_disabled_by_default():
    state = cskh.default_state()
    assert state["enabled"] is False
    assert state["mode"] == "rules_only"


def test_cskh_on_allows_armed_mode_without_active_business_connection(monkeypatch):
    import bot

    state = cskh.default_state()
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "cskh_business_state", lambda: state)

    def save(next_state):
        state.clear()
        state.update(next_state)
        return state

    monkeypatch.setattr(bot, "save_cskh_business_state", save)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    asyncio.run(bot.cmd_cskh_on(update, _obj(args=[], bot=FakeBot())))
    assert state["enabled"] is True
    assert "chế độ chờ Business chat" in update.message.replies[-1][0]


def test_cskh2_off_suppresses_business_auto_reply():
    guard = cskh.evaluate_auto_reply_guard(cskh.default_state(), _event(), now=2000)
    assert guard["disabled_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh2_handoff_suppresses_auto_reply():
    state = {**cskh.default_state(), "enabled": True}
    state = cskh.set_handoff(state, "222", True, "admin")
    guard = cskh.evaluate_auto_reply_guard(state, _event(), now=2000)
    assert guard["handoff_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh2_duplicate_guard_preserved():
    state = {**cskh.default_state(), "enabled": True}
    event = _event(message_id=44)
    state = cskh.record_auto_reply(state, event, {"intent_id": "greeting"}, {"payload": {"business_connection_id": event.business_connection_id}})
    guard = cskh.evaluate_auto_reply_guard(state, event, now=2000)
    assert guard["duplicate_suppressed"] is True
    assert guard["allowed"] is False


def test_cskh2_self_admin_deleted_guards_preserved():
    base = {**cskh.default_state(), "enabled": True}
    self_guard = cskh.evaluate_auto_reply_guard(base, _event(from_user_id=999), bot_user_id=999, now=2000)
    assert self_guard["self_message_suppressed"] is True

    admin_state = cskh.upsert_business_connection(base, _obj(id="business-connection-abcdef123456", user=_obj(id=111), is_enabled=True))
    admin_guard = cskh.evaluate_auto_reply_guard(admin_state, _event(from_user_id=111), now=2000)
    assert admin_guard["admin_manual_suppressed"] is True

    deleted_state = cskh.mark_deleted_business_messages(
        base,
        {"business_connection_id": "business-connection-abcdef123456", "chat_id": "222", "message_ids": ["55"]},
    )
    deleted_guard = cskh.evaluate_auto_reply_guard(deleted_state, _event(message_id=55), now=2000)
    assert deleted_guard["deleted_suppressed"] is True


def test_cskh2_no_public_internal_terms():
    result = _classify("video kẹt 20%")
    assert cskh.public_reply_is_safe(result["reply"])


def test_cskh2_no_auto_refund_or_topup_promise():
    joined = " ".join(
        _classify(text)["reply"]
        for text in ["hoàn Xu cho tôi", "mình nạp tiền rồi chưa thấy Xu", "bị trừ Xu mà video fail"]
    ).lower()
    assert "đã hoàn" not in joined
    assert "đã cộng xu" not in joined


def test_ticket_fields_exist_for_required_issue_types():
    ticket_fields = _data()["ticket_fields"]
    for key in ("payment", "product_video", "subdub", "music", "voice", "premium_private_bot"):
        assert key in ticket_fields
        assert ticket_fields[key]


def test_playbook_doc_exists_and_has_4a_qc_escalation_refund():
    text = PLAYBOOK_PATH.read_text(encoding="utf-8")
    for term in ("4A", "QC Checklist", "Escalation", "Refund / Xu", "Forbidden Wording"):
        assert term in text


def test_music_runtime_untouched():
    changed = _changed_files()
    assert not any(("music" in path.lower() and not path.startswith("tests/")) for path in changed)


def test_product_video_runtime_untouched():
    changed = _changed_files()
    forbidden = ("video_real_render", "video_provider", "video_project", "product_video", "video_product")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_subdub_runtime_untouched():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_payos_pricing_db_untouched():
    changed = " ".join(_changed_files()).lower()
    assert "payos" not in changed
    assert "pricing" not in changed
    assert "migration" not in changed


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.sent = None

    async def get_me(self):
        return _obj(id=999, username="toanaasbot", can_connect_to_business=True)

    async def get_webhook_info(self):
        return _obj(allowed_updates=cskh.BUSINESS_UPDATE_TYPES)
