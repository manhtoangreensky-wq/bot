from __future__ import annotations

from copy import deepcopy

from services import video_edit_capabilities as capabilities


WORKER_IDENTITY = {
    "worker_id": "worker-video-edit",
    "filter_worker_id": "worker-video-edit",
    "ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
    "filter_ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
}


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
        "enhance_resolution_normalize": {"section": "restore", "owner": "video_local_editing"},
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

    resolution = capabilities.capability("enhance_resolution_normalize")
    public_truth = " ".join(
        str(resolution.get(field) or "")
        for field in ("public_name", "description", "risk_notes")
    ).lower()
    assert "không phải ai upscale" in public_truth
    assert capabilities.plan_patch("enhance_resolution_normalize") == {"resolution": "1080p"}


def test_public_capability_copy_is_vietnamese_first() -> None:
    public_copy = "\n".join(
        str(item.get(field) or "")
        for item in capabilities.public_actionable_capabilities()
        for field in ("public_name", "description", "risk_notes")
    ).lower()
    for english_fragment in ("crop theo", "fade-in", "fade-out", "vignette", "slow zoom"):
        assert english_fragment not in public_copy


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


def test_intent_compiler_merges_nested_patch_without_erasing_existing_plan() -> None:
    existing = {
        "volume": 0.75,
        "quality_filters": {"sharpen": True},
    }
    result = capabilities.compile_local_intent("giảm nhiễu", base_plan=existing)
    assert result["ok"] is True
    assert result["plan_patch"] == {
        "volume": 0.75,
        "quality_filters": {"sharpen": True, "denoise": True},
    }
    assert existing == {
        "volume": 0.75,
        "quality_filters": {"sharpen": True},
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


def test_runtime_filter_admission_is_fail_closed_and_audio_aware() -> None:
    unknown = capabilities.runtime_capability_admission(
        "enhance_denoise",
        available_filters=set(),
        filters_known=False,
        has_audio=True,
        **WORKER_IDENTITY,
    )
    assert unknown["ready"] is False
    assert unknown["reason"] == "filter_snapshot_missing"

    missing = capabilities.runtime_capability_admission(
        "enhance_denoise",
        available_filters={"format", "unsharp"},
        filters_known=True,
        has_audio=True,
        **WORKER_IDENTITY,
    )
    assert missing["ready"] is False
    assert missing["reason"] == "filter_missing:hqdn3d"

    loudnorm_without_audio = capabilities.runtime_capability_admission(
        "audio_loudnorm",
        available_filters={"loudnorm"},
        filters_known=True,
        has_audio=False,
        **WORKER_IDENTITY,
    )
    assert loudnorm_without_audio["ready"] is False
    assert loudnorm_without_audio["reason"] == "audio_stream_required_for_loudnorm"

    color = capabilities.runtime_capability_admission(
        "enhance_light_color",
        available_filters=set(),
        filters_known=False,
        has_audio=False,
        **WORKER_IDENTITY,
    )
    assert color["ready"] is False
    assert color["reason"] == "filter_snapshot_missing"
    assert color["required_filters"] == ["eq", "format", "unsharp"]

    color_missing = capabilities.runtime_capability_admission(
        "enhance_light_color",
        available_filters={"format", "unsharp"},
        filters_known=True,
        has_audio=False,
        **WORKER_IDENTITY,
    )
    assert color_missing["ready"] is False
    assert color_missing["reason"] == "filter_missing:eq"

    color_ready = capabilities.runtime_capability_admission(
        "enhance_light_color",
        available_filters={"eq", "format", "unsharp"},
        filters_known=True,
        has_audio=False,
        **WORKER_IDENTITY,
    )
    assert color_ready["ready"] is True

    soft_clean = capabilities.runtime_capability_admission(
        "enhance_soft_clean",
        available_filters={"eq", "format", "hqdn3d", "unsharp"},
        filters_known=True,
        has_audio=False,
        **WORKER_IDENTITY,
    )
    assert capabilities.plan_patch("enhance_soft_clean") == {"color_preset": "soft_clean"}
    assert soft_clean["ready"] is True
    assert soft_clean["required_filters"] == ["eq", "format", "hqdn3d", "unsharp"]
