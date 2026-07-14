from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _state() -> dict:
    return video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu sản phẩm bằng hai cảnh trọn ý",
    )


@pytest.mark.parametrize("key", [key for key, _label in video_scene3_flow.CREATIVE_CONTROLS])
def test_each_creative_item_has_five_local_suggestions_and_no_side_effects(key: str):
    state = _state()
    suggestions = video_scene3_flow.creative_suggestions(state, key)
    assert len(suggestions) == 5
    assert len(set(suggestions)) == 5
    assert all(str(value).strip() for value in suggestions)
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


@pytest.mark.parametrize(
    "key",
    [
        "voiceover", "captions", "cta", "scene_text", "preserve_source_audio",
        "music_mood", "transition_style", "target_duration",
    ],
)
def test_each_text_content_option_has_five_editable_local_suggestions(key: str):
    suggestions = video_scene3_flow.content_addon_suggestions(_state(), key)
    assert len(suggestions) == 5
    assert len(set(suggestions)) == 5


@pytest.mark.parametrize("position", [key for key, _label in video_scene3_flow.LOGO_POSITIONS])
def test_logo_and_copyright_safe_zones_save_all_six_positions(position: str):
    state = video_scene3_flow.configure_content_safe_zone(
        _state(),
        "logo_safe_zone",
        position=position,
    )
    state = video_scene3_flow.configure_content_safe_zone(
        state,
        "watermark_safe_zone",
        position=position,
    )
    planner = video_scene3_flow.planner_content_addons(state)
    assert planner["logo_safe_zone"] == position
    assert planner["watermark_safe_zone"] == position
    assert state["content_affecting_addons"]["logo_safe_zone"]["value"]["applied_to_mp4"] is False


@pytest.mark.parametrize("position", [key for key, _label in video_scene3_flow.LOGO_POSITIONS])
def test_logo_image_and_watermark_text_are_separate_and_positioned(position: str):
    state = video_scene3_flow.configure_post_asset(
        _state(),
        "logo_image",
        file_id="telegram-logo-id",
        file_unique_id="telegram-logo-unique",
        mime_type="image/png",
    )
    state = video_scene3_flow.configure_post_position(state, "logo_image", position)
    state = video_scene3_flow.configure_watermark_text(state, "© TOAN AAS")
    state = video_scene3_flow.configure_post_position(state, "watermark_text", position)

    logo = state["postproduction_addons"]["logo_image"]["value"]
    watermark = state["postproduction_addons"]["watermark_text"]["value"]
    assert logo["asset_file_id"] == "telegram-logo-id"
    assert logo["position"] == position
    assert logo["width_ratio"] == 0.12
    assert logo["max_width_ratio"] == 0.18
    assert logo["preserve_aspect_ratio"] is True
    assert "text" not in logo
    assert watermark["text"] == "© TOAN AAS"
    assert watermark["position"] == position
    assert "asset_file_id" not in watermark
    assert logo["applied_to_mp4"] is False
    assert watermark["applied_to_mp4"] is False


def test_public_post_menu_removes_duplicate_image_watermark_and_mandatory_mp4_option():
    public_keys = [key for key, _label in video_scene3_flow.PUBLIC_POST_ADDONS]
    legacy_keys = [key for key, _label in video_scene3_flow.POST_ADDONS]
    assert "logo_image" in public_keys
    assert "watermark_text" in public_keys
    assert "watermark_image" not in public_keys
    assert "mp4_export" not in public_keys
    assert "watermark_image" in legacy_keys
    assert "mp4_export" in legacy_keys
    assert video_scene3_flow.planner_post_addons(_state())["output_packaging"] is True


def test_post_inputs_inherit_the_matching_content_safe_zone_without_duplicate_configuration():
    state = video_scene3_flow.configure_content_safe_zone(_state(), "logo_safe_zone", position="bottom_left")
    state = video_scene3_flow.configure_content_safe_zone(state, "watermark_safe_zone", position="top_center")
    state = video_scene3_flow.configure_post_asset(state, "logo_image", file_id="logo")
    state = video_scene3_flow.configure_watermark_text(state, "© TOAN AAS")
    assert state["postproduction_addons"]["logo_image"]["value"]["position"] == "bottom_left"
    assert state["postproduction_addons"]["watermark_text"]["value"]["position"] == "top_center"


