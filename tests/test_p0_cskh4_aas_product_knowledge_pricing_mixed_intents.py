import asyncio
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from services import telegram_business_support as cskh
from tests.aiedit1_scope_guard import without_aiedit1_scope


ROOT = Path(__file__).resolve().parents[1]
KB_PATH = ROOT / "config" / "cskh_knowledge_base.json"
CSKH4_TEST = "tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py"


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


def _kb():
    return json.loads(KB_PATH.read_text(encoding="utf-8"))


def _product(product_id):
    return _kb()["products"][product_id]


def _classify(text):
    return cskh.classify_cskh_message(text, variation_seed=text)


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _event(text="cái ảnh với video ấy"):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id="business-connection-abcdef123456",
        chat_id="123456789",
        from_user_id="111",
        from_is_bot=False,
        text=text,
        caption="",
        message_id="1",
        timestamp=1000,
        media_type="",
    )


def _run(coro):
    return asyncio.run(coro)


def test_cskh4_product_matrix_contains_video_ai():
    item = _product("product_video")
    assert "video" in item["aliases"]
    assert item["pricing_source_key"] == "product_video"


def test_cskh4_product_matrix_contains_image_ai():
    item = _product("image_ai")
    assert "ảnh AI" in item["aliases"]
    assert item["next_question"]


def test_cskh4_product_matrix_contains_img2vid():
    item = _product("image_to_video")
    assert "ghép ảnh" in item["aliases"]
    assert "số lượng ảnh" in item["required_inputs"]


def test_cskh4_product_matrix_contains_subdub():
    item = _product("subdub")
    assert "phụ đề" in item["aliases"]
    assert "lồng tiếng" in item["aliases"]


def test_cskh4_product_matrix_contains_payment():
    item = _product("payment_xu")
    assert item["handoff_required"] is True
    assert "ảnh bill hoặc mã giao dịch" in item["required_inputs"]


def test_cskh4_each_product_has_aliases_required_inputs_next_question():
    for product_id, item in _kb()["products"].items():
        assert item["canonical_product_id"] == product_id
        assert item["aliases"], product_id
        assert item["required_inputs"], product_id
        assert item["next_question"], product_id
        assert item["pricing_source_key"], product_id
        assert "price_unknown_safe_reply" in item


def test_cskh4_gia_anh_classifies_image_pricing():
    result = _classify("giá ảnh sao em")
    assert result["intent_id"] == "image_ai_pricing"
    assert result["primary_product"] == "image_ai"


def test_cskh4_video_va_anh_classifies_mixed_product():
    result = _classify("video và ảnh em")
    assert result["intent_id"] == "mixed_product_pricing"
    assert result["mixed_intent"] is True
    assert result["primary_product"] == "product_video"
    assert "image_ai" in result["secondary_products"]


def test_cskh4_anh_roi_ghep_video_classifies_img2vid():
    result = _classify("ảnh rồi ghép video được không")
    assert result["intent_id"] == "image_to_video_pricing"
    assert result["primary_product"] == "image_to_video"


def test_cskh4_tao_anh_ai_gia_sao_classifies_image_ai_pricing():
    assert _classify("tạo ảnh AI giá sao")["intent_id"] == "image_ai_pricing"


def test_cskh4_phu_de_gia_sao_classifies_subtitle_pricing():
    assert _classify("phụ đề giá sao")["intent_id"] == "subtitle_pricing"


def test_cskh4_long_tieng_gia_sao_classifies_dub_pricing():
    assert _classify("lồng tiếng giá sao")["intent_id"] == "dub_pricing"


def test_cskh4_bot_rieng_gia_sao_classifies_private_bot():
    result = _classify("bot riêng giá sao")
    assert result["intent_id"] == "bot_private_pricing"
    assert result["handoff_required"] is True


def test_cskh4_unknown_price_does_not_invent_number():
    reply = _classify("dịch vụ kia giá sao")["reply"]
    assert not re.search(r"\b\d+[\d.,]*(?:\s*(?:xu|vnd|đ|k|tr|triệu))?\b", reply.lower())


def test_cskh4_reply_gia_anh_specific_and_natural():
    reply = _classify("giá ảnh sao em")["reply"]
    assert "tạo/chỉnh ảnh AI" in reply
    assert "50 Xu" in reply
    assert "600 Xu" in reply
    assert "hóa đơn" in reply


def test_cskh4_reply_video_va_anh_combo():
    reply = _classify("video và ảnh em")["reply"]
    assert "tạo ảnh trước" in reply
    assert "làm video AI từ ảnh" in reply


