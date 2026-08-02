from services import aas_shared_knowledge as shared
from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


RUNTIME_FACTS = {
    "available": True,
    "source": "runtime_canonical",
    "xu_to_vnd": 100,
    "image_tiers": [("Ảnh tiết kiệm", 51), ("Ảnh cao", 601)],
    "video_tiers": [("Cơ bản", 333)],
    "scene_seconds": 6,
    "subtitle_rate": 0.1,
    "dub_rate": 0.1,
}


def _enabled_aichat_state(user_id: str = "continuity-user") -> dict:
    state = aichat.default_state()
    state, _result = aichat.enable_with_consent(state, user_id)
    return state


def test_human_touch_runtime_facts_are_shared_by_all_reply_surfaces():
    shared_result = shared.classify_shared_answer("Tạo video bao nhiêu", runtime_facts=RUNTIME_FACTS)
    business_result = cskh.classify_cskh_message("Tạo video bao nhiêu", runtime_facts=RUNTIME_FACTS)
    state = _enabled_aichat_state()
    _state, aichat_result = aichat.process_message(
        state,
        "continuity-user",
        "Tạo video bao nhiêu",
        queue_unknown=False,
        runtime_facts=RUNTIME_FACTS,
    )

    assert shared_result["reply"] == business_result["reply"] == aichat_result["reply"]
    for result in (shared_result, business_result, aichat_result):
        assert result["pricing_source"] == "runtime_canonical"
        assert "333 Xu" in result["reply"]
        assert "1 cảnh = 6s" in result["reply"]
        assert "200 Xu" not in result["reply"]


def test_human_touch_explicit_unavailable_facts_never_fall_back_to_static_prices():
    unavailable = {"available": True, "source": "runtime_canonical"}
    shared_result = shared.classify_shared_answer("Tạo ảnh bao nhiêu", runtime_facts=unavailable)
    business_result = cskh.classify_cskh_message("Tạo ảnh bao nhiêu", runtime_facts=unavailable)
    state = _enabled_aichat_state()
    _state, aichat_result = aichat.process_message(
        state,
        "continuity-user",
        "Tạo ảnh bao nhiêu",
        queue_unknown=False,
        runtime_facts=unavailable,
    )

    for result in (shared_result, business_result, aichat_result):
        assert result["pricing_source"] == "runtime_unavailable"
        assert result["reply"] == shared.PRICE_UNKNOWN_SAFE_REPLY
        for stale_price in ("50 Xu", "150 Xu", "600 Xu"):
            assert stale_price not in result["reply"]


def test_human_touch_complaint_apologizes_first_without_unverified_promise():
    result = shared.classify_shared_answer("Bot trừ Xu mà không ra video", runtime_facts=RUNTIME_FACTS)
    folded = cskh._fold(result["reply"])

    assert result["reply"].startswith("Dạ em xin lỗi")
    assert "da hoan xu" not in folded
    assert "da cong xu" not in folded
    assert "hoan/no-charge" not in folded
    assert "voucher" not in folded
    assert "vip" not in folded


def test_human_touch_pack_covers_capabilities_policy_escalation_voice_and_subdub():
    capabilities = cskh.classify_cskh_message("Bạn có thể biết gì", runtime_facts=RUNTIME_FACTS)
    bonus = cskh.classify_cskh_message("Nạp MoMo sao không bonus", runtime_facts=RUNTIME_FACTS)
    manager = cskh.classify_cskh_message("Tôi muốn gặp quản lý", runtime_facts=RUNTIME_FACTS)
    voice = cskh.classify_cskh_message("Chọn giọng nữ mà ra nam", runtime_facts=RUNTIME_FACTS)
    subdub = cskh.classify_cskh_message(
        "Phụ đề + lồng tiếng 2000 ký tự",
        runtime_facts=RUNTIME_FACTS,
    )

    assert capabilities["intent_id"] == "ask_capabilities"
    assert "TOAN AAS" in capabilities["reply"]
    assert bonus["intent_id"] == "payment_bonus_question"
    assert "không tự hứa" in bonus["reply"].lower()
    assert manager["intent_id"] == "admin_handoff"
    assert "admin" in manager["reply"].lower()
    assert voice["intent_id"] == "voice_tts_error"
    assert "giọng" in voice["reply"].lower()
    assert "video" not in voice["reply"].lower()
    assert subdub["intent_id"] == "subdub_pricing"
    assert "400 Xu" in subdub["reply"]
    assert subdub["pricing_source"] == "runtime_canonical"


def test_human_touch_public_guard_rejects_required_banned_copy_and_private_paths():
    forbidden_replies = (
        "Không phải lỗi bên em.",
        "Do provider lỗi.",
        "Chắc được hoàn Xu.",
        "Em tặng anh Xu.",
        "Anh bấm sai rồi.",
        "Chờ đi.",
        "Không làm được.",
        "Xem log tại C:\\private\\bot.log.",
    )

    for reply in forbidden_replies:
        assert not cskh.public_reply_is_safe(reply)


def test_human_touch_prompt_caption_and_script_are_usable_drafts_without_side_effects():
    prompt = shared.classify_shared_answer("Tạo prompt video nước hoa nam", runtime_facts=RUNTIME_FACTS)
    caption = shared.classify_shared_answer("Viết caption cho serum dưỡng ẩm", runtime_facts=RUNTIME_FACTS)
    script = shared.classify_shared_answer("Viết kịch bản video cho cà phê rang xay", runtime_facts=RUNTIME_FACTS)

    assert "nước hoa nam" in prompt["reply"].lower()
    assert "9:16" in prompt["reply"]
    assert "serum dưỡng ẩm" in caption["reply"].lower()
    assert "#" in caption["reply"]
    assert "cảnh 1" in script["reply"].lower()
    for result in (prompt, caption, script):
        assert result["intent_id"] == "prompt_create_request"
        assert cskh.public_reply_is_safe(result["reply"])
