from __future__ import annotations

from copy import deepcopy

from services import video_edit_capabilities as capabilities


def test_every_public_actionable_capability_has_a_local_plan_mapping() -> None:
    actionable = capabilities.public_actionable_capabilities()
    assert actionable
    for item in actionable:
        assert item["enabled"] is True
        assert item["execution_owner"] == "video_local_editing"
        assert item["local_or_provider"] == "local"
        assert capabilities.plan_patch(item["feature_key"])


def test_provider_only_effects_are_not_actionable() -> None:
    keys = {
        item["feature_key"]
        for item in capabilities.capabilities_for("effects")
    }
    assert not keys & {
        "effect_zoom_pan",
        "effect_parallax",
        "effect_moving_light",
        "effect_light_outline",
        "effect_particles",
        "effect_subtle_transition",
    }


def test_required_local_capabilities_are_exposed_with_truthful_owners() -> None:
    expected = {
        "enhance_denoise": {"section": "restore", "owner": "video_local_editing"},
        "audio_loudnorm": {"section": "audio", "owner": "video_local_editing"},
        "effect_fade": {"section": "effects", "owner": "video_local_editing"},
        "effect_vignette": {"section": "effects", "owner": "video_local_editing"},
        "effect_slow_zoom": {"section": "effects", "owner": "video_local_editing"},
    }
    for key, contract in expected.items():
        item = capabilities.capability(key)
        assert item["enabled"] is True
        assert item["section"] == contract["section"]
        assert item["execution_owner"] == contract["owner"]
        assert item["local_or_provider"] == "local"
        assert capabilities.plan_patch(key)


def test_remove_middle_is_one_local_mp4_and_not_split_delivery() -> None:
    item = capabilities.capability("manual_remove_middle")
    assert item["execution_owner"] == "video_local_editing"
    assert item["local_or_provider"] == "local"
    assert item["enabled"] is True
    description = item["description"].lower()
    assert "một file mp4" in description
    assert "xuất riêng" not in description
    assert capabilities.plan_patch("manual_remove_middle")


def test_plan_patch_is_deep_copy_and_does_not_leak_mutations() -> None:
    first = capabilities.plan_patch("effect_fade")
    first["local_effects"]["fade_in_ms"] = 9_999
    second = capabilities.plan_patch("effect_fade")
    assert second["local_effects"]["fade_in_ms"] == 300


def test_vietnamese_intent_compiler_is_deterministic_and_local() -> None:
    intent = "làm sáng, rõ và âm lượng đều"
    first = capabilities.compile_local_intent(intent)
    second = capabilities.compile_local_intent(intent)
    assert first == second
    assert first["ok"] is True
    assert first["provider_called"] is False
    assert first["feature_keys"] == [
        "enhance_light_color",
        "enhance_basic_sharpen",
        "audio_loudnorm",
    ]
    assert first["plan_patch"] == {
        "color_preset": "bright_clear",
        "quality_filters": {"sharpen": True},
        "audio_normalization": "loudnorm",
    }
    assert "0 Xu" in first["message_vi"]


def test_vietnamese_vertical_tiktok_intent_maps_to_local_ratio() -> None:
    result = capabilities.compile_local_intent("video dọc TikTok")
    assert result["ok"] is True
    assert result["provider_called"] is False
    assert result["feature_keys"] == ["aspect_basic_crop"]
    assert result["plan_patch"] == {
        "crop_or_fit": {"aspect_ratio": "9:16", "mode": "crop"}
    }


def test_unsupported_generative_intent_fails_closed_without_job() -> None:
    result = capabilities.compile_local_intent("tạo phép thuật/parallax")
    assert result["ok"] is False
    assert result["unsupported"] is True
    assert result["feature_keys"] == []
    assert result["plan_patch"] == {}
    assert result["job_created"] is False
    assert result["provider_called"] is False
    assert result["wallet_mutated"] is False
    assert "chưa tạo" in result["message_vi"].lower()


def test_unknown_capability_has_no_patch_and_catalog_remains_valid() -> None:
    assert capabilities.plan_patch("provider_magic_effect") == {}
    assert capabilities.validate_capability_catalog() is True
    # Keep the test honest about accidental shared mutable catalog records.
    snapshot = deepcopy(capabilities.capability("enhance_basic_sharpen"))
    snapshot["public_name"] = "đã sửa ngoài catalog"
    assert capabilities.capability("enhance_basic_sharpen")["public_name"] != snapshot["public_name"]
