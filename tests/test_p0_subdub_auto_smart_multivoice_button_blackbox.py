"""Acceptance test suite for SubDub Auto Smart MultiVoice Button & Blackbox integration.

TASK: P0.SUBDUB.AUTO.SMART.MULTIVOICE.BUTTON.BLACKBOX.ACCEPTANCE.R1.C1
PROGRAM: P0.SUBDUB.AUTO.SMART.MULTIVOICE.V1
"""

import pytest
from unittest.mock import patch

import bot
from services.subdub_blackboxes import auto_smart_multivoice, auto_multi_speaker


# ===========================================================================
# C2. Test Menu (Voice Keyboards)
# ===========================================================================

def test_c2_video_dubbing_voice_keyboard_button_order_and_count():
    """Verify video_dubbing_voice_keyboard contains exactly 1 smart button with canonical callback in exact order."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {"mode": "dub", "video_processing_mode": "dub"}
        markup = bot.video_dubbing_voice_keyboard("vi", state, include_auto=True)
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        callbacks = [btn.callback_data for btn in buttons]

        # SMART_BUTTON_COUNT=1
        smart_btns = [btn for btn in buttons if btn.callback_data == "videodub|voice|auto_smart_multivoice"]
        assert len(smart_btns) == 1, f"Expected 1 Smart button, found {len(smart_btns)}"
        assert smart_btns[0].text == "✨ Tự động thông minh (Smart Multi)"

        # Canonical button sequence: female, male, auto2, automulti, smart, saved, create
        expected_callbacks = [
            "videodub|voice|default_female",
            "videodub|voice|default_male",
            "videodub|voice|auto_speaker_gender",
            "videodub|voice|auto_multi_speaker",
            "videodub|voice|auto_smart_multivoice",
            "videodub|voice_saved",
            "videodub|voice_create",
        ]
        indices = [callbacks.index(cb) for cb in expected_callbacks]
        assert indices == sorted(indices), f"Button callbacks not in required order: {callbacks}"


def test_c2_subtitle_plus_dub_voice_keyboard_button_order_and_count():
    """Verify subtitle_plus_dub_voice_keyboard contains exactly 1 smart button with canonical callback in exact order."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {
            "mode": "dub",
            "video_processing_mode": "dub",
            "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        }
        markup = bot.subtitle_plus_dub_voice_keyboard("vi", state, include_auto=True)
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        callbacks = [btn.callback_data for btn in buttons]

        smart_btns = [btn for btn in buttons if btn.callback_data == "videodub|voice|auto_smart_multivoice"]
        assert len(smart_btns) == 1, f"Expected 1 Smart button, found {len(smart_btns)}"
        assert smart_btns[0].text == "✨ Tự động thông minh (Smart Multi)"

        expected_callbacks = [
            "videodub|voice|default_female",
            "videodub|voice|default_male",
            "videodub|voice|auto_speaker_gender",
            "videodub|voice|auto_multi_speaker",
            "videodub|voice|auto_smart_multivoice",
            "videodub|voice_saved",
            "videodub|voice_library",
        ]
        indices = [callbacks.index(cb) for cb in expected_callbacks]
        assert indices == sorted(indices), f"Button callbacks not in required order: {callbacks}"


# ===========================================================================
# C3. Test Explicit Smart Selection
# ===========================================================================

def test_c3_explicit_smart_selection_canonical_state():
    """Verify selecting auto_smart_multivoice sets canonical state fields and purges manual fields."""
    state = {
        "mode": "dub",
        "voice_style": "Custom Voice",
        "selected_voice_id": "v-12345",
        "voice_id": "v-12345",
    }
    applied = bot.subdub_apply_voice_choice(state, "auto_smart_multivoice", activation_enabled=True)
    assert applied is not None
    assert applied.get("voice_kind") == "auto_speaker_gender"
    assert applied.get("voice_selection_mode") == "auto_speaker"
    assert applied.get("auto_speaker_lane") == auto_smart_multivoice.AUTO_SMART_MULTIVOICE_LANE
    assert applied.get("auto_smart_multivoice_opt_in") is True

    # No stale manual voice fields
    assert "voice_style" not in applied
    assert "selected_voice_id" not in applied
    assert "voice_id" not in applied


# ===========================================================================
# C4. Test Routing
# ===========================================================================

def test_c4_smart_routing_decision_and_runner():
    """Verify explicit Smart state routes to auto_smart_multivoice with explicit_smart_multivoice_opt_in."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "auto_speaker_lane": auto_smart_multivoice.AUTO_SMART_MULTIVOICE_LANE,
            "auto_smart_multivoice_opt_in": True,
        }
        engine, reason = bot.subdub_auto_routing_decision(state)
        assert engine == "auto_smart_multivoice"
        assert reason == "explicit_smart_multivoice_opt_in"

        runner = bot.subdub_auto_blackbox_runner(state)
        assert runner == auto_smart_multivoice.run_auto_smart_multivoice_blackbox


# ===========================================================================
# C5. Unselected / Default / Non-Smart States Never Route to Smart
# ===========================================================================

@pytest.mark.parametrize("state", [
    {"mode": "dub"},
    {"mode": "dub", "voice_kind": "default_female"},
    {"mode": "dub", "voice_kind": "default_male"},
    {"mode": "dub", "voice_kind": "saved_voice"},
    {"mode": "dub", "voice_kind": "custom_prompt"},
    {"mode": "dub", "voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker"},
    {"mode": "dub", "voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker", "auto_speaker_lane": "multi"},
])
def test_c5_non_smart_states_never_route_to_smart(state):
    """Verify that unselected and non-smart states never route to auto_smart_multivoice."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        engine, _ = bot.subdub_auto_routing_decision(state)
        assert engine != "auto_smart_multivoice", f"State {state} incorrectly routed to Smart!"