def test_cskh4_reply_anh_roi_ghep_video():
    reply = _classify("ảnh rồi ghép video được không")["reply"]
    assert "đã có ảnh sẵn" in reply
    assert "bao nhiêu ảnh" in reply
    assert "mấy giây" in reply


def test_cskh4_reply_phu_de_long_tieng():
    reply = _classify("phụ đề với lồng tiếng bao nhiêu")["reply"]
    assert "phụ đề" in reply
    assert "lồng tiếng" in reply
    assert "0.1 Xu/ký tự" in reply or "0.10 Xu/ký tự" in reply


def test_cskh4_reply_video_missing_file_asks_job_code():
    result = _classify("video xong chưa thấy file")
    assert result["intent_id"] == "product_video_failed_no_file"
    assert "mã xử lý" in result["reply"]
    assert "video" in result["reply"].lower()


def test_cskh4_replies_no_internal_terms():
    replies = [
        _classify("giá ảnh sao em")["reply"],
        _classify("video và ảnh em")["reply"],
        _classify("phụ đề với lồng tiếng bao nhiêu")["reply"],
    ]
    assert all(cskh.public_reply_is_safe(reply) for reply in replies)


def test_cskh4_replies_no_unapproved_refund_promise():
    joined = " ".join(
        _classify(text)["reply"]
        for text in ["video xong chưa thấy file", "nạp tiền chưa thấy Xu", "hoàn Xu đi"]
    ).lower()
    assert "đã hoàn" not in joined
    assert "đã cộng xu" not in joined
    assert "chắc chắn hoàn" not in joined


def test_cskh4_mixed_video_image_not_unknown():
    assert _classify("video và ảnh em")["intent_id"] != "out_of_scope"


def test_cskh4_mixed_subtitle_dub_not_unknown():
    result = _classify("phụ đề với lồng tiếng bao nhiêu")
    assert result["intent_id"] == "subdub_pricing"
    assert result["mixed_intent"] is True


def test_cskh4_mixed_video_logo_subtitle_not_unknown():
    result = _classify("video có logo và phụ đề")
    assert result["intent_id"] == "mixed_product_pricing"
    assert "subdub" in result["secondary_products"]


def test_cskh4_mixed_payment_plus_video_prioritizes_payment_support():
    result = _classify("nạp tiền rồi tạo video")
    assert result["intent_id"] == "payment_xu_not_received"
    assert result["primary_product"] == "payment_xu"


def test_cskh4_mixed_intent_asks_one_next_question():
    result = _classify("video và ảnh em")
    assert result["next_question"]
    assert result["reply"].count("?") + result["reply"].count("ạ?") <= 2


def test_cskh4_synonyms_video():
    for text in ["clip giá sao", "trailer giá sao", "tiktok video giá sao"]:
        assert _classify(text)["primary_product"] == "product_video"


def test_cskh4_synonyms_image():
    for text in ["hình ảnh giá sao", "avatar giá sao", "logo giá sao"]:
        assert _classify(text)["intent_id"] == "image_ai_pricing"


def test_cskh4_synonyms_img2vid():
    for text in ["slideshow bao nhiêu", "video từ ảnh được không", "ảnh chạy giá sao"]:
        assert _classify(text)["primary_product"] == "image_to_video"


def test_cskh4_synonyms_subdub():
    for text in ["subtitle giá sao", "dub giá sao", "voice over giá sao"]:
        assert _classify(text)["primary_product"] == "subdub"


def test_cskh4_synonyms_pricing():
    for text in ["ảnh bao nhiêu", "ảnh nhiêu tiền", "ảnh nhiêu xu", "ảnh phí sao", "gói ảnh rẻ nhất"]:
        assert _classify(text)["intent_id"] == "image_ai_pricing"


def test_cskh4_typo_short_phrases_still_classify():
    assert _classify("ghep anh thanh video bao nhieu")["primary_product"] == "image_to_video"
    assert _classify("sub gia sao")["primary_product"] == "subdub"


def test_cskh4_price_uses_config_when_available():
    result = _classify("ghép ảnh thành video bao nhiêu")
    assert result["pricing_source"] == "config"
    assert "miễn phí tối đa 3 ảnh" in result["reply"]


def test_cskh4_price_unknown_asks_clarification():
    result = _classify("giá ảnh sao em")
    assert result["pricing_source"] == "pricing_doc"
    assert "50 Xu" in result["reply"]
    assert "600 Xu" in result["reply"]


def test_cskh4_price_doc_numbers_are_allowed_for_image():
    reply = _classify("giá ảnh sao em")["reply"].lower()
    for marker in ["50 xu", "150 xu", "600 xu"]:
        assert marker in reply


