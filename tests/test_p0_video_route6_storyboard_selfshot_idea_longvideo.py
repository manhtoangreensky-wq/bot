from __future__ import annotations

from pathlib import Path

from services import video_idea_handoff, video_long_planning


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def test_storyboard_image_callbacks_have_one_owner_and_precede_generic_image_handler():
    assert '("vstoryimg|", "handle_storyboard_image_callback")' in BOT_SOURCE
    dedicated = 'CallbackQueryHandler(handle_storyboard_image_callback, pattern=r"^vstoryimg\\|")'
    generic = 'CallbackQueryHandler(handle_create_media_callback, pattern=r"^create_media\\|")'
    assert BOT_SOURCE.count(dedicated) == 1
    assert BOT_SOURCE.index(dedicated) < BOT_SOURCE.index(generic)

    owner = _between(
        "async def handle_storyboard_image_callback",
        "async def cmd_tool_test_workflow_image",
    )
    assert "storyboard_quick_image_owner_valid" in owner
    assert "_handle_create_media_callback_impl" in owner
    validator = _between(
        "def storyboard_quick_image_owner_valid",
        "async def _handle_create_media_callback_impl",
    )
    assert '"vstory|image_return"' in validator

    quick_keyboards = _between(
        "def quick_image_entry_keyboard",
        "def quick_image_confirm_keyboard",
    )
    assert 'callback_data=f"{callback_prefix}|qi_suggest"' in quick_keyboards
    assert 'callback_data=quick_image_callback(state, f"qi_pick_{index}")' in quick_keyboards
    assert 'callback_data=quick_image_callback(state, "cancel")' in quick_keyboards

    provider_block = _between(
        'if str(pending.get("source") or "") == "quick_image_v6":',
        'elif str(pending.get("source") or "") in {"image_prompt_tool", "image_edit_create_new"}:',
    )
    assert "quick_state = get_quick_image_flow(uid) or {}" in provider_block
    assert "quick_image_confirm_keyboard(token, lang, quick_state)" in provider_block


def test_storyboard_image_session_keeps_scene_slot_and_exact_parent():
    prepare = _between(
        "def storyboard2_prepare_quick_image",
        "async def _handle_storyboard2_callback_impl",
    )
    for contract in (
        'flow="storyboard"',
        'product="storyboard_prompt"',
        'owner="storyboard_image"',
        'session_id=',
        'generation_state="planning"',
        'idea_id=',
        'storyboard_scene_index=scene_index',
        'storyboard_slot=slot',
        'return_to="vstory|image_return"',
    ):
        assert contract in prepare

    namespace = _between(
        "def quick_image_callback_namespace",
        "def quick_image_callback",
    )
    assert 'return "vstoryimg"' in namespace


def test_route6_callback_prefixes_have_one_owner_and_one_registered_handler():
    owner_map = _between(
        "VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES = (",
        "\n)\n\n\ndef video_route_expected_handler",
    )
    expected = {
        "vstory|": ("handle_storyboard2_callback", r"^vstory\|"),
        "vstoryimg|": ("handle_storyboard_image_callback", r"^vstoryimg\|"),
        "vproduct|": ("handle_video_product_callback", r"^vproduct\|(?!b14_confirm(?:\||$))"),
        "videa|": ("handle_video_idea_dynamic_callback", r"^videa\|"),
        "longvideo|": ("handle_long_video_callback", r"^longvideo\|"),
    }
    for prefix, (handler, pattern) in expected.items():
        assert owner_map.count(f'("{prefix}", "{handler}")') == 1
        registration = f'CallbackQueryHandler({handler}, pattern=r"{pattern}")'
        assert BOT_SOURCE.count(registration) == 1

    assert owner_map.index('("vstoryimg|", "handle_storyboard_image_callback")') < owner_map.index(
        '("create_media|", "handle_create_media_callback")'
    )


def test_selfshot_uploads_are_owned_by_distinct_sessions_and_route_once():
    ss2 = _between("def video_selfshot2_draft", "def save_video_selfshot2_draft")
    ss3 = _between("def video_selfshot3_draft", "def save_video_selfshot3_draft")
    assert 'defaults["owner"] = "selfshot2"' in ss2
    assert 'defaults["owner"] = "selfshot3"' in ss3
    assert 'defaults["session_id"]' in ss2
    assert 'defaults["session_id"]' in ss3

    media = _between(
        "async def handle_video_product_pending_media",
        "async def open_prompt_video_finalization_from_state",
    )
    assert media.count("video_selfshot_media_owner_valid(") == 2
    assert 'owner="selfshot2"' in media
    assert 'owner="selfshot3"' in media
    assert 'step="awaiting_selfshot2_video"' in media
    assert 'step="awaiting_selfshot3_video"' in media
    assert "inspect_video_editor_source" in media