@pytest.mark.parametrize("key", sorted(video_scene3_flow.AUDIO_POST_ADDONS))
def test_every_audio_addon_has_editable_volume_without_engine_side_effects(key: str):
    assert video_scene3_flow.AUDIO_VOLUME_LEVELS == (20, 40, 60, 80, 100)
    state = video_scene3_flow.configure_audio_volume(_state(), key, 60)
    entry = state["postproduction_addons"][key]
    assert entry["enabled"] is True
    assert entry["value"]["volume_percent"] == 60
    assert entry["value"]["applied_to_mp4"] is False
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }
    assert video_scene3_flow.preconfirm_audio_side_effects(state) == {
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
    }


@pytest.mark.parametrize(
    ("choice", "voice_type", "voice_source"),
    [
        ("default_female", "female", "approved_default"),
        ("default_male", "male", "approved_default"),
        ("custom_voice", "custom_voice", "user_or_saved_asset"),
    ],
)
def test_voice_choices_cover_default_female_default_male_and_personal_voice(
    choice: str,
    voice_type: str,
    voice_source: str,
):
    state = _state()
    if choice == "custom_voice":
        state["reference_assets"] = {
            "items": [{
                "type": "voice_audio",
                "media_kind": "audio",
                "file_id": "voice-file-id",
                "file_unique_id": "voice-file-unique",
                "mime_type": "audio/ogg",
                "owner_user_id": 123,
                "source_message_id": 456,
                "provider_uploaded": False,
            }],
        }
    state = video_scene3_flow.configure_voice_choice(state, choice, user_id=123)
    voice = state["postproduction_addons"]["voice"]
    assert voice["enabled"] is True
    assert voice["value"]["voice_choice"] == choice
    assert voice["value"]["voice_type"] == voice_type
    assert voice["value"]["voice_source"] == voice_source
    assert voice["value"]["custom_voice_required"] is (choice == "custom_voice")
    if choice == "custom_voice":
        assert voice["value"]["asset_file_id"] == "voice-file-id"
        assert voice["value"]["asset_owner_user_id"] == 123
        assert voice["value"]["custom_voice_asset_present"] is True


def test_personal_voice_rejects_missing_or_cross_user_assets_without_enabling_addon():
    state = _state()
    state["reference_assets"] = {
        "items": [{
            "type": "voice_audio",
            "media_kind": "audio",
            "file_id": "another-user-voice",
            "owner_user_id": 999,
        }],
    }
    result = video_scene3_flow.configure_voice_choice(state, "custom_voice", user_id=123)
    assert result["postproduction_addons"]["voice"]["enabled"] is False
    assert result["postproduction_addons"]["voice"]["value"] == ""
    assert video_scene3_flow.personal_voice_asset(state, 123) == {}


@pytest.mark.parametrize("source_choice", ["choose_existing", "create_new"])
@pytest.mark.parametrize("vocal_mode", ["instrumental", "with_lyrics"])
def test_music_source_and_vocal_mode_are_explicit_planning_choices(
    source_choice: str,
    vocal_mode: str,
):
    state = video_scene3_flow.configure_music_source(_state(), source_choice)
    state = video_scene3_flow.configure_music_vocal_mode(state, vocal_mode)
    state = video_scene3_flow.configure_post_note(state, "music", "Nhạc ấm áp, lời ngắn nếu dùng bản có lời")
    music = state["postproduction_addons"]["music"]
    assert music["enabled"] is True
    assert music["value"]["music_source_choice"] == source_choice
    assert music["value"]["vocal_mode"] == vocal_mode
    assert music["value"]["music_request"].startswith("Nhạc ấm áp")
    assert music["value"]["generation_planned_only"] is (source_choice == "create_new")
    assert music["value"]["applied_to_mp4"] is False
    assert video_scene3_flow.preconfirm_side_effects(state)["provider_called"] is False


