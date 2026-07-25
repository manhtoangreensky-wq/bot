from __future__ import annotations

from pathlib import Path

import pytest

from services import video_long_planning, video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def _ready_state(product_type: str = "video_ai_real") -> dict:
    state = video_tail9.new_state(
        product_type=product_type,
        session_id=f"session-{product_type}",
        scene_count=3,
        ratio="9:16",
    )
    return video_tail9.select_package(
        state,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"total_xu": 300, "scene_count": 3},
        capability_snapshot={"ok": True, "engine_route": state["engine_route"]},
    )


@pytest.mark.parametrize(
    ("product_type", "engine_route", "source_audio"),
    [
        ("video_ai_real", "video_ai_canonical", False),
        ("script_image_video", "script_to_video", False),
        ("storyboard_prompt", "storyboard_to_video", False),
        ("video_trend", "trend_video", False),
        ("frame_video_local", "frame_video_render", False),
        ("self_shot_scene_change", "self_shot_scene_change", True),
        ("self_shot_cinematic_transform", "self_shot_cinematic_transform", True),
    ],
)
def test_shared_tail_keeps_product_specific_engine_routes(
    product_type: str,
    engine_route: str,
    source_audio: bool,
) -> None:
    state = video_tail9.new_state(product_type=product_type, session_id="one")
    assert state["engine_route"] == engine_route
    assert state["audio_config"]["source_audio_available"] is source_audio
    assert state["audio_config"]["source_audio"] is source_audio


def test_tail_state_is_scoped_to_product_session_and_plan_revision() -> None:
    state = video_tail9.new_state(
        product_type="storyboard_prompt",
        session_id="storyboard-session",
        plan_revision=4,
    )
    assert set(video_tail9.STATE_FIELDS).issubset(state)
    assert video_tail9.scope_matches(
        state,
        product_type="storyboard_prompt",
        session_id="storyboard-session",
        plan_revision=4,
    )
    assert not video_tail9.scope_matches(
        state,
        product_type="video_trend",
        session_id="storyboard-session",
        plan_revision=4,
    )


def test_audio_toggles_and_zero_to_two_hundred_volume_are_canonical() -> None:
    state = video_tail9.new_state(
        product_type="self_shot_scene_change",
        session_id="selfshot-session",
    )
    state = video_tail9.toggle_audio(state, "dubbing")
    assert state["audio_config"]["dubbing"] is True
    state = video_tail9.toggle_audio(state, "dubbing")
    assert state["audio_config"]["dubbing"] is False
    assert video_tail9.set_volume(state, "music", -5)["audio_config"]["volumes"]["music"] == 0
    assert video_tail9.set_volume(state, "music", 250)["audio_config"]["volumes"]["music"] == 200
    assert state["audio_config"]["clipping_guard"] is True
    assert state["audio_config"]["ducking"] is True


def test_new_tail_state_keeps_optional_branding_unconfigured() -> None:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        session_id="unconfigured-branding",
    )

    assert state["logo_status"] == "not_configured"
    assert state["watermark_status"] == "not_configured"
    assert state["logo_config"]["position"] == ""
    assert state["watermark_config"]["position"] == ""


def test_summary_preparation_keeps_optional_tail_parts_nonblocking() -> None:
    state = video_tail9.new_state(
        product_type="video_trend",
        session_id="summary-optional",
    )
    state.update({
        "content_source": "content_profiles",
        "content_mode": "suggestions",
        "selected_prompt": "Prompt video đã duyệt",
        "prompt_revision": 1,
    })

    summary = video_tail9.prepare_summary(state)

    assert summary["audio_status"] == "not_configured"
    assert summary["logo_status"] == "not_configured"
    assert summary["watermark_status"] == "not_configured"
    assert summary["summary_status"] == "ready"


def test_summary_back_and_direct_open_use_the_review_contract() -> None:
    summary_keyboard = _between(
        "def video_tail9_summary_keyboard",
        "def video_tail9_public_blocker_text",
    )
    handler = _between(
        "async def handle_video_tail_callback",
        "async def handle_video_tail9_pending_text",
    )

    assert '[("⬅️ Quay lại", "video_tail|review|open"), ("🏠 Menu chính", "menu|main")]' in summary_keyboard
    assert 'if action == "summary":\n            tail = video_tail9.prepare_summary(tail)' in handler
    assert 'return await video_tail9_render(query, uid, context, "summary")' in handler
    assert 'if action == "back":\n            return await video_tail9_render(query, uid, context, "review")' in handler


def test_source_audio_capability_does_not_override_missing_source_stream() -> None:
    state = video_tail9.new_state(
        product_type="self_shot_scene_change",
        session_id="silent-source",
    )
    state["audio_config"]["source_audio_available"] = False
    state["audio_config"]["source_audio"] = False
    normalized = video_tail9.normalize_state(state)
    assert normalized["audio_config"]["source_audio_available"] is False
    assert normalized["audio_config"]["source_audio"] is False


def test_capability_failure_blocks_package_invoice_and_confirm() -> None:
    state = video_tail9.new_state(product_type="video_ai_real", session_id="blocked")
    with pytest.raises(ValueError, match="execution_owner_unavailable"):
        video_tail9.select_package(
            state,
            quality_tier_id="300",
            package_id="product_video_300",
            pricing_snapshot={"total_xu": 300},
            capability_snapshot={"ok": False, "reason": "execution_owner_unavailable"},
        )
    with pytest.raises(ValueError, match="package_not_selected"):
        video_tail9.confirm_once(state, "confirm-1")


