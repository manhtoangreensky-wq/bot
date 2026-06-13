from video_prompt_quality import (
    ACTION_PACKS,
    AUDIO_MODES,
    PROMPT_EXAMPLE_SPECS,
    PROMPT_STRENGTH_LEVELS,
    STYLE_PACKS,
    build_video_prompt,
    build_video_prompt_example,
    parse_video_user_intent,
    video_prompt_library_summary,
)


def _package(text: str, **previous):
    intent = parse_video_user_intent(text, "promptvideo", previous)
    return intent, build_video_prompt(intent)


def test_video_prompt_has_required_director_sections():
    _, package = _package("luxury perfume product reveal, 15 seconds")
    prompt = package["prompt"]
    for heading in (
        "[Global Vision & Tone]",
        "[Subject / Product Lock]",
        "[Shot Breakdown]",
        "[Camera Direction]",
        "[VFX / Motion]",
        "[Audio / SFX]",
        "[Quality / Style]",
        "[Continuity Locks]",
        "[Final Hold]",
        "[Negative Constraints]",
    ):
        assert heading in prompt


def test_duration_15s_generates_seven_timed_shots():
    intent, package = _package("cinematic product story, 15 seconds")
    assert intent["duration_seconds"] == 15
    assert len(intent["shot_breakdown"]) == 7
    assert "1. [0.0-" in package["prompt"]
    assert "7. [" in package["prompt"]


def test_duration_60s_generates_reviewable_segments():
    intent, package = _package("documentary business story, 60 seconds")
    assert intent["duration_seconds"] == 60
    assert 6 <= len(intent["shot_breakdown"]) <= 10
    assert "Segment goal:" in package["prompt"]
    assert "[Segment Outline]" in package["prompt"]
    assert "Render and review each segment separately" in package["prompt"]


def test_prompt_libraries_have_required_coverage():
    summary = video_prompt_library_summary()
    assert summary["style_pack_count"] >= 20
    assert summary["action_pack_count"] >= 20
    assert summary["audio_mode_count"] >= 15
    assert summary["example_count"] >= 10
    assert "dark_angel_gothic" in STYLE_PACKS
    assert "product_luxury_reveal" in STYLE_PACKS
    assert "finger_snap_transformation" in ACTION_PACKS
    assert "product_spin_reveal" in ACTION_PACKS
    assert "voiceover_vi" in AUDIO_MODES
    assert "provider_safe" in PROMPT_STRENGTH_LEVELS


def test_genre_inference_does_not_apply_dark_fantasy_to_product_ad():
    dark_intent, dark_package = _package(
        "a man in a white shirt transforms into an original dark angel, finger snap, 15 seconds"
    )
    assert dark_intent["style_pack"] == "dark_angel_gothic"
    assert dark_intent["action_pack"] == "finger_snap_transformation"
    assert "Dark Angel / Gothic Transformation" in dark_package["prompt"]

    product_intent, product_package = _package("TikTok ad for a turquoise mini blender, 10 seconds")
    assert product_intent["genre"] == "trend_video"
    assert product_intent["style_pack"] == "tiktok_viral_product_demo"
    assert "Dark Angel" not in product_package["prompt"]
    assert "opening 1-3 seconds" in product_package["prompt"]


def test_toan_aas_request_uses_ai_automation_commercial_pack():
    intent, package = _package("TOAN AAS AI automation business promo, 15 seconds")
    assert intent["style_pack"] == "ai_automation_system_promo"
    assert "AI Automation System Promo" in package["prompt"]
    assert "dark angel" not in package["prompt"].lower()


def test_provider_safe_reduces_effect_complexity():
    _, package = _package(
        "premium product transformation with particles, 15 seconds",
        prompt_strength="provider_safe",
    )
    assert "Minimal provider-safe effects" in package["prompt"]
    assert "one slow, stable camera move per shot" in package["prompt"]
    assert "Avoid bullet-time, heavy morphing" in package["prompt"]


def test_examples_are_full_prompts_and_provider_language_can_be_english():
    assert len(PROMPT_EXAMPLE_SPECS) >= 10
    package = build_video_prompt_example("luxury_product_reveal")
    assert "[Global Vision & Tone]" in package["prompt"]
    assert "[Shot Breakdown]" in package["prompt"]
    assert "[Audio / SFX]" in package["prompt"]
    assert "[Negative Constraints]" in package["prompt"]
    assert "Goal:" in package["prompt"]


def test_prompt_preview_is_pure_planning_without_provider_or_xu_side_effects():
    intent, package = _package(
        "AI automation office product ad, 15 seconds",
        prompt_strength="director",
    )
    assert intent["prompt_strength"] == "director"
    assert package["provider_video_allowed"] is True
    assert "API key" not in package["prompt"]
    assert "Xu" not in package["prompt"]