# ===========================================================================
# C6. Auto-2 Protected (Switch Smart -> Auto-2)
# ===========================================================================

def test_c6_switch_from_smart_to_auto2_clears_smart_state():
    """Verify switching from Smart to Auto-2 purges auto_smart_multivoice_opt_in and routes to auto_speaker."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {"mode": "dub"}
        state = bot.subdub_apply_voice_choice(state, "auto_smart_multivoice", activation_enabled=True)
        assert state.get("auto_smart_multivoice_opt_in") is True

        state = bot.subdub_apply_voice_choice(state, "auto_speaker_gender", activation_enabled=True)
        assert state is not None
        assert state.get("voice_kind") == "auto_speaker_gender"
        assert not state.get("auto_speaker_lane")

        # REQUIRED CONTRACT: auto_smart_multivoice_opt_in must NOT remain truthy
        assert not state.get("auto_smart_multivoice_opt_in"), "auto_smart_multivoice_opt_in leaked into Auto-2 state!"

        engine, _ = bot.subdub_auto_routing_decision(state)
        assert engine == "auto_speaker", f"Expected route auto_speaker, got {engine}!"


# ===========================================================================
# C7. Auto-Multi Protected (Switch Smart -> Auto-Multi)
# ===========================================================================

def test_c7_switch_from_smart_to_automulti_clears_smart_state():
    """Verify switching from Smart to Auto-Multi purges auto_smart_multivoice_opt_in and routes to multi."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {"mode": "dub"}
        state = bot.subdub_apply_voice_choice(state, "auto_smart_multivoice", activation_enabled=True)
        assert state.get("auto_smart_multivoice_opt_in") is True

        state = bot.subdub_apply_voice_choice(state, "auto_multi_speaker", activation_enabled=True)
        assert state is not None
        assert state.get("auto_speaker_lane") == auto_multi_speaker.AUTO_MULTI_SPEAKER_LANE

        # REQUIRED CONTRACT: auto_smart_multivoice_opt_in must NOT remain truthy
        assert not state.get("auto_smart_multivoice_opt_in"), "auto_smart_multivoice_opt_in leaked into Auto-Multi state!"

        engine, _ = bot.subdub_auto_routing_decision(state)
        assert engine in {"auto_multi_speaker", "auto_multi_speaker_v2"}
        assert engine != "auto_smart_multivoice"


# ===========================================================================
# C8. Switching Matrix (All Transitions)
# ===========================================================================

@pytest.mark.parametrize("from_choice,to_choice", [
    ("default_female", "auto_smart_multivoice"),
    ("auto_speaker_gender", "auto_smart_multivoice"),
    ("auto_multi_speaker", "auto_smart_multivoice"),
    ("auto_smart_multivoice", "default_female"),
    ("auto_smart_multivoice", "auto_speaker_gender"),
    ("auto_smart_multivoice", "auto_multi_speaker"),
])
def test_c8_switching_matrix_state_isolation(from_choice, to_choice):
    """Verify all transitions to and from Smart maintain exactly one active voice mode and 0 leaks."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {"mode": "dub"}
        state = bot.subdub_apply_voice_choice(state, from_choice, activation_enabled=True)
        assert state is not None

        state = bot.subdub_apply_voice_choice(state, to_choice, activation_enabled=True)
        assert state is not None

        engine, _ = bot.subdub_auto_routing_decision(state)
        if to_choice == "auto_smart_multivoice":
            assert state.get("auto_smart_multivoice_opt_in") is True
            assert engine == "auto_smart_multivoice"
        else:
            assert not state.get("auto_smart_multivoice_opt_in"), f"Leaked auto_smart_multivoice_opt_in when switching to {to_choice}!"
            assert engine != "auto_smart_multivoice", f"Wrong engine {engine} when switched to {to_choice}!"


# ===========================================================================
# C9. Confirmation Text
# ===========================================================================

def test_c9_confirmation_text_displays_smart_choice():
    """Verify confirm texts display Smart choice in vi and en without confusing Auto-2 or Auto-Multi."""
    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        state = {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "auto_speaker_lane": auto_smart_multivoice.AUTO_SMART_MULTIVOICE_LANE,
            "auto_smart_multivoice_opt_in": True,
            "target_language": "vi",
        }
        text_vi = bot.video_dubbing_confirm_text(state, "vi")
        assert "✨ Tự động thông minh (Smart Multi)" in text_vi
        assert "👥 Tự động 2 giọng" not in text_vi
        assert "👥 Tự động nhiều giọng" not in text_vi

        sub_text_vi = bot.subtitle_plus_dub_confirm_text(state, "vi")
        assert "✨ Tự động thông minh (Smart Multi)" in sub_text_vi

        text_en = bot.video_dubbing_confirm_text(state, "en")
        assert "✨ Auto Smart Multi" in text_en


# ===========================================================================
# C10. Voice-Create Label Regression
# ===========================================================================

def test_c10_voice_create_label_regression():
    """Verify regression lock on standalone voice create button label."""
    from tests.test_p0_subdub_two_speaker_live_ui_lock import (
        test_standalone_voice_create_button_does_not_claim_to_send_another_video,
    )
    test_standalone_voice_create_button_does_not_claim_to_send_another_video()