def test_audio_addons_default_off_and_public_controls_cover_view_edit_remove_volume_and_back():
    state = _state()
    assert all(
        state["postproduction_addons"][key]["enabled"] is False
        for key in video_scene3_flow.AUDIO_POST_ADDONS
    )
    namespace = {
        "video_scene3_flow": video_scene3_flow,
        "video_scene3_keyboard": lambda rows: rows,
    }
    exec(compile(_function_source("video_scene3_post_detail_keyboard"), "<audio-detail-keyboard>", "exec"), namespace)
    keyboard = namespace["video_scene3_post_detail_keyboard"]
    for key in sorted(video_scene3_flow.AUDIO_POST_ADDONS):
        rows = keyboard({**state, "active_post_addon": key})
        callbacks = {callback for row in rows for _label, callback in row}
        assert "vprofile|post_volume" in callbacks
        assert "vprofile|post_edit" in callbacks
        assert "vprofile|post_view" in callbacks or key in {"voice", "music"}
        assert "vprofile|post_remove" in callbacks
        assert "vprofile|post_detail_done" in callbacks
    volume_namespace = {
        "video_scene3_flow": video_scene3_flow,
        "video_scene3_keyboard": lambda rows: rows,
        "InlineKeyboardMarkup": object,
    }
    exec(compile(_function_source("video_scene3_post_volume_keyboard"), "<audio-volume-keyboard>", "exec"), volume_namespace)
    volume_rows = volume_namespace["video_scene3_post_volume_keyboard"]()
    assert [callback for _label, callback in volume_rows[0]] == [
        f"vprofile|post_volume_set|{value}" for value in (20, 40, 60, 80, 100)
    ]
    assert "vprofile|post_volume_done" in {callback for row in volume_rows for _label, callback in row}


def test_public_handlers_wire_guided_input_logo_text_positions_and_quality_guide():
    handler = _function_source("handle_video_profile_studio_callback")
    pending_text = _function_source("handle_video_profile_studio_pending_text")
    pending_media = _function_source("handle_video_scene3_pending_media")
    renderer = _function_source("video_profile_scene1_render")

    for action in (
        "creative_suggest", "creative_pick", "creative_custom",
        "content_suggest_item", "content_pick", "content_custom",
        "content_position_set", "post_asset", "post_text", "post_position_set",
        "post_voice_choice", "post_music_source", "post_music_mode",
        "post_volume", "post_volume_set", "post_volume_done",
        "quality_info_done",
    ):
        assert f'if action == "{action}"' in handler
    assert 'if step == "await_post_text"' in pending_text
    assert '"await_post_asset_upload"' in pending_media
    assert "configure_post_asset" in pending_media
    assert "provider_router" not in pending_media
    assert "requests." not in pending_media
    assert "httpx." not in pending_media
    assert '"owner_user_id": safe_int(getattr(update.effective_user, "id", 0), 0)' in pending_media
    assert "configure_voice_choice" in pending_media
    for step in (
        "creative_detail", "creative_suggestions", "content_detail", "content_suggestions",
        "content_position", "post_position", "post_volume", "quality_guide",
    ):
        assert f'"{step}"' in renderer


def test_quality_copy_is_differentiated_without_public_provider_or_model_names():
    block_start = BOT_SOURCE.index("VIDEO_SCENE3_QUALITY_PUBLIC_SPECS = {")
    block_end = BOT_SOURCE.index("VIDEO_B14_3_CREATIVE_CHOICES =", block_start)
    block = BOT_SOURCE[block_start:block_end]
    for price in (200, 300, 400, 500, 600, 800, 1000, 1200, 1500):
        assert f"{price}:" in block
    for secret_name in ("ShopAIKey", "Key4U", "veo", "kling", "grok", "minimax"):
        assert secret_name.lower() not in block.lower()
    guide = _function_source("video_scene3_quality_guide_text")
    assert "không phải lời hứa hoàn tất" in guide
    assert "Chỉ video cuối hợp lệ đã gửi mới được tính Xu" in guide


