from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    starts = [
        BOT_SOURCE.find(f"\ndef {name}("),
        BOT_SOURCE.find(f"\nasync def {name}("),
    ]
    starts = [value + 1 for value in starts if value >= 0]
    if not starts:
        raise AssertionError(f"missing function: {name}")
    start = min(starts)
    ends = [
        value + 1
        for value in (
            BOT_SOURCE.find("\ndef ", start + 1),
            BOT_SOURCE.find("\nasync def ", start + 1),
        )
        if value >= 0
    ]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def test_public_video_menu_opens_every_lane_except_long_form():
    rows = _between("VIDEO_PUBLIC_MENU_ROWS = (", "VIDEO_PUBLIC_ROUTE_MATRIX = {")
    matrix = _between("VIDEO_PUBLIC_ROUTE_MATRIX = {", "def video_public_route_for_tool")
    expected_rows = (
        '("video_trend", "video_ai_real")',
        '("script_image_video", "frame_video_local")',
        '("self_shot_scene_change", "multi_scene_film")',
        '("storyboard_prompt", "video_idea")',
        '("video_local_edit", "video_downloader")',
        '("main_menu", "video_guide")',
    )

    assert all(row in rows for row in expected_rows)
    assert matrix.count('"entry_callback": "longvideo|public_guard"') == 1
    long_route = matrix[matrix.index('"multi_scene_film": {'):matrix.index('"video_idea": {')]
    assert '"invoice_reachable": False' in long_route
    assert '"job_reachable": False' in long_route


def test_vproduct_open_uses_one_canonical_public_access_contract():
    access = _function_source("video_public_product_flow_access")
    handler = _function_source("handle_video_product_callback")

    assert 'product == "multi_scene_film"' in access
    assert '"long_form_video_in_development"' in access
    assert '"flow_access_allowed": True' in access
    assert "video_public_product_flow_access(value)" in handler
    assert 'flow_access.get("flow_block_reason") == "long_form_video_in_development"' in handler


def test_public_access_contract_behavior_is_open_except_long_form():
    namespace = {
        "video_public_route_for_tool": lambda product: ({"product_id": product} if product in {"video_ai_real", "multi_scene_film"} else {}),
        "VIDEO_PRODUCT_REGISTRY": {"video_ai_real": {}, "multi_scene_film": {}},
    }
    exec(_function_source("video_public_product_flow_access"), namespace)
    access = namespace["video_public_product_flow_access"]

    assert access("video_ai_real")["flow_access_allowed"] is True
    assert access("multi_scene_film") == {
        "product_id": "multi_scene_film",
        "flow_access_allowed": False,
        "flow_block_reason": "long_form_video_in_development",
    }
    assert access("missing")["flow_block_reason"] == "unknown_video_product"


def test_public_planning_text_does_not_depend_on_provider_runtime():
    source = _function_source("video_ai_true_text")
    assert 'shopaikey_public_flow_access_guard("video")' in source
    assert "shopaikey_public_generation_guard" not in source
    assert "VIDEO_AI_PUBLIC_ENABLED" not in source


def test_provider_submit_guard_remains_at_final_confirmation():
    source = _function_source("handle_shopaikey_public_callback")
    assert "shopaikey_provider_submit_guard(" in source
    assert "confirmed=action in" in source
    assert "restore_shopaikey_pending_confirmation" in source


def test_storyboard_missing_image_stays_in_planning_until_confirm():
    callback = _function_source("_handle_storyboard2_callback_impl")
    start = callback.index('if action == "asset_ai_missing":')
    end = callback.index("\n    if action in {", start)
    branch = callback[start:end]
    prepare = _function_source("storyboard2_prepare_quick_image")

    assert "storyboard2_prepare_quick_image" in branch
    assert "shopaikey_image_generate" not in branch
    assert 'return_to="vstory|image_return"' in prepare
    assert 'source_flow="video_scene3"' in prepare


def test_storyboard_provider_failure_returns_to_same_asset_panel_without_charge():
    source = _function_source("handle_shopaikey_public_image_confirm_delivery_first")
    assert "if scene3_handoff:" in source
    assert "video_scene3_record_generated_image" in source
    assert "video_scene3_image_handoff_panel" in source
    assert 'refund_status="not_charged"' in source
    assert 'billing_status="failed_not_charged"' in source
