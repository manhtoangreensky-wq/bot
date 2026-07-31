from __future__ import annotations

from services import video_edit_state_machine as machine


def test_videoedit_parent_matrix_is_exact() -> None:
    assert machine.parent_callback("workspace", lane="manual_edit") == "videoedit|manual"
    assert machine.parent_callback("workspace", lane="ai_edit") == "videoedit|ai"
    assert machine.parent_callback("workspace", lane="quality_enhance") == "videoedit|restore"
    assert machine.parent_callback("cut") == "videoedit|workspace"
    assert machine.parent_callback("trim_input") == "videoedit|cut"
    assert machine.parent_callback("split") == "videoedit|cut"
    assert machine.parent_callback("split_input") == "videoedit|split"
    assert machine.parent_callback("join") == "videoedit|workspace"
    assert machine.parent_callback("concat_input") == "videoedit|join"
    assert machine.parent_callback("reorder_input") == "videoedit|join"
    assert machine.parent_callback("frame") == "videoedit|workspace"
    assert machine.parent_callback("transform") == "videoedit|workspace"
    assert machine.parent_callback("rotation_value") == "videoedit|transform"
    assert machine.parent_callback("audio") == "videoedit|workspace"
    assert machine.parent_callback("audio_input") == "videoedit|audio"
    assert machine.parent_callback("color") == "videoedit|workspace"
    assert machine.parent_callback("overlay") == "videoedit|workspace"
    assert machine.parent_callback("text_input") == "videoedit|overlay"
    assert machine.parent_callback("logo_input") == "videoedit|overlay"
    assert machine.parent_callback("srt_input") == "videoedit|overlay"
    assert machine.parent_callback("effects") == "videoedit|workspace"
    assert machine.parent_callback("effect_detail") == "videoedit|effects"
    assert machine.parent_callback("source_info") == "videoedit|workspace"
    assert machine.parent_callback("review") == "videoedit|workspace"
    assert machine.parent_callback("confirmation") == "videoedit|review"


def test_videoedit_confirmation_screen_has_an_exact_resume_callback() -> None:
    assert machine.screen_callback("confirmation") == "videoedit|confirmation"


def test_videoedit_parent_callback_fails_closed() -> None:
    assert machine.safe_parent_callback("videoedit|cut") == "videoedit|cut"
    assert machine.safe_parent_callback("videoedit|") == "videoedit|hub"
    assert machine.safe_parent_callback("vproduct|open|product_video") == "videoedit|hub"
    assert machine.safe_parent_callback("subdub|menu") == "videoedit|hub"
    assert machine.safe_parent_callback("lvs27b|open") == "videoedit|hub"
    assert machine.safe_parent_callback("menu|main_video") == "videoedit|hub"
    assert machine.safe_parent_callback("menu|main_video", root=True) == "menu|main_video"
    assert machine.safe_parent_callback("menu|main", root=True) == "menu|main"
    assert machine.safe_parent_callback("menu|unexpected", root=True) == "videoedit|hub"


def test_videoedit_unknown_screen_and_lane_fail_to_hub() -> None:
    assert machine.parent_callback("missing") == "videoedit|hub"
    assert machine.parent_callback("workspace", lane="missing") == "videoedit|hub"


def test_videoedit_parent_map_is_immutable_to_callers() -> None:
    first = machine.parent_matrix()
    first["cut"] = "subdub|menu"
    second = machine.parent_matrix()
    assert second["cut"] == "videoedit|workspace"


def test_videoedit_legacy_actions_map_to_live_canonical_actions() -> None:
    expected = {
        "manual_info": ("manual", "manual"),
        "split_info": ("split_from_manual", "cut"),
        "ai_info": ("ai", "assistant"),
        "cut": ("manual_cut", "cut"),
        "timeline": ("manual_join", "join"),
        "split": ("split_from_manual", "cut"),
        "audio": ("manual_audio", "audio"),
        "effects": ("manual_effects", "effects"),
        "plan": ("review", "review"),
        "resize": ("aspect", "frame"),
        "crop": ("aspect", "frame"),
        "ratio": ("aspect", "frame"),
        "vertical": ("aspect", "frame"),
        "compress": ("resolution", "resolution"),
        "subtitle": ("srt", "overlay"),
        "color": ("color", "color"),
        "preset": ("color_preset", "color"),
        "text": ("text_overlay", "overlay"),
        "sharpen": ("restore", "quality"),
    }
    for raw_action, (canonical_action, requested_group) in expected.items():
        assert machine.canonical_compatibility_action(raw_action) == canonical_action
        assert machine.requested_group(raw_action) == requested_group


def test_videoedit_live_actions_are_not_rewritten_as_legacy_redirects() -> None:
    for action in (
        "manual",
        "manual_cut",
        "manual_join",
        "manual_audio",
        "manual_effects",
        "aspect",
        "resolution",
        "rotation",
        "flip",
        "speed",
        "volume",
        "color_preset",
        "text_overlay",
        "logo",
        "srt",
        "review",
    ):
        assert machine.canonical_compatibility_action(action) == action


def test_videoedit_source_info_resumes_the_exact_input_screen() -> None:
    assert machine.resume_callback("trim_input", "trim_edges") == "videoedit|trim_edges"
    assert machine.resume_callback("trim_input", "remove_middle") == "videoedit|remove_middle"
    assert machine.resume_callback("split_input", "split_custom") == "videoedit|split_custom"
    assert machine.resume_callback("concat_input", "concat") == "videoedit|concat"
    assert machine.resume_callback("reorder_input", "concat_order") == "videoedit|reorder"
    assert machine.resume_callback("text_input", "text_overlay") == "videoedit|text_overlay"
    assert machine.resume_callback("logo_input", "logo") == "videoedit|logo"
    assert machine.resume_callback("srt_input", "srt") == "videoedit|srt"
    assert machine.resume_callback("choose_aspect") == "videoedit|aspect"
    assert machine.resume_callback("choose_resolution") == "videoedit|resolution"
    assert machine.resume_callback("rotation_value") == "videoedit|transform"


def test_videoedit_requested_group_resumes_exact_screen_after_upload() -> None:
    expected = {
        "cut": "cut",
        "join": "join",
        "frame": "frame",
        "resolution": "resolution",
        "audio": "audio",
        "effects": "effects",
        "overlay": "overlay",
        "color": "color",
        "review": "review",
    }
    for group, screen in expected.items():
        assert machine.requested_group_screen(group) == screen
    assert machine.requested_group_screen("../../subdub") == ""
