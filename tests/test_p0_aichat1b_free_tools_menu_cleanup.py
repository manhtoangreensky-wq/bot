import re
import subprocess
from pathlib import Path

from aiedit1_scope_guard import without_aiedit1_scope


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    match = re.search(rf"^def {re.escape(name)}\(.*?^def ", BOT_SOURCE, flags=re.M | re.S)
    if match:
        return match.group(0).rsplit("\ndef ", 1)[0]
    match = re.search(rf"^async def {re.escape(name)}\(.*?^(?:async )?def ", BOT_SOURCE, flags=re.M | re.S)
    if match:
        return match.group(0).rsplit("\ndef ", 1)[0].rsplit("\nasync def ", 1)[0]
    raise AssertionError(f"function not found: {name}")


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_free_tools_menu_has_single_full_width_aichat_button():
    body = _function_source("free_hub_main_keyboard")

    assert '[[InlineKeyboardButton("🤖 Bật AI Chatbot"' in body
    assert 'callback_data="aichat|on"' in body
    assert '"aichat|off"' not in body
    assert '"aichat|assist_on"' not in body


def test_free_tools_menu_removed_extra_support_feedback_and_ai_controls():
    body = _function_source("free_hub_main_keyboard")

    assert "Tắt AI Chatbot" not in body
    assert "Cấp quyền AI hỗ trợ thao tác" not in body
    assert "Hỗ trợ" not in body
    assert "Góp ý / Báo lỗi" not in body
    assert "support|start" not in body
    assert "feedback|start" not in body


def test_aichat_consent_back_stack_goes_to_free_tools_and_main_menu():
    body = _function_source("aichat_consent_keyboard")

    assert 'callback_data="aichat|consent_on"' in body
    assert 'callback_data="aichat|back_freehub"' in body
    assert 'callback_data="menu|main"' in body


def test_aichat_enabled_screen_back_stack_goes_to_free_tools_and_main_menu():
    body = _function_source("aichat_control_keyboard")

    assert 'callback_data="aichat|back_freehub"' in body
    assert 'callback_data="menu|main"' in body
    assert 'callback_data="aichat|off"' in body
    assert 'callback_data="aichat|assist_on"' in body


def test_aichat_callback_back_route_returns_free_tools_without_cross_route():
    body = _function_source("handle_aichat_callback")

    assert 'if action == "back_freehub"' in body
    assert "free_hub_main_text(lang)" in body
    assert "free_hub_main_keyboard(lang)" in body
    assert 'if action in {"assist_on", "assist_off"}' in body
    assert 'if action == "off"' in body
    assert "menu|main_video" not in body
    assert "menu|main_music" not in body
    assert "invoice" not in body.lower()


def test_aichat1b_scope_guard_only_touches_menu_cleanup_files():
    allowed = {
        "bot.py",
        "docs/superpowers/plans/2026-08-02-p0-cskh-continuity.md",
        "docs/superpowers/specs/2026-08-02-p0-cskh-continuity-design.md",
        "knowledge/toan_aas_cskh_aichat_context.md",
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/cskh_session_memory.py",
        "services/telegram_business_support.py",
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
        "tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
        "tests/test_p0_cskh_continuity_unified.py",
    }

    assert without_aiedit1_scope(_changed_files()).issubset(allowed)