def test_preconfirm_contract_remains_zero_after_all_new_planning_configuration():
    state = video_scene3_flow.set_entry(
        _state(),
        "creative_controls",
        "visual_style",
        video_scene3_flow.creative_suggestions(_state(), "visual_style")[0],
    )
    state = video_scene3_flow.set_entry(
        state,
        "content_affecting_addons",
        "captions",
        video_scene3_flow.content_addon_suggestions(state, "captions")[0],
    )
    state = video_scene3_flow.configure_content_safe_zone(state, "logo_safe_zone", position="top_right")
    state = video_scene3_flow.configure_post_asset(state, "logo_image", file_id="logo")
    state = video_scene3_flow.configure_post_position(state, "logo_image", "top_right")
    state = video_scene3_flow.configure_watermark_text(state, "© TOAN AAS")
    state = video_scene3_flow.configure_post_position(state, "watermark_text", "bottom_right")
    assert video_scene3_flow.preconfirm_side_effects(state) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }
    assert video_scene3_flow.preconfirm_audio_side_effects(state) == {
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
    }


def test_product_video_has_one_authoritative_final_confirm_handler_contract():
    assert BOT_SOURCE.count("async def handle_product_video_public_confirm_callback(") == 1
    assert '"product_video_confirm_handler_count": 1' in BOT_SOURCE
    assert 'if action == "b14_confirm" and not bool(getattr(context, "_product_video_authoritative_confirm", False))' in BOT_SOURCE


