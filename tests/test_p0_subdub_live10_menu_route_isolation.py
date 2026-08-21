from pathlib import Path
import re


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(name):
    pattern = rf"(?ms)^(?:async )?def {re.escape(name)}\b.*?(?=^(?:async )?def |\Z)"
    match = re.search(pattern, BOT_SOURCE)
    assert match, f"missing function source: {name}"
    return match.group(0)


def test_live10_four_lane_menu_callbacks_are_isolated():
    source = _function_source("video_dubbing_menu_keyboard")
    for mode in (
        "VIDEO_SUBTITLE_MODE_CREATE",
        "VIDEO_SUBTITLE_MODE_TRANSLATE",
        "VIDEO_SUBTITLE_MODE_DUB",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB",
    ):
        assert f"VIDEO_SUBTITLE_MODE_{mode.removeprefix('VIDEO_SUBTITLE_MODE_')}" in source
    assert 'callback_data="menu|main"' in source
    assert 'callback_data="menu|translation_media_file"' not in source
    assert 'callback_data="menu|translation_media_audio"' not in source


def test_live10_source_and_combo_buttons_route_to_subdub_only():
    source = _function_source("video_dubbing_source_keyboard")
    assert 'callback_data="videodub|source_upload"' in source
    assert 'callback_data="videodub|back_type"' in source
    assert 'callback_data="menu|main"' in source
    assert "VIDEO_DUBBING_FLOW_HAS_SUBTITLE" in source
    assert "VIDEO_DUBBING_FLOW_NO_SUBTITLE" in source
    assert 'f"videodub|path|{VIDEO_DUBBING_FLOW_HAS_SUBTITLE}"' in source
    assert 'f"videodub|path|{VIDEO_DUBBING_FLOW_NO_SUBTITLE}"' in source


def test_live10_language_voice_and_audio_buttons_have_matching_handlers():
    language = _function_source("video_dubbing_language_keyboard")
    voice = _function_source("video_dubbing_voice_keyboard")
    mix = _function_source("subdub_audio_mix_keyboard")
    layer = _function_source("subdub_audio_layer_keyboard")
    assert "videodub|language|" in language
    assert "videodub|language_custom" in language
    assert "videodub|back_language_to_source" in language
    assert 'videodub|voice|default_female' in voice
    assert 'videodub|voice|default_male' in voice
    assert "videodub|voice_saved" in voice
    assert "videodub|voice_create" in voice
    assert "videodub|back_voice" in voice
    for callback in (
        "audio_original",
        "audio_dub",
        "back_audio_mix",
    ):
        assert f'callback_data="videodub|{callback}"' in mix
    for callback in ("audio_original_input", "audio_dub_input", "audio_keep", "audio_mix"):
        assert f"videodub|{callback}" in layer
    assert 'callback_data="menu|main"' in layer

    handler = _function_source("handle_video_dubbing_callback")
    for action in (
        "language",
        "language_custom",
        "back_language_to_source",
        "voice",
        "voice_saved",
        "voice_create",
        "back_voice",
        "audio_mix",
        "audio_original",
        "audio_dub",
        "audio_original_input",
        "audio_dub_input",
        "audio_keep",
        "back_audio_mix",
    ):
        assert f'"{action}"' in handler


def test_live10_specific_subdub_input_precedes_product_video_dispatch_once():
    source = _function_source("handle_message")
    subdub_guard = source.index("pending_subdub = get_video_dubbing_pending(uid)")
    subdub_dispatch = source.index("handle_video_dubbing_pending_text(update, context)")
    product_video = source.index("handle_video_product_pending_text")

    assert subdub_guard < subdub_dispatch < product_video
    assert source.count("handle_video_dubbing_pending_text(update, context)") == 1
    assert "VIDEO_DUBBING_PENDING_TEXT_STEPS" in source


def test_live10_all_subdub_text_states_share_the_early_owner_guard():
    start = BOT_SOURCE.index("VIDEO_DUBBING_PENDING_TEXT_STEPS = frozenset")
    end = BOT_SOURCE.index("async def handle_video_dubbing_pending_text", start)
    steps = BOT_SOURCE[start:end]
    for step in (
        "language_custom",
        "voice_custom",
        "voice_saved_select",
        "voice_speed",
        "link_input",
        "subtitle_edit_line_number",
        "subtitle_edit_line_text",
        "subtitle_find_text",
        "subtitle_replace_text",
        "subtitle_time_shift",
        "dialogue_text_input",
        "subdub_original_volume_input",
        "subdub_dub_volume_input",
    ):
        assert f'"{step}"' in steps


def test_live10_numeric_dub_volume_has_a_dedicated_pending_state():
    pending = _function_source("handle_video_dubbing_pending_text")
    assert '"subdub_original_volume_input"' in pending
    assert '"subdub_dub_volume_input"' in pending
    assert "user_numeric_audio_mix" in pending
    assert "dubbed_voice_volume_percent" in pending
    assert "handle_video_product_pending_text" not in pending
    assert "scene_count" not in pending


def test_live10_product_video_text_handlers_do_not_steal_subdub_volume_input():
    helper = _function_source("subdub_text_input_owns_message")
    assert "get_video_dubbing_pending(user_id)" in helper
    assert "VIDEO_DUBBING_PENDING_TEXT_STEPS" in helper

    for name in (
        "handle_video_product_pending_text",
        "handle_video_finalization_pending_text",
        "handle_developing_video_pending_text",
        "handle_video_idea_dynamic_pending_text",
    ):
        source = _function_source(name)
        guard = source.index("subdub_text_input_owns_message(uid)")
        scene_refs = [
            source.find('"b14_scene_custom"'),
            source.find('"waiting_scene_count"'),
            source.find('"scene_count_custom"'),
            source.find('"idea2_scene_count_custom"'),
        ]
        scene_refs = [idx for idx in scene_refs if idx >= 0]
        if scene_refs:
            assert guard < min(scene_refs), f"{name} can still steal numeric SubDub volume input"


def test_live10_terminal_panel_recovers_only_after_real_artifact_delivery():
    source = _function_source("subdub_finalize_delivered_panel")
    evidence = source.index("subdub_terminal_delivery_evidence")
    missing_evidence_guard = source.index("if not job_key or not job or not delivery_message_id")
    replacement = source.index('edit_method = "replacement_status_message"')
    terminal_commit = source.rindex("update_subtitle_dub_pipeline_job(")

    assert evidence < missing_evidence_guard < replacement < terminal_commit
    assert "await message.reply_text(" in source
    assert '"progress_percent": 100' in source
    assert '"status_panel_terminalized": True' in source
    assert "rendered is None or not effective_panel_message_id" in source
