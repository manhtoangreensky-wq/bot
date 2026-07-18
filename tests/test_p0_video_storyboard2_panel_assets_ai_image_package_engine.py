from __future__ import annotations

import ast
import re
from pathlib import Path

from services import video_flow6, video_flow7, video_scene3_flow, video_storyboard2


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
STORYBOARD_SOURCE = (ROOT / "services" / "video_storyboard2.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _board(scene_count: int = 2) -> dict:
    board = video_storyboard2.default_state()
    board = video_storyboard2.set_scene_count(board, scene_count)
    board = video_storyboard2.set_ratio(board, "9:16")
    board = video_storyboard2.apply_content(
        board,
        "Giới thiệu một sản phẩm bằng câu chuyện liền mạch, không đổi nhận diện.",
        mode="manual",
    )
    return video_storyboard2.approve_content(board)


def _with_start_images(board: dict) -> dict:
    current = board
    for scene_index in range(1, int(current["scene_count"]) + 1):
        current = video_storyboard2.assign_image(
            current,
            scene_index,
            "start",
            video_storyboard2.image_record(
                scene_index=scene_index,
                slot="start",
                file_id=f"start-{scene_index}",
                source_type="telegram_upload",
                artifact_receipt={"message_id": scene_index},
                prompt=f"Ảnh đầu cảnh {scene_index}",
                prompt_version=1,
            ),
        )
    return current


def _ready_board(scene_count: int = 2) -> dict:
    board = _with_start_images(_board(scene_count))
    board = video_storyboard2.compile_video_prompts(board)
    board = video_storyboard2.build_transitions(board)
    board["addons_ready"] = True
    return video_storyboard2.normalize_state(board)


def test_storyboard_has_one_canonical_entry_and_no_nested_idea_video() -> None:
    rows = video_flow7.ENTRY_ROWS["storyboard_prompt"]
    callbacks = [callback for row in rows for _label, callback in row]
    labels = [label for row in rows for label, _callback in row]
    assert callbacks == ["vstory|start", "vstory|upload", "vstory|ai", "vstory|help"]
    assert all("idea" not in callback for callback in callbacks)
    assert all("Ý tưởng video" not in label for label in labels)
    assert BOT_SOURCE.count('CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")') == 1
    assert BOT_SOURCE.count('CallbackQueryHandler(handle_storyboard_callback, pattern=r"^storyboard\\|")') == 1
    legacy = _function_source("handle_storyboard_callback")
    assert "return await handle_storyboard2_legacy_callback(update, context)" in legacy
    assert legacy.index("return await handle_storyboard2_legacy_callback") < legacy.index("query = update.callback_query")


def test_scene_image_limits_and_mapping_for_two_and_five_scenes() -> None:
    two = _with_start_images(_board(2))
    two_summary = video_storyboard2.asset_summary(two)
    assert two_summary == {
        "minimum_images": 2,
        "maximum_images": 4,
        "ready_images": 2,
        "ready_start": 2,
        "ready_end": 0,
        "missing_start": [],
        "missing_required_end": [],
        "ok": True,
    }
    five = _with_start_images(_board(5))
    five_summary = video_storyboard2.asset_summary(five)
    assert (five_summary["minimum_images"], five_summary["maximum_images"]) == (5, 10)
    assert [scene["start_image"]["image_id"] for scene in five["scenes"]] == [
        f"scene_{index}_start" for index in range(1, 6)
    ]


def test_storyboard_images_can_be_replaced_deleted_and_reordered_by_scene_slot() -> None:
    board = _with_start_images(_board(2))
    moved = video_storyboard2.move_image_to_scene(board, 1, 2, "start")
    assert moved["active_scene_index"] == 2
    assert moved["scenes"][1]["start_image"]["file_id"] == "start-1"
    assert moved["scenes"][0]["start_image"]["file_id"] == "start-2"
    assert moved["scenes"][1]["start_image"]["image_id"] == "scene_2_start"
    assert moved["scenes"][0]["start_image"]["image_id"] == "scene_1_start"

    replacement = video_storyboard2.image_record(
        scene_index=2,
        slot="start",
        file_id="replacement-2",
        source_type="telegram_upload",
        artifact_receipt={"telegram_message_id": 202},
    )
    replaced = video_storyboard2.assign_image(moved, 2, "start", replacement)
    assert replaced["scenes"][1]["start_image"]["file_id"] == "replacement-2"
    deleted = video_storyboard2.remove_image(replaced, 2, "start")
    assert deleted["scenes"][1]["start_image"]["status"] == "missing"


def test_optional_end_image_changes_capability_without_losing_scene_mapping() -> None:
    board = _with_start_images(_board(2))
    assert video_storyboard2.required_capability(board) == "image_to_video"
    board = video_storyboard2.set_end_mode(board, 2, "required")
    assert video_storyboard2.asset_summary(board)["ok"] is False
    board = video_storyboard2.assign_image(
        board,
        2,
        "end",
        video_storyboard2.image_record(
            scene_index=2,
            slot="end",
            result_url="https://fixture.invalid/end-2.png",
            source_type="quick_image_paid_delivery",
            artifact_receipt={"delivered": True},
            prompt="Ảnh cuối cảnh 2",
            prompt_version=2,
        ),
    )
    assert video_storyboard2.asset_summary(board)["ok"] is True
    assert video_storyboard2.required_capability(board) == "first_last_frame_video"
    manifest = video_storyboard2.build_manifest(board)
    assert manifest["scenes"][1]["end_image_id"] == "scene_2_end"
    assert manifest["scenes"][1]["input_mode"] == "first_last_frame_video"


def test_start_and_end_prompts_are_distinct_and_inherit_scene_ratio_and_continuity() -> None:
    board = _board(2)
    board["continuity"] = {
        "character": "Nhân vật A",
        "product": "Sản phẩm nguyên mẫu",
        "brand_color": "xanh ngọc",
    }
    board["profile"] = {"key": "product_showcase", "label": "Trưng bày sản phẩm"}
    board["style"] = {"visual": "điện ảnh chân thật"}
    start = video_storyboard2.image_prompt(board, 1, "start", 0)
    end = video_storyboard2.image_prompt(board, 1, "end", 0)
    assert start["prompt"] != end["prompt"]
    for value in (start["prompt"], end["prompt"]):
        assert "9:16" in value
        assert "Cảnh 1" in value
        assert "Nhân vật A" in value
        assert "xanh ngọc" in value
        assert "Trưng bày sản phẩm" in value
    assert "trạng thái trước hành động" in start["prompt"]
    assert "hành động đã hoàn tất" in end["prompt"]


def test_video_prompts_are_per_scene_and_transition_count_is_n_minus_one() -> None:
    board = _ready_board(5)
    prompts = [scene["video_prompt"] for scene in board["scenes"]]
    assert len(prompts) == 5
    assert len(set(prompts)) == 5
    assert all("8 giây" in prompt and "9:16" in prompt for prompt in prompts)
    assert len(board["transitions"]) == 4
    assert board["transitions"][0]["from_scene_id"] == "scene_1"
    assert board["transitions"][-1]["to_scene_id"] == "scene_5"


def test_storyboard_preflight_and_execution_route_are_canonical_and_side_effect_free() -> None:
    board = _ready_board(2)
    result = video_storyboard2.preflight(board)
    assert result["ok"] is True
    assert result["job_type"] == "storyboard_to_video"
    assert result["execution_owner"] == "owner_product_video"
    assert result["manifest"]["scene_count"] == 2
    assert result["manifest"]["required_capability"] == "image_to_video"
    assert result["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }

    context = video_flow6.normalize_context({
        "product_id": "storyboard_prompt",
        "flow_kind": "storyboard",
        "content_mode": "manual",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "asset_requirement": "images_required",
        "required_capability": "image_to_video",
        "storyboard_manifest": result["manifest"],
        "asset_manifest": {
            "items": [
                {
                    "scene_index": scene["scene_index"],
                    "slot": "start",
                    "file_id": scene["start_image_file_id"],
                }
                for scene in result["manifest"]["scenes"]
            ]
        },
    })
    gate = video_flow6.asset_gate_status(context)
    route = video_flow6.execution_route_for(context)
    assert gate["ok"] is True
    assert gate["mapped_scene_count"] == 2
    assert route["job_type"] == "storyboard_to_video"
    assert route["execution_owner"] == "owner_product_video"
    assert route["required_capability"] == "image_to_video"


def test_missing_assets_block_before_invoice_or_provider_submit() -> None:
    board = _board(2)
    board = video_storyboard2.assign_image(
        board,
        1,
        "start",
        video_storyboard2.image_record(
            scene_index=1,
            slot="start",
            file_id="only-scene-one",
            source_type="telegram_upload",
        ),
    )
    result = video_storyboard2.preflight(board)
    assert result["ok"] is False
    assert result["block_reason"] == "storyboard_start_images_missing"
    assert result["side_effects"]["provider_calls"] == 0
    assert result["side_effects"]["job"] == 0
    assert result["side_effects"]["wallet_mutations"] == 0


def test_paid_image_handoff_returns_to_exact_storyboard_scene_and_slot() -> None:
    prepare = _function_source("storyboard2_prepare_quick_image")
    confirmation = _function_source("quick_image_video_scene3_confirmation_fields")
    recorder = _function_source("video_scene3_record_generated_image")
    cancel = _function_source("handle_create_media_callback")
    assert 'return_to="vstory|image_return"' in prepare
    assert "storyboard_scene_index=scene_index" in prepare
    assert "storyboard_slot=slot" in prepare
    assert 'if str(state.get("return_to") or "") == "vstory|image_return"' in confirmation
    assert 'if delivered and (str(output_file_id or "").strip() or str(image_url or "").strip())' in recorder
    assert "video_storyboard2.assign_image" in recorder
    assert 'return_pending = {**quick_state, "origin_flow": "video_scene3"}' in cancel
    assert "video_scene3_image_handoff_panel(scene_state)" in cancel


def test_storyboard_keyboards_have_one_to_five_row_exact_back_and_no_duplicate_actions() -> None:
    suggestion = _function_source("storyboard2_suggestion_keyboard")
    image_prompt = _function_source("storyboard2_image_prompt_keyboard")
    count = _function_source("storyboard2_count_keyboard")
    video_prompt = _function_source("storyboard2_video_prompt_keyboard")
    assert 'range(1, 6)' in suggestion
    assert 'range(1, 6)' in image_prompt
    assert 'storyboard2_nav("vstory|entry")' in count
    assert video_prompt.count('"vstory|video_done"') == 1
    assert '"vstory|scene_screen"' in video_prompt
    asset_keyboard = _function_source("storyboard2_asset_keyboard")
    assert '"vstory|asset_move_prev"' in asset_keyboard
    assert '"vstory|asset_move_next"' in asset_keyboard
    assert '"💡 Ý tưởng video"' not in _function_source("storyboard2_entry_keyboard")


def test_all_public_storyboard_callbacks_have_one_canonical_owner() -> None:
    callback_tokens = set(re.findall(r'vstory\|([a-z0-9_]+)', BOT_SOURCE))
    allowlist_source = _function_source("storyboard2_quality_keyboard") + BOT_SOURCE[
        BOT_SOURCE.index("STORYBOARD2_CALLBACK_ACTIONS") : BOT_SOURCE.index("def storyboard2_package_resolutions")
    ]
    allowlist = set(re.findall(r'"([a-z0-9_]+)"', allowlist_source))
    assert callback_tokens <= allowlist
    callback = _function_source("_handle_storyboard2_callback_impl")
    assert callback.index("if action not in STORYBOARD2_CALLBACK_ACTIONS") < callback.index("outer = video_profile_studio_state(context)")
    assert BOT_SOURCE.count('CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")') == 1


def test_storyboard_package_filter_hides_contract_invalid_tiers_without_provider_calls() -> None:
    source = _function_source("storyboard2_package_resolutions")
    calls = []

    class _Scene3:
        @staticmethod
        def normalize_state(state):
            return dict(state)

    class _Catalog:
        @staticmethod
        def resolve_product_video_model(**kwargs):
            calls.append(dict(kwargs))
            return {"ok": int(kwargs["tier"]) in {300, 600}}

    namespace = {
        "video_scene3_flow": _Scene3,
        "video_flow6_required_capability": lambda _kind, state: state["required_capability"],
        "safe_int": lambda value, default=0: int(value or default),
        "VIDEO_B14_2_QUALITY_OPTIONS": (200, 300, 400, 500, 600),
        "video_provider_catalog": _Catalog,
    }
    exec(source, namespace)
    result = namespace["storyboard2_package_resolutions"]({
        "scene_count": 2,
        "required_capability": "image_to_video",
    })
    assert [item["price"] for item in result] == [300, 600]
    assert len(calls) == 5
    assert all(call["required_capability"] == "image_to_video" for call in calls)
    assert all(call["requires_concat"] is True for call in calls)


def test_storyboard_quality_back_and_two_frame_fallback_are_exact() -> None:
    keyboard = _function_source("storyboard2_quality_keyboard")
    callback = _function_source("_handle_storyboard2_callback_impl")
    profile_callback = _function_source("handle_video_profile_studio_callback")
    assert '"vstory|review_from_quality"' in keyboard
    assert '"vstory|one_image_mode"' in keyboard
    assert 'if action == "review_from_quality"' in callback
    assert 'if action == "one_image_mode"' in callback
    assert 'set_end_mode(board, scene_index, "none")' in callback
    assert 'step == "quality" and str(state.get("flow_kind") or "") == "storyboard"' in profile_callback


def test_storyboard_addons_survive_handoff_to_runtime_plan() -> None:
    handoff = _function_source("storyboard2_scene3_handoff")
    assert '"dubbing_mix": bool(selected_addons.get("dubbing"))' in handoff
    assert '"subtitle_rendering": bool(selected_addons.get("subtitles"))' in handoff
    assert '"music_mix": bool(selected_addons.get("music"))' in handoff
    assert '"sfx_mix": bool(selected_addons.get("sfx"))' in handoff
    assert '"logo_burn_in": bool(selected_addons.get("logo"))' in handoff
    assert '"post_production": runtime_post' in handoff


def test_storyboard_handoff_satisfies_scene_contract_before_invoice() -> None:
    source = _function_source("storyboard2_scene3_handoff")
    namespace = {
        "video_storyboard2": video_storyboard2,
        "video_profile_studio_state": lambda _context: {},
        "video_flow6": video_flow6,
        "save_video_profile_studio_state": lambda _context, state: dict(state),
    }
    exec(source, namespace)

    board = _ready_board(2)
    result = namespace["storyboard2_scene3_handoff"](object(), board)
    counts = video_scene3_flow.scene_contract_counts(result)
    assert counts == {
        "expected": 2,
        "scenes": 2,
        "image_strategies": 2,
        "image_prompts": 2,
        "image_prompts_expected": 2,
        "video_prompts": 2,
    }
    assert result["image_source_mode"] == "uploaded"
    assert all(item["approved"] for item in result["image_strategy_per_scene"].values())
    assert result["execution_route"]["job_type"] == "storyboard_to_video"
    assert result["execution_route"]["execution_owner"] == "owner_product_video"


def test_invalid_storyboard_inputs_are_idempotent_and_do_not_repeat_error_panels() -> None:
    text_handler = _function_source("handle_storyboard2_pending_text")
    media_handler = _function_source("handle_storyboard2_pending_media")
    assert 'board["processed_text_message_ids"] = processed' not in text_handler
    media_ledger = 'board["processed_media_message_ids"] = (processed + ([message_id] if message_id else []))[-100:]'
    assert media_handler.count(media_ledger) == 1
    assert media_handler.index(media_ledger) < media_handler.index("if media is None:")


def test_entry_modes_split_after_ratio_and_keep_exact_back_targets() -> None:
    callback = _function_source("_handle_storyboard2_callback_impl")
    payload = _function_source("storyboard2_screen_payload")
    suggestion_keyboard = _function_source("storyboard2_suggestion_keyboard")
    assert 'if entry_mode == "existing"' in callback
    assert 'move(board, "await_content", awaiting_input="content")' in callback
    assert 'elif entry_mode == "ai"' in callback
    assert 'move(board, "suggestions", awaiting_input="")' in callback
    assert '"vstory|ratio_screen" if entry_mode == "existing"' in payload
    assert '"vstory|ratio_screen" if entry_mode == "ai"' in suggestion_keyboard


def test_storyboard_service_has_no_provider_http_wallet_or_file_side_effects() -> None:
    forbidden = (
        "requests.",
        "httpx.",
        "aiohttp.",
        "urlopen(",
        "update_wallet",
        "deduct_xu",
        "charge_wallet",
        "charge_xu",
        "subprocess",
        "open(",
    )
    assert all(token not in STORYBOARD_SOURCE for token in forbidden)


def test_all_touched_storyboard_bot_functions_parse_as_python311_source() -> None:
    names = (
        "storyboard2_state",
        "storyboard2_new_outer_state",
        "save_storyboard2_state",
        "storyboard2_keyboard",
        "storyboard2_nav",
        "storyboard2_entry_keyboard",
        "storyboard2_count_keyboard",
        "storyboard2_ratio_keyboard",
        "storyboard2_content_choice_keyboard",
        "storyboard2_suggestion_keyboard",
        "storyboard2_scene_review_keyboard",
        "storyboard2_asset_keyboard",
        "storyboard2_image_prompt_keyboard",
        "storyboard2_video_prompt_keyboard",
        "storyboard2_transition_keyboard",
        "storyboard2_addon_keyboard",
        "storyboard2_review_keyboard",
        "storyboard2_package_resolutions",
        "storyboard2_quality_text",
        "storyboard2_quality_keyboard",
        "storyboard2_entry_text",
        "storyboard2_screen_payload",
        "storyboard2_render",
        "storyboard2_scene3_handoff",
        "storyboard2_prepare_quick_image",
        "_handle_storyboard2_callback_impl",
        "handle_storyboard2_callback",
        "handle_storyboard2_legacy_callback",
        "handle_storyboard2_pending_text",
        "handle_storyboard2_pending_media",
        "quick_image_video_scene3_confirmation_fields",
        "video_scene3_image_handoff_target_step",
        "video_scene3_image_handoff_panel",
        "video_scene3_record_generated_image",
        "handle_storyboard_callback",
        "handle_create_media_callback",
    )
    for name in names:
        ast.parse("from __future__ import annotations\n\n" + _function_source(name), filename=f"<{name}>")