def test_idea_handoff_restores_exact_parent_context_and_next_step():
    parent = video_idea_handoff.build_parent_handoff(
        {
            "flow": "storyboard",
            "flow_session_id": "story-session",
            "flow_revision": 4,
            "storyboard_session_id": "board-session",
            "idea_preset_id": 42,
            "idea_content": "Nội dung đã duyệt",
            "idea_prompt": "Prompt đã sửa",
            "scene_count": 2,
            "aspect_ratio": "16:9",
            "reference_assets": {
                "source_media_refs": ["img-a", "img-b"],
                "items": [{"file_id": "img-a", "media_kind": "photo"}],
            },
        },
        product_id="storyboard_prompt",
        return_callback="vstory|idea_return",
    )
    result = video_idea_handoff.apply_parent_handoff({"subject": "Preset"}, parent)
    assert result["source_product_id"] == "storyboard_prompt"
    assert result["step"] == "storyboard_scene_review"
    assert result["storyboard_session_id"] == "board-session"
    assert result["scene_count"] == 2
    assert result["aspect_ratio"] == "16:9"
    assert result["idea_parent_return_callback"] == "vstory|idea_return"
    assert result["idea_source_flow"] == "storyboard"
    assert result["idea_return_step"] == "storyboard_scene_review"
    assert result["idea_preset_id"] == 42
    assert result["idea_content"] == "Nội dung đã duyệt"
    assert result["idea_prompt"] == "Prompt đã sửa"
    assert result["reference_assets"]["source_media_refs"] == ["img-a", "img-b"]


def test_idea_handoff_keeps_each_selfshot_lane_separate():
    expected_steps = {
        "self_shot_scene_change": "selfshot2_scene_plan",
        "self_shot_cinematic_transform": "selfshot3_timeline",
    }
    for product, expected_step in expected_steps.items():
        parent = video_idea_handoff.build_parent_handoff(
            {
                "flow": product,
                "session_id": f"{product}-session",
                "source_analysis": {"duration_seconds": 12},
                "reference_assets": {
                    "source_media_ref": f"{product}-video",
                    "source_media_refs": [f"{product}-video"],
                },
            },
            product_id=product,
            return_callback=f"vproduct|idea_back|{product}",
        )
        result = video_idea_handoff.apply_parent_handoff({}, parent)
        assert result["source_product_id"] == product
        assert result["step"] == expected_step
        assert result["reference_assets"]["source_media_ref"] == f"{product}-video"
        assert result["idea_parent_state"]["source_analysis"]["duration_seconds"] == 12


def test_idea_approval_dispatches_to_each_real_parent_component():
    dispatcher = _between(
        "async def video_idea_render_exact_parent",
        "async def handle_video_idea_dynamic_callback",
    )
    assert 'product_id == "storyboard_prompt"' in dispatcher
    assert 'video_storyboard2.move(board, "scene_review"' in dispatcher
    assert "product_id == video_selfshot2.PRODUCT_ID" in dispatcher
    assert 'video_selfshot2_render(query, user_id, "scene_plan"' in dispatcher
    assert "product_id == video_selfshot3.PRODUCT_ID" in dispatcher
    assert 'target_screen = "timeline"' in dispatcher
    assert "video_selfshot3_render(query, user_id, target_screen" in dispatcher
    assert "video_profile_scene1_render(query, handoff, lang)" in dispatcher


def test_idea_parent_next_step_contract_is_product_specific():
    assert video_idea_handoff.NEXT_STEPS == {
        "video_idea": "video_prompts",
        "video_trend": "scene_plan",
        "video_ai_real": "scene_plan",
        "script_image_video": "scene_plan",
        "video_reference": "scene_plan",
        "motion_prompt": "scene_plan",
        "storyboard_prompt": "storyboard_scene_review",
        "self_shot_scene_change": "selfshot2_scene_plan",
        "self_shot_cinematic_transform": "selfshot3_timeline",
        "multi_scene_film": "long_chapter_plan",
    }


def test_long_video_is_publicly_locked_and_internal_contract_is_ten_minutes_per_scene():
    assert video_long_planning.PUBLIC_ENABLED is False
    assert video_long_planning.SCENE_DURATION_SECONDS == 600
    assert video_long_planning.public_access_allowed(is_admin=False) is False
    assert video_long_planning.public_access_allowed(is_admin=True) is False

    plan = video_long_planning.normalize_internal_plan({"duration_minutes": 120})
    assert plan["canonical_planning_flow"] == "video_ai_real"
    assert plan["scene_unit_minutes"] == 10
    assert plan["planning_steps"] == list(video_long_planning.INTERNAL_STEPS)
    assert plan["scene_duration_seconds"] == 600
    assert plan["scene_count"] == 12
    assert plan["public_enabled"] is False
    assert plan["provider_called"] is False
    assert plan["job_created"] is False
    assert plan["outbox_created"] is False
    assert plan["xu_charged"] == 0

    handler = _between("async def handle_long_video_callback", "async def handle_storyboard_pack_callback")
    guard = handler[: handler.index('if action == "start":')]
    assert "video_long_planning.public_access_allowed" in guard
    assert "clear_developing_video_pending" not in guard


