import inspect

import bot
from services import subdub_blackbox_contracts


def test_language_blackboxes_keep_vietnamese_english_chinese_separate():
    expected = {
        "vi": ("vietnamese", "vi"),
        "English": ("english", "en"),
        "zh-CN": ("chinese", "zh-cn"),
    }
    for requested, (family, locale) in expected.items():
        resolved = subdub_blackbox_contracts.resolve_language_blackbox(requested)
        assert resolved.family == family
        assert resolved.requested_locale == locale
        assert resolved.translation_locale == locale
        assert resolved.tts_locale == locale


def test_international_blackbox_preserves_requested_locale():
    for requested, locale in (
        ("ja-JP", "ja-jp"),
        ("ko-KR", "ko-kr"),
        ("th-TH", "th-th"),
        ("ar-SA", "ar-sa"),
        ("hi-IN", "hi-in"),
        ("ru-RU", "ru-ru"),
    ):
        resolved = subdub_blackbox_contracts.resolve_language_blackbox(requested)
        assert resolved.family == "international"
        assert resolved.requested_locale == locale
        assert resolved.translation_locale == locale
        assert resolved.tts_locale == locale


def test_lane_blackboxes_are_independent_and_dub_defaults_to_muted_source():
    subtitle = subdub_blackbox_contracts.resolve_lane_blackbox(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    dub = subdub_blackbox_contracts.resolve_lane_blackbox(bot.VIDEO_SUBTITLE_MODE_DUB)
    combo = subdub_blackbox_contracts.resolve_lane_blackbox(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    assert subtitle.lane == "subtitle"
    assert subtitle.uses_subtitles and subtitle.uses_translation and not subtitle.uses_tts
    assert dub.lane == "dub"
    assert dub.uses_translation and dub.uses_tts and not dub.keep_original_audio_default
    assert combo.lane == "combo"
    assert combo.uses_subtitles and combo.uses_translation and combo.uses_tts
    assert not combo.keep_original_audio_default


def test_dub_and_combo_share_restored_pr400_pipeline_contract():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subdub_blackboxes.run_subdub_lane_blackbox(" in source
    assert "runner=subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "synthesize_segments=_synthesize_dub_segments_for_blackbox" in source
    assert "build_timeline_audio=build_dub_timeline_audio" in source
    assert "render_video=_render_video_for_blackbox" in source
    assert "synthesize_canonical_dub_segment_chunks(" not in source


def test_original_audio_cannot_leak_when_user_did_not_enable_it():
    assert bot.subdub_audio_mix_state_fields({"original_audio_volume_percent": 100})["original_audio_volume_percent"] == 0
    explicit = bot.subdub_audio_mix_state_fields(
        {"keep_original_audio": True, "original_audio_volume_percent": 30}
    )
    assert explicit["keep_original_audio"] is True
    assert explicit["original_audio_volume_percent"] == 30


def test_blackbox_contract_does_not_change_subtitle_renderer_or_delivery_route():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subdub_blackboxes.run_subdub_lane_blackbox(" in source
    assert "prepare_subtitles=_prepare_subtitles_for_blackbox" in source
    assert "render_video=_render_video_for_blackbox" in source
    assert "video_dubbing_send_final_outputs" not in source
