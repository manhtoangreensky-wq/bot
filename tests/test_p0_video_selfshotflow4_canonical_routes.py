from __future__ import annotations

from pathlib import Path

import pytest

from services import video_selfshotflow4


def _state(flow: str, *, with_tracks: bool = True) -> dict:
    person_tracks = [{"subject_id": "person-1", "subject_type": "person", "description": "người trong video", "label": "Người trong video"}] if with_tracks else []
    object_tracks = [{"subject_id": "object-1", "subject_type": "object", "description": "sản phẩm trong video", "label": "Sản phẩm"}] if with_tracks else []
    return {
        video_selfshotflow4.FLOW_FLAGS[flow]: True,
        video_selfshotflow4.FLOW_SCREEN_KEYS[flow]: "segment",
        "source_asset": {"file_id": f"{flow}-source", "duration_seconds": 16, "width": 1080, "height": 1920, "audio_streams": 1},
        "source_analysis": {
            "source_hash": f"{flow}-hash",
            "duration_seconds": 16,
            "width": 1080,
            "height": 1920,
            "audio_manifest": {"stream_count": 1},
            "person_tracks": person_tracks,
            "object_tracks": object_tracks,
            "product_tracks": [],
            "pet_tracks": [],
            "interaction_graph": [],
            "main_actions": ["đi bộ và giới thiệu sản phẩm"],
        },
        "source_ratio": "9:16",
    }


def _open_subject(flow: str, state: dict) -> dict:
    target = "mode" if flow == "ss3" else "subject"
    result = video_selfshotflow4.apply_action(flow, state, "c4show", target)
    assert result["screen"] == target
    if flow == "ss3":
        result = video_selfshotflow4.apply_action(flow, result["state"], "c4mode", "one_take")
        assert result["screen"] == "subject"
    return result["state"]


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_canonical_flow_reaches_prompt_and_tail_without_side_effects(flow: str):
    state = _state(flow)
    result = video_selfshotflow4.apply_action(flow, state, "c4segment", "whole")
    assert result["screen"] == "analysis"

    state = _open_subject(flow, result["state"])

    result = video_selfshotflow4.apply_action(flow, state, "c4subject", "track:person-1")
    assert result["screen"] == "content_source"

    result = video_selfshotflow4.apply_action(flow, result["state"], "c4source", "profiles")
    assert result["screen"] == "profiles"

    result = video_selfshotflow4.apply_action(flow, result["state"], "c4profile", "0")
    assert result["screen"] == "prompt"
    prompt_model = video_selfshotflow4.screen_model(flow, "prompt", result["state"])
    assert [label for label, _callback in prompt_model["rows"][0]] == ["1", "2", "3", "4", "5"]
    assert video_selfshotflow4.validate_rows(
        prompt_model["rows"],
        back_callback=f"vproduct|{flow}|c4show|profiles",
    )["ok"]

    result = video_selfshotflow4.apply_action(flow, result["state"], "c4prompt", "1")
    assert result["screen"] == "tail_review"
    final = result["state"]
    assert final["provider_called"] is False
    assert final["job_created"] is False
    assert final["outbox_created"] is False
    assert final["generated_files"] == 0
    assert final["wallet_mutations"] == 0
    assert final["xu_charged"] == 0


def test_ss2_no_tracks_allows_user_confirmed_subject_without_fake_detector_claim():
    state = _state("ss2", with_tracks=False)
    state = video_selfshotflow4.apply_action("ss2", state, "c4segment", "whole")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4show", "subject")["state"]
    result = video_selfshotflow4.apply_action("ss2", state, "c4subject", "person")
    manifest = result["state"]["subject_manifest"]
    assert result["screen"] == "content_source"
    assert manifest["subjects"][0]["provenance"] == "user_confirmed_source_bound"


def test_subject_layout_stays_two_buttons_per_row_when_detection_count_is_odd():
    state = _state("ss2")
    state["source_analysis"]["object_tracks"] = []
    state[video_selfshotflow4.FLOW_SCREEN_KEYS["ss2"]] = "subject"
    model = video_selfshotflow4.screen_model("ss2", "subject", state)
    subject_rows = model["rows"][:-1]
    assert all(len(row) == 2 for row in subject_rows)
    assert any(label == "🚫 Không có nhân vật chính" for row in subject_rows for label, _callback in row)

    state = video_selfshotflow4.apply_action("ss2", state, "c4subject", "none")["state"]
    assert state["subject_manifest"]["selection_mode"] == "motion_only"


def test_ss3_no_tracks_keeps_user_confirmation_instead_of_forcing_description():
    state = _state("ss3", with_tracks=False)
    state = video_selfshotflow4.apply_action("ss3", state, "c4segment", "whole")["state"]
    state = _open_subject("ss3", state)
    result = video_selfshotflow4.apply_action("ss3", state, "c4subject", "person")
    manifest = result["state"]["subject_manifest"]
    assert result["screen"] == "content_source"
    assert manifest["user_confirmed_source_bound"] is True


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_skip_always_keeps_a_nonempty_prompt(flow: str):
    state = _state(flow)
    state = video_selfshotflow4.apply_action(flow, state, "c4segment", "whole")["state"]
    state = _open_subject(flow, state)
    state = video_selfshotflow4.apply_action(flow, state, "c4subject", "person")["state"]
    state = video_selfshotflow4.apply_action(flow, state, "c4source", "custom")["state"]
    state = video_selfshotflow4.apply_text(flow, state, "content", "Biến đổi thế giới quanh chủ thể nhưng giữ hành động nguồn.")["state"]
    result = video_selfshotflow4.apply_action(flow, state, "c4prompt", "skip")
    assert result["screen"] == "tail_review"
    assert result["state"]["selected_prompt"]["text"]