def test_route6_scope_has_no_provider_execution_contract():
    service_source = (
        (ROOT / "services" / "video_idea_handoff.py").read_text(encoding="utf-8")
        + (ROOT / "services" / "video_long_planning.py").read_text(encoding="utf-8")
    )
    for forbidden in (
        "requests.post",
        "httpx.post",
        "provider.submit",
        "shopaikey",
        "key4u",
        "charge_wallet",
    ):
        assert forbidden not in service_source.lower()


def test_route6_callback_crawler_has_no_dead_owner_duplicate_or_generic_x():
    registrations = {
        "vstory|": ('handle_storyboard2_callback', r'^vstory\|'),
        "vstoryimg|": ('handle_storyboard_image_callback', r'^vstoryimg\|'),
        "videa|": ('handle_video_idea_dynamic_callback', r'^videa\|'),
        "longvideo|": ('handle_long_video_callback', r'^longvideo\|'),
    }
    for prefix, (handler, pattern) in registrations.items():
        assert BOT_SOURCE.count(f'("{prefix}", "{handler}")') == 1
        assert BOT_SOURCE.count(
            f'CallbackQueryHandler({handler}, pattern=r"{pattern}")'
        ) == 1

    affected_handlers = "\n".join((
        _between("async def _handle_storyboard2_callback_impl", "async def handle_storyboard2_callback"),
        _between("async def handle_video_product_pending_media", "async def open_prompt_video_finalization_from_state"),
        _between("async def handle_long_video_callback", "async def handle_storyboard_pack_callback"),
        _between("async def video_idea_render_exact_parent", "async def handle_video_idea_dynamic_callback"),
        _between("async def handle_video_idea_dynamic_callback", "def video_idea_admin_main_text"),
        _between("async def handle_storyboard_image_callback", "async def cmd_tool_test_workflow_image"),
    ))
    assert "Có lỗi khi xử lý lệnh" not in affected_handlers
    assert "create_product_video_job" not in affected_handlers
    assert "provider.submit" not in affected_handlers
    assert "charge_wallet" not in affected_handlers


def test_storyboard_back_callbacks_are_navigation_only_and_keep_quick_image_owner():
    callback_impl = _between(
        "async def _handle_create_media_callback_impl",
        "async def handle_create_media_callback",
    )
    assert 'quick_image_callback_namespace(state) == "vstoryimg"' in callback_impl
    assert 'back_callback="vstory|assets_screen"' in callback_impl
    assert 'context_return_callback="vstory|image_return"' in callback_impl

    storyboard_owner = _between(
        "async def handle_storyboard_image_callback",
        "async def cmd_tool_test_workflow_image",
    )
    assert 'callback_data=f"create_media|{suffix}"' in storyboard_owner
    assert "storyboard2_render(query, context, readonly)" in storyboard_owner
    cancel = storyboard_owner[
        storyboard_owner.index('if suffix == "cancel":'):
        storyboard_owner.index("return await _handle_create_media_callback_impl")
    ]
    assert "handle_create_media_callback" not in cancel
    assert 'board["active_scene_index"]' in cancel
    assert 'board["active_slot"]' in cancel
    assert 'video_storyboard2.move(board, "assets", push=False, awaiting_input="")' in cancel
    assert "save_storyboard2_state(context, board)" in cancel
    assert "clear_quick_image_flow(uid)" in cancel
    assert 'context.user_data["video_scene3_image_handoff_active"] = False' in cancel
    assert "storyboard2_render(query, context, board)" in cancel
    for forbidden in ("create_image(", "provider.submit", "create_invoice", "charge_wallet"):
        assert forbidden not in storyboard_owner


def test_idea_render_failure_preserves_parent_state_and_does_not_fall_through():
    handler = _between(
        "async def handle_video_idea_dynamic_callback",
        "def video_idea_admin_main_text",
    )
    failure_block = _between(
        '"video_idea_exact_parent_render_failed | product=%s preset=%s exception=%s"',
        "clear_developing_video_pending(uid)",
    )
    assert "restore_developing_video_pending(uid, \"videoidea\", state, \"idea2_preview\")" in failure_block
    assert "chưa tạo tác vụ" in failure_block
    assert "chưa gọi nguồn dựng" in failure_block
    assert "chưa trừ Xu" in failure_block
    approval_tail = _between(
        'save_developing_video_plan(uid, "videoidea", {',
        "return rendered",
    )
    assert approval_tail.index("clear_developing_video_pending(uid)") > approval_tail.index("rendered =")
