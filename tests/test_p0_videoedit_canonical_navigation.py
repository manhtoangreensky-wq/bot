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