def test_final_confirm_is_idempotent() -> None:
    state = _ready_state()
    confirmed, created = video_tail9.confirm_once(state, "confirm-token")
    assert created is True
    duplicate, created_again = video_tail9.confirm_once(confirmed, "confirm-token")
    assert created_again is False
    assert duplicate["confirm_token"] == "confirm-token"


def test_delivery_receipt_charge_and_progress_require_real_delivery() -> None:
    state, _created = video_tail9.confirm_once(_ready_state(), "confirm-token")
    rendered = video_tail9.update_delivery_truth(
        state,
        final_mp4_valid=True,
        delivery_message_id="",
    )
    assert rendered["status_stage"] == "delivering"
    assert video_tail9.public_progress(rendered) == 90
    with pytest.raises(ValueError, match="receipt_before_delivery"):
        video_tail9.update_delivery_truth(
            state,
            final_mp4_valid=True,
            delivery_message_id="",
            receipt_created=True,
        )
    delivered = video_tail9.update_delivery_truth(
        state,
        final_mp4_valid=True,
        delivery_message_id="telegram-message-42",
        receipt_created=True,
        charged=True,
    )
    assert delivered["status_stage"] == "delivered"
    assert delivered["receipt_state"] == "created"
    assert delivered["charge_state"] == "charged"
    assert video_tail9.public_progress(delivered) == 100


def test_callback_namespace_has_one_owner_and_one_registered_handler() -> None:
    owner_map = _between(
        "VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES = (",
        "\n)\n\n\ndef video_route_expected_handler",
    )
    assert owner_map.count('(\"video_tail|\", \"handle_video_tail_callback\")') == 1
    registration = (
        'CallbackQueryHandler(handle_video_tail_callback, '
        'pattern=r"^video_tail\\|", block=True)'
    )
    assert BOT_SOURCE.count(registration) == 1
    assert BOT_SOURCE.index(registration) < BOT_SOURCE.index(
        'CallbackQueryHandler(handle_video_product_callback, '
        'pattern=r"^vproduct\\|(?!b14_confirm(?:\\||$))")'
    )


def test_selfshot_legacy_tail_callbacks_are_read_only_redirects() -> None:
    handler = _between(
        "async def handle_video_product_callback",
        "async def handle_video_product_pending_text",
    )
    selfshot2 = handler[handler.index('if action == "ss2":'):handler.index('if action == "ss3":')]
    selfshot3 = handler[handler.index('if action == "ss3":'):handler.index('if action == "scene3_mode":')]
    assert "legacy_tail_screen" in selfshot2
    assert "legacy_tail_screen" in selfshot3
    assert "video_b14_prepare_project_for_invoice" not in selfshot2
    assert "video_b14_prepare_project_for_invoice" not in selfshot3
    assert 'return await video_tail9_render(query, uid, context, legacy_tail_screen)' in selfshot2
    assert 'return await video_tail9_render(query, uid, context, legacy_tail_screen)' in selfshot3


def test_tail_media_and_text_intakes_have_exact_owner_and_back_target() -> None:
    assert '"awaiting_video_tail9_logo"' in BOT_SOURCE
    assert 'callback_data="video_tail|logo|open"' in BOT_SOURCE
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_tail_callback, pattern=r"^video_tail\\|", block=True)'
    ) == 1
    message_dispatch = _between("async def handle_message", "def run_video_trend_catalog_refresh_once")
    assert message_dispatch.count("handle_video_tail9_pending_text(update, context)") == 1


def test_tail_keyboards_have_no_duplicate_volume_or_logo_skip_callbacks() -> None:
    volume = _between(
        "def video_tail9_volume_keyboard",
        "def video_tail9_logo_text",
    )
    assert volume.count('f"video_tail|audio|custom|{key}"') == 1
    logo = _between(
        "def video_tail9_logo_keyboard",
        "def video_tail9_position_keyboard",
    )
    assert '"video_tail|logo|done"' in logo
    assert '"video_tail|logo|skip"' in logo
    assert logo.count('"video_tail|quality|open"') == 0


def test_tail_confirmation_is_only_persisted_after_a_real_job_exists() -> None:
    handler = _between(
        "async def handle_video_tail_callback",
        "async def handle_video_tail9_pending_text",
    )
    delegated = handler.index("await handle_product_video_public_confirm_callback")
    persisted = handler.index("video_tail9.confirm_once", delegated)
    assert delegated < persisted
    assert 'if job_id > 0:' in handler[delegated:persisted]
    assert 'tail["job_id"] = str(job_id)' in handler[persisted:]


def test_long_video_keeps_internal_engine_lock_but_opens_shared_commercial_preview() -> None:
    assert video_long_planning.PUBLIC_ENABLED is False
    assert video_long_planning.SCENE_DURATION_SECONDS == 600
    contract = video_tail9.commercial_contract("long_video")
    assert contract["public_planning_enabled"] is True
    assert contract["execution_enabled"] is False
    assert contract["execution_blocker"] == "long_video_under_upgrade"
    assert contract["scene_duration_seconds"] == 600
    handler = _between("async def handle_long_video_callback", "async def handle_storyboard_pack_callback")
    assert "start_public_video_scene2_step" in handler
    assert '"multi_scene_film"' in handler
    assert "handle_video_product_callback" not in handler
    assert "query.data =" not in handler


def test_preconfirm_tail_contract_does_not_call_provider_or_mutate_wallet() -> None:
    source = _between(
        "VIDEO_TAIL9_STATE_KEY =",
        "async def handle_video_product_callback",
    )
    assert "provider.submit" not in source
    assert "requests.post" not in source
    assert "wallet_deduct" not in source
    assert "deduct_xu" not in source
    assert "video_b14_prepare_project_for_invoice" not in source
