import re
import subprocess
from pathlib import Path

import pytest

from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


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


def _assert_reply_safe(result):
    reply = result["reply"]
    assert cskh.public_reply_is_safe(reply), reply
    assert result.get("playbook_policy_claims", {}).get("unsafe") is False
    assert "đã hoàn" not in reply.lower()
    assert "đã cộng xu" not in reply.lower()
    assert "chắc chắn hoàn" not in reply.lower()


def test_cskh6_playbook_is_curated_not_raw_script_ingested():
    playbook = cskh.load_playbook()
    status = cskh.playbook_status(playbook)

    assert playbook["raw_script_auto_ingest"] is False
    assert status["scenario_count"] >= 12
    assert status["unsafe_unverified_claims_count"] == 0
    assert status["policy_confirm_scenario_count"] >= 4
    assert {"acknowledge", "mirror", "verified_answer", "next_action", "handoff_if_needed"} <= set(
        playbook["response_framework"]["steps"]
    )
    assert {
        "safe_public_fact",
        "config_priced_fact",
        "admin_action_required",
        "policy_confirm_required",
        "never_auto_promise",
    } <= cskh.playbook_policy_claim_categories(playbook)


@pytest.mark.parametrize(
    ("text", "scenario_id", "must_contain"),
    [
        ("này sử dụng sao anh", "new_user_how_to_use", ("video", "ảnh")),
        ("tạo video giá sao", "video_sales_consulting", ("video", "sản phẩm")),
        ("1 Xu bằng bao nhiêu", "xu_conversion_safe", ("1 Xu = 100đ", "Nạp Xu")),
        ("tạo ảnh AI giá sao", "image_ai_safe", ("ảnh", "prompt")),
        ("ảnh rồi ghép video được không", "img2vid_safe", ("ảnh", "mấy giây")),
        ("phụ đề với lồng tiếng bao nhiêu", "subdub_combo_safe", ("phụ đề", "lồng tiếng")),
        ("clone giọng của tôi giá sao", "voice_clone_safe", ("file ghi âm", "chưa báo giá")),
    ],
)
def test_cskh6_human_touch_product_replies(text, scenario_id, must_contain):
    result = _classify(text)

    assert result["playbook_scenario_id"] == scenario_id
    _assert_reply_safe(result)
    for expected in must_contain:
        assert expected in result["reply"]


def test_cskh6_xu_conversion_uses_verified_pricing_doc_rate():
    result = _classify("1 Xu bằng bao nhiêu tiền")

    assert result["intent_id"] == "pricing_topup"
    assert result["playbook_scenario_id"] == "xu_conversion_safe"
    assert "1 Xu = 100đ" in result["reply"]
    assert "pricing_doc" in result["source"]


@pytest.mark.parametrize(
    ("text", "scenario_id", "requires_handoff"),
    [
        ("em nạp tiền rồi nhưng không nhận bonus", "payment_issue_handoff", True),
        ("video bị kẹt không ra file", "technical_failure_safe", True),
        ("giá mắc quá bên khác free", "price_objection", False),
        ("app lừa đảo à tôi bóc phốt", "angry_customer_deescalation", True),
        ("tôi sẽ đăng bài bóc phốt", "public_complaint_safe", True),
        ("khách VIP có giảm không", "vip_loyalty_safe", True),
    ],
)
def test_cskh6_sensitive_cases_handoff_without_overpromising(text, scenario_id, requires_handoff):
    result = _classify(text)

    assert result["playbook_scenario_id"] == scenario_id
    assert result["handoff_required"] is requires_handoff
    assert result["ticket_required"] is requires_handoff
    if requires_handoff:
        assert result.get("ticket_preview")
    _assert_reply_safe(result)


def test_cskh6_policy_guard_blocks_fake_refunds_bonus_vouchers_and_prices():
    assert cskh.detect_policy_claims("Dạ em đã hoàn Xu cho mình rồi ạ")["unsafe"] is True
    assert cskh.detect_policy_claims("Em tặng voucher cho mình luôn")["unsafe"] is True
    assert cskh.detect_policy_claims("Dạ em tặng Xu bonus thêm cho mình")["unsafe"] is True
    assert cskh.detect_policy_claims("Gói này 100k làm được ngay")["unsafe"] is True
    assert cskh.detect_policy_claims("Em chưa tự hứa VIP/giảm giá khi chưa có chính sách xác nhận")["unsafe"] is False


def test_cskh6_test_message_classifies_without_sending():
    result = cskh.playbook_test_message("tạo video giá sao")

    assert result["intent_id"] == "product_video_pricing"
    assert result["playbook_scenario_id"] == "video_sales_consulting"
    assert result["policy_claims"]["unsafe"] is False
    assert result["status"]["scenario_count"] >= 12
    assert "sent" not in result


def test_cskh6_scope_guard_cskh_only_no_locked_runtime_touched():
    changed = set(_changed_files())
    allowed = {
        "bot.py",
        "knowledge/toan_aas_cskh_aichat_context.md",
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/telegram_business_support.py",
        "config/cskh_playbook.json",
        "config/cskh_training_data.json",
        "config/cskh_knowledge_base.json",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
    }
    forbidden_fragments = (
        "music",
        "product_video",
        "img2vid",
        "subdub",
        "voice",
        "payos",
        "pricing",
        "database",
        "wallet",
        "provider",
        "webhook",
        "remote_worker",
        "local_worker",
    )

    assert changed <= allowed
    assert not any(any(fragment in path.lower() for fragment in forbidden_fragments) and not path.startswith("tests/") for path in changed)