def test_cskh4_free_only_when_configured():
    assert "miễn phí" in _classify("ghép ảnh thành video bao nhiêu")["reply"].lower()
    assert "tạo/chỉnh ảnh ai" in _classify("giá ảnh sao em")["reply"].lower()


def test_cskh4_pricing_source_debug_present():
    result = _classify("giá ảnh sao em")
    assert result["pricing_source"] in {"config", "runtime", "unknown", "pricing_doc"}


def test_cskh4_test_thread_outputs_primary_product(monkeypatch):
    text = _run_cskh_test_thread(monkeypatch, "alo | giá ảnh sao em")
    assert "Primary product:" in text
    assert "image_ai" in text


def test_cskh4_test_thread_outputs_pricing_source(monkeypatch):
    text = _run_cskh_test_thread(monkeypatch, "ghép ảnh thành video bao nhiêu")
    assert "Pricing source:" in text
    assert "config" in text


def test_cskh4_test_thread_outputs_matched_aliases(monkeypatch):
    text = _run_cskh_test_thread(monkeypatch, "video và ảnh em")
    assert "Matched aliases:" in text
    assert "video" in text


def test_cskh4_existing_cskh_test_still_works(monkeypatch):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    _run(bot.cmd_cskh_test(update, _obj(args=["nạp", "Xu", "chưa", "cộng"])))
    payload = update.message.replies[-1][0]
    assert "Would send: <code>no</code>" in payload
    assert "Primary product:" in payload


def test_cskh4_low_confidence_product_question_queued():
    result = _classify("bên em có loại kia không")
    state, item = cskh.add_learning_candidate(cskh.default_state(), _event("bên em có loại kia không"), result, text="bên em có loại kia không")
    assert item["id"] in state["learning_queue"]
    assert item["status"] == "open"


def test_cskh4_learning_queue_contains_detected_keywords():
    result = _classify("bên em có loại kia không")
    _state, item = cskh.add_learning_candidate(cskh.default_state(), _event("bên em có loại kia không"), result, text="bên em có loại kia không")
    assert "loai kia" in item["detected_keywords"]


def test_cskh4_learning_queue_no_unreviewed_auto_update():
    result = _classify("bên em có loại kia không")
    state, _item = cskh.add_learning_candidate(cskh.default_state(), _event("bên em có loại kia không"), result, text="bên em có loại kia không")
    assert "intents" not in state


def test_cskh4_learning_queue_masks_chat_id():
    result = _classify("bên em có loại kia không")
    _state, item = cskh.add_learning_candidate(cskh.default_state(), _event("bên em có loại kia không"), result, text="bên em có loại kia không")
    assert item["chat_id_masked"] != "123456789"
    assert "..." in item["chat_id_masked"]


def test_cskh4_no_music_runtime_changes():
    changed = _changed_files()
    assert not any(("music" in path.lower() and not path.startswith("tests/")) for path in changed)


def test_cskh4_no_product_video_runtime_changes():
    changed = _changed_files()
    forbidden = ("video_real_render", "video_provider", "video_project", "video_product")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh4_no_img2vid_runtime_changes():
    changed = _changed_files()
    forbidden = ("img2vid", "image_to_video", "ghep_anh", "storyboard")
    assert not any(any(term in path.lower() for term in forbidden) and not path.startswith("tests/") for path in changed)


def test_cskh4_no_subdub_runtime_changes():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_cskh4_no_voice_runtime_changes():
    changed = _changed_files()
    assert not any(("voice" in path.lower() or "tts" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_cskh4_no_payos_pricing_db_destructive_changes():
    allowed = {
        "docs/superpowers/plans/2026-08-02-p0-cskh-continuity.md",
        "docs/superpowers/specs/2026-08-02-p0-cskh-continuity-design.md",
        CSKH4_TEST,
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/cskh_session_memory.py",
        "services/telegram_business_support.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh_continuity_unified.py",
    }
    changed_files = without_aiedit1_scope(_changed_files())
    changed = " ".join(path for path in changed_files if path not in allowed).lower()
    for forbidden in ("payos", "pricing", "migration", "db"):
        assert forbidden not in changed


def test_cskh4_no_provider_calls():
    changed = _changed_files()
    assert not any(path.startswith("providers/") for path in changed)
    result = _classify("giá ảnh sao em")
    assert result["reply"]


def _run_cskh_test_thread(monkeypatch, text):
    import bot

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = _obj(effective_user=_obj(id=1), message=FakeMessage())
    _run(bot.cmd_cskh_test_thread(update, _obj(args=text.split())))
    assert update.message.replies
    return update.message.replies[-1][0]


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