def test_ss3_creates_exactly_four_transformation_stages():
    state = _state("ss3")
    state = video_selfshotflow4.apply_action("ss3", state, "c4segment", "whole")["state"]
    state = _open_subject("ss3", state)
    state = video_selfshotflow4.apply_action("ss3", state, "c4subject", "person")["state"]
    state = video_selfshotflow4.apply_action("ss3", state, "c4source", "ideas")["state"]
    state = video_selfshotflow4.apply_action("ss3", state, "c4idea", "0")["state"]
    result = video_selfshotflow4.apply_action("ss3", state, "c4prompt", "1")
    assert len(result["state"]["transformation_stages"]) == 4


def test_stale_show_callback_cannot_jump_to_an_unrelated_screen():
    state = _state("ss2")
    result = video_selfshotflow4.apply_action("ss2", state, "c4show", "prompt")
    assert result["screen"] == "segment"

    result = video_selfshotflow4.apply_action("ss2", state, "c4show", "mode")
    assert result["screen"] == "segment"

    result = video_selfshotflow4.apply_action("ss2", state, "c4source", "profiles")
    assert result["screen"] == "segment"
    assert "selected_content" not in result["state"]


def test_invalid_selfshot_callback_values_keep_the_exact_current_screen():
    state = _state("ss2")
    state = video_selfshotflow4.apply_action("ss2", state, "c4segment", "whole")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4show", "subject")["state"]
    assert video_selfshotflow4.apply_action("ss2", state, "c4subject", "track:gone")["screen"] == "subject"

    state = video_selfshotflow4.apply_action("ss2", state, "c4subject", "person")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4source", "profiles")["state"]
    assert video_selfshotflow4.apply_action("ss2", state, "c4profile", "not-a-number")["screen"] == "profiles"
    assert video_selfshotflow4.apply_action("ss2", state, "c4profile", "999")["screen"] == "profiles"

    state = video_selfshotflow4.apply_action("ss2", state, "c4profile", "0")["state"]
    assert video_selfshotflow4.apply_action("ss2", state, "c4prompt", "not-a-number")["screen"] == "prompt"


def test_missing_source_duration_stays_in_segment_without_a_generic_error_path():
    state = _state("ss2")
    state["source_analysis"]["duration_seconds"] = "not-a-duration"
    result = video_selfshotflow4.apply_action("ss2", state, "c4segment", "whole")
    assert result["screen"] == "segment"
    assert "source_segment" not in result["state"]


def test_bot_places_the_canonical_owner_before_legacy_selfshot_handlers():
    source = Path("bot.py").read_text(encoding="utf-8")
    for flow in ("ss2", "ss3"):
        marker = f'if video_selfshotflow4.enabled("{flow}", current):'
        start = source.index(marker)
        legacy = source.index("legacy_tail_screen = {", start)
        block = source[start:legacy]
        assert 'if operation.startswith("c4"):' in block
        assert f'video_selfshotflow4.apply_action("{flow}", current, operation, argument)' in block
        assert "return await video_selfshotflow4_handle_result" in block
        assert "read-only" in block


def test_prompt_back_returns_to_the_exact_content_source_that_opened_it():
    state = _state("ss2")
    state = video_selfshotflow4.apply_action("ss2", state, "c4segment", "whole")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4show", "subject")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4subject", "person")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4source", "profiles")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4profile", "0")["state"]
    model = video_selfshotflow4.screen_model("ss2", "prompt", state)
    assert model["rows"][-1][0][1] == "vproduct|ss2|c4show|profiles"


def test_custom_content_is_used_in_prompt_and_escaped_for_telegram_html():
    state = _state("ss2", with_tracks=False)
    state = video_selfshotflow4.apply_action("ss2", state, "c4segment", "whole")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4show", "subject")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4subject", "person")["state"]
    state = video_selfshotflow4.apply_action("ss2", state, "c4source", "custom")["state"]
    state = video_selfshotflow4.apply_text("ss2", state, "content", "Câu chuyện <liền mạch>")["state"]
    model = video_selfshotflow4.screen_model("ss2", "prompt", state)
    assert "Câu chuyện &lt;liền mạch&gt;" in model["text"]


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_every_canonical_screen_has_its_exact_back_owner(flow: str):
    state = _state(flow)
    for screen in sorted(video_selfshotflow4.FLOW_SCREENS[flow]):
        state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = screen
        model = video_selfshotflow4.screen_model(flow, screen, state)
        parent = video_selfshotflow4.screen_parent(flow, screen)
        expected = "vproduct|selfshot_hub" if parent == "hub" else f"vproduct|{flow}|c4show|{parent}"
        assert model["rows"][-1][0][1] == expected
        assert model["rows"][-1][1][1] == "menu|main"
        assert video_selfshotflow4.validate_rows(model["rows"], back_callback=expected)["ok"]