def test_actual_telegram_callback_routes_guided_screens_and_legacy_redirects_without_side_effects():
    handler_source = _function_source("handle_video_profile_studio_callback")

    def save_state(context, state):
        clean = video_scene3_flow.normalize_state(state)
        context.user_data["video_profile_studio"] = clean
        return clean

    def read_state(context):
        return video_scene3_flow.normalize_state(context.user_data.get("video_profile_studio") or {})

    def step_state(context, state, step, *, push=True, **fields):
        history = list(state.get("history") or [])
        current = str(state.get("step") or "menu")
        if push and current != step:
            history.append(current)
        return save_state(context, {**state, **fields, "step": step, "history": history[-40:]})

    def return_parent(context, state, parent, **fields):
        history = list(state.get("history") or [])
        if history and history[-1] == parent:
            history.pop()
        return save_state(context, {**state, **fields, "step": parent, "history": history})

    async def render(_query, state, _lang):
        return save_state(context, state)

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "video_profile_studio_state": read_state,
        "save_video_profile_studio_state": save_state,
        "video_profile_studio_step": step_state,
        "video_scene3_return_to_parent": return_parent,
        "video_scene2_action_allowed": lambda _state, _action: True,
        "video_scene2_reconcile_state": lambda _context, state: state,
        "video_profile_scene1_render": render,
        "video_scene3_flow": video_scene3_flow,
        "safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "VIDEO_PRODUCT_REGISTRY": {},
    }
    exec(compile("from __future__ import annotations\nasync " + handler_source, "<scene3ux2-handler>", "exec"), namespace)
    handler = namespace["handle_video_profile_studio_callback"]

    class Query:
        data = ""
        from_user = SimpleNamespace(id=123)

        async def answer(self, *_args, **_kwargs):
            return None

    query = Query()
    context = SimpleNamespace(user_data={})
    state = _state()
    state.update({"scene_count": 2, "step": "creative_controls", "history": ["materials"]})
    save_state(context, state)
    update = SimpleNamespace(callback_query=query)

    async def run_action(callback: str):
        query.data = callback
        await handler(update, context)
        current = read_state(context)
        assert video_scene3_flow.preconfirm_side_effects(current)["provider_called"] is False
        return current

    async def run_flow():
        state = await run_action("vprofile|creative|visual_style")
        assert state["step"] == "creative_detail"
        state = await run_action("vprofile|creative_suggest")
        assert state["step"] == "creative_suggestions"
        state = await run_action("vprofile|creative_pick|2")
        assert state["step"] == "creative_detail"
        assert state["creative_controls"]["visual_style"]["value"] == video_scene3_flow.creative_suggestions(state, "visual_style")[1]
        state = await run_action("vprofile|creative_detail_done")
        assert state["step"] == "creative_controls"

        state = save_state(context, {**state, "step": "content_addons", "history": ["creative_controls"]})
        state = await run_action("vprofile|content|logo_safe_zone")
        assert state["step"] == "content_detail"
        state = await run_action("vprofile|content_position")
        assert state["step"] == "content_position"
        state = await run_action("vprofile|content_position_set|bottom_left")
        assert state["step"] == "content_detail"
        assert video_scene3_flow.planner_content_addons(state)["logo_safe_zone"] == "bottom_left"
        state = await run_action("vprofile|content_detail_done")
        assert state["step"] == "content_addons"
        state = await run_action("vprofile|content|captions")
        state = await run_action("vprofile|content_suggest_item")
        assert state["step"] == "content_suggestions"
        state = await run_action("vprofile|content_pick|1")
        assert state["step"] == "content_detail"
        assert state["content_affecting_addons"]["captions"]["enabled"] is True

        state = save_state(context, {
            **state,
            "step": "post_addons",
            "history": ["full_review"],
            "reference_assets": {"items": [{"type": "logo", "file_id": "material-logo", "mime_type": "image/png"}]},
        })
        state = await run_action("vprofile|post_toggle|watermark_image")
        assert state["step"] == "post_detail"
        assert state["active_post_addon"] == "logo_image"
        assert state["postproduction_addons"]["logo_image"]["value"]["asset_file_id"] == "material-logo"
        state = await run_action("vprofile|post_detail_done")
        assert state["step"] == "post_addons"
        state = await run_action("vprofile|post_toggle|mp4_export")
        assert state["step"] == "post_addons"
        state = await run_action("vprofile|post_toggle|subtitles")
        state = await run_action("vprofile|post_enable")
        assert state["postproduction_addons"]["subtitles"]["enabled"] is True
        state = await run_action("vprofile|post_detail_done")
        state = await run_action("vprofile|post_toggle|voice")
        state = await run_action("vprofile|post_voice_choice|custom_voice")
        assert state["step"] == "await_material_upload"
        assert state["input_target"] == "voice_audio"
        assert state["postproduction_addons"]["voice"]["enabled"] is False
        state = save_state(context, {
            **state,
            "step": "post_detail",
            "active_post_addon": "voice",
            "reference_assets": {"items": [{
                "type": "voice_audio",
                "media_kind": "audio",
                "file_id": "owned-voice",
                "owner_user_id": 123,
            }]},
        })
        state = await run_action("vprofile|post_voice_choice|custom_voice")
        assert state["postproduction_addons"]["voice"]["value"]["asset_file_id"] == "owned-voice"
        state = await run_action("vprofile|post_voice_choice|default_female")
        assert state["postproduction_addons"]["voice"]["value"]["voice_type"] == "female"
        state = await run_action("vprofile|post_volume")
        assert state["step"] == "post_volume"
        state = await run_action("vprofile|post_volume_set|60")
        assert state["step"] == "post_detail"
        assert state["postproduction_addons"]["voice"]["value"]["volume_percent"] == 60
        state = await run_action("vprofile|post_detail_done")
        state = await run_action("vprofile|post_toggle|music")
        state = await run_action("vprofile|post_music_source|create_new")
        state = await run_action("vprofile|post_music_mode|with_lyrics")
        state = await run_action("vprofile|post_volume")
        state = await run_action("vprofile|post_volume_set|40")
        music = state["postproduction_addons"]["music"]["value"]
        assert music["music_source_choice"] == "create_new"
        assert music["vocal_mode"] == "with_lyrics"
        assert music["volume_percent"] == 40
        assert music["generation_planned_only"] is True

        state = save_state(context, {**state, "step": "quality", "history": ["aspect_ratio"]})
        state = await run_action("vprofile|quality_info")
        assert state["step"] == "quality_guide"
        state = await run_action("vprofile|quality_info_done")
        assert state["step"] == "quality"

    asyncio.run(run_flow())
