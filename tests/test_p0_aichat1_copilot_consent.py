import os
import subprocess
from pathlib import Path

from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AICHAT_COPILOT_STATE_FILE", str(tmp_path / "aichat_state.json"))
    monkeypatch.setenv("CSKH_BUSINESS_STATE_FILE", str(tmp_path / "cskh_state.json"))


def _enabled_state(user_id="101"):
    state = aichat.default_state()
    state, _result = aichat.enable_with_consent(state, user_id)
    return state


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_aichat_on_requires_explicit_consent_before_enable(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state, result = aichat.request_enable(aichat.default_state(), "101")

    assert result["consent_required"] is True
    assert aichat.is_enabled(state, "101") is False
    assert "trước khi trừ Xu hoặc gọi provider" in result["reply"]

    state, enabled = aichat.enable_with_consent(state, "101")
    assert enabled["enabled"] is True
    assert aichat.is_enabled(state, "101") is True


def test_aichat_off_silences_copilot_and_does_not_touch_cskh(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    ai_state = _enabled_state("101")
    cskh_state = {**cskh.default_state(), "enabled": True}

    ai_state, _off = aichat.disable_user(ai_state, "101")
    ai_state, result = aichat.process_message(ai_state, "101", "alo")

    assert result["action_guard"] == "disabled_no_reply"
    assert result["replied"] is False
    assert cskh_state["enabled"] is True


def test_cskh_off_does_not_disable_aichat(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    ai_state = _enabled_state("101")
    cskh_state = {**cskh.default_state(), "enabled": True}

    cskh_state = cskh.set_enabled(cskh_state, False)

    assert cskh_state["enabled"] is False
    assert aichat.is_enabled(ai_state, "101") is True


def test_aichat_uses_cskh_knowledge_for_pricing(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "bang gia")

    assert result["intent_id"] == "pricing_table_general"
    assert "aichat" in result["source"]
    assert "cskh_knowledge" in result["source"]
    assert "pricing" in result["source"]
    assert "TOAN AAS" in result["reply"]
    assert result["provider_call_allowed"] is False


def test_aichat_uses_human_touch_playbook_for_video_error(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "video bi ket khong ra file")

    assert result["intent_id"] == "product_video_failed_no_file"
    assert "cskh_playbook" in result["source"]
    assert result["action_guard"] == "answer_only"
    assert result["reply"].startswith("Dạ")


def test_aichat_image_and_video_real_tasks_prepare_flow_without_provider(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, image = aichat.process_message(state, "101", "tao anh that cho shop")
    assert image["action_guard"] == "needs_action_permission"
    assert image["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert image["provider_call_allowed"] is False
    assert image["xu_charge_allowed"] is False

    state, _permission = aichat.set_action_permission(state, "101", True)
    state, video = aichat.process_message(state, "101", "tao video that cho shop")
    assert video["action_guard"] == "prepare_flow_stop_at_confirm"
    assert video["target_flow"]["callback"] == "menu|main_video"
    assert "màn báo giá hoặc xác nhận" in video["reply"]
    assert video["provider_call_allowed"] is False
    assert video["invoice_confirm_allowed"] is False


def test_aichat_prompt_request_returns_free_text_only(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "viet prompt anh cho nuoc hoa nam")

    assert result["action_guard"] == "free_text_only"
    assert "prompt miễn phí" in result["reply"]
    assert result["provider_call_allowed"] is False
    assert result["xu_charge_allowed"] is False


def test_aichat_refund_policy_does_not_promise_credit(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "hoan xu giup em")
    folded = cskh._fold(result["reply"])

    assert result["action_guard"] == "admin_review_required"
    assert "da hoan xu" not in folded
    assert "da cong xu" not in folded
    assert "admin kiểm tra" in result["reply"]


def test_aichat_internal_provider_api_debug_question_is_blocked(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "bot dang dung provider api debug nao")
    folded = cskh._fold(result["reply"])

    assert result["action_guard"] == "internal_info_blocked"
    assert "provider" not in folded
    assert "api" not in folded
    assert "debug" not in folded


def test_aichat_unknown_goes_to_shared_learning_queue(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")

    state, result = aichat.process_message(state, "101", "toi muon blorb zorx qqq")
    shared = cskh.load_state()
    candidates = cskh.list_learning_candidates(shared, limit=5)

    assert result["learning_candidate_id"]
    assert "learning_queue" in result["source"]
    assert candidates
    assert candidates[0]["why_queued"] == "aichat_unknown_needs_admin_review"


def test_aichat_trace_has_source_permission_and_action_guard(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state("101")
    state, _result = aichat.process_message(state, "101", "bang gia")
    payload = aichat.status_payload(state, "101")
    last = payload["last_trace"]

    assert last["entry"] == "aichat"
    assert "source" in last
    assert last["permission"] == "default_answer"
    assert last["action_guard"] == "answer_only"
    assert last["provider_call_allowed"] is False
    assert last["xu_charge_allowed"] is False


def test_aichat_bot_wiring_and_freehub_buttons_present():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert 'CommandHandler("aichat_on", cmd_aichat_on)' in source
    assert 'CommandHandler("aichat_off", cmd_aichat_off)' in source
    assert 'CommandHandler("aichat_status", cmd_aichat_status)' in source
    assert 'CommandHandler("aichat_test", cmd_aichat_test)' in source
    assert 'CommandHandler("aichat_trace", cmd_aichat_trace)' in source
    assert 'CallbackQueryHandler(handle_aichat_callback, pattern=r"^aichat\\|")' in source
    assert "Bật AI Chatbot" in source
    assert "Tắt AI Chatbot" in source
    assert "Cấp quyền AI hỗ trợ thao tác" in source


def test_aichat_scope_guard_only_touches_aichat_bot_and_tests():
    allowed = {
        "bot.py",
        "knowledge/toan_aas_cskh_aichat_context.md",
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/telegram_business_support.py",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
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

    assert set(_changed_files()).issubset(allowed)
