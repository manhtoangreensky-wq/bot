"""Customer-facing SubDub information must match the live product contract."""

from __future__ import annotations

import hashlib
import json

import bot
import pytest
from services import subdub_speaker_cast
from services.pricing_guide_content import (
    PUBLIC_COPY_LOCALES,
    public_subdub_auto_pricing_line,
    public_subdub_deep_copy,
)


def _button_map(markup) -> dict[str, str]:
    return {
        str(button.callback_data or ""): str(button.text or "")
        for row in markup.inline_keyboard
        for button in row
    }


def test_subdub_menu_names_every_live_lane_and_current_output_contract():
    text = bot.video_dubbing_menu_text("vi", "translation")

    for expected in (
        "Tạo phụ đề tự động",
        "Dịch phụ đề video",
        "Lồng tiếng video",
        "Phụ đề + Lồng tiếng",
        "MP4",
        "SRT",
        "2 người nói",
        "3–8 người nói",
    ):
        assert expected in text
    assert "tối đa 16" not in text


def test_subdub_voice_picker_names_each_current_voice_service(monkeypatch):
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda: True)

    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        buttons = _button_map(
            bot.video_dubbing_voice_keyboard(
                locale,
                {
                    "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
                    "target_language": "English",
                },
            )
        )

        assert buttons["videodub|voice|default_female"] == copy["voice_default_female"]
        assert buttons["videodub|voice|default_male"] == copy["voice_default_male"]
        assert buttons["videodub|voice|auto_speaker_gender"] == copy["voice_auto_speaker"]
        assert buttons["videodub|voice|auto_multi_speaker"] == copy["voice_auto_multi_speaker"]
        assert buttons["videodub|voice_create"] == copy["voice_custom_create"]
        assert len(set(buttons.values())) == len(buttons.values())


def test_all_locales_describe_exact_two_and_three_to_eight_auto_lanes():
    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        current_copy = " ".join(
            (
                copy["menu_body"],
                copy["voice_auto_speaker"],
                copy["voice_auto_multi_speaker"],
                copy["voice_auto_explanation"],
            )
        )

        assert all(marker in current_copy for marker in ("2", "3", "8"))
        assert "16" not in current_copy
        assert copy["output_mp4_srt"]


def test_subdub_pricing_names_auto_two_and_auto_multi_separately():
    for locale in sorted(PUBLIC_COPY_LOCALES):
        copy = public_subdub_deep_copy(locale)
        text = bot.video_dubbing_pricing_text(locale)

        assert copy["voice_auto_speaker"] in text
        assert copy["voice_auto_multi_speaker"] in text
        assert text.count(copy["voice_auto_price_rule"]) == 2
        assert "16" not in text
        guide_line = public_subdub_auto_pricing_line(locale)
        assert copy["voice_auto_speaker"] in guide_line
        assert copy["voice_auto_multi_speaker"] in guide_line


def test_subdub_confirmation_distinguishes_primary_mp4_and_optional_srt():
    states = {
        bot.VIDEO_SUBTITLE_MODE_CREATE: {},
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE: {"target_language": "English"},
        bot.VIDEO_SUBTITLE_MODE_DUB: {
            "target_language": "English",
            "voice_style": "Giọng nữ mặc định",
        },
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: {
            "target_language": "English",
            "voice_style": "Giọng nữ mặc định",
        },
    }
    copy = public_subdub_deep_copy("vi")

    for mode, fields in states.items():
        text = bot.video_dubbing_confirm_text(
            {"mode": mode, "source_file_id": "fixture", **fields},
            "vi",
        )
        assert "MP4" in text
        if mode == bot.VIDEO_SUBTITLE_MODE_DUB:
            assert copy["output_mp4_srt"] not in text
        else:
            assert copy["output_mp4_srt"] in text


def test_subdub_exact_price_screen_names_auto_two_or_auto_multi():
    copy = public_subdub_deep_copy("vi")
    base = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_exact_receipt": {
            "actual_billable_words": 100,
            "actual_auto_xu": 50,
            "actual_subtitle_xu": 0,
            "actual_total_xu": 50,
        },
    }

    auto_two = bot.subdub_auto_exact_confirmation_text(base, "vi")
    auto_multi = bot.subdub_auto_exact_confirmation_text(
        {**base, "auto_speaker_lane": "multi"},
        "vi",
    )

    assert copy["voice_auto_speaker"] in auto_two
    assert copy["voice_auto_multi_speaker"] in auto_multi
    assert copy["voice_auto_multi_speaker"] not in auto_two


def test_subdub_catalog_is_identical_for_admin_and_customer():
    customer_text, customer_markup = bot.localized_menu_content(
        "translation_video_factory",
        False,
        "vi",
    )
    admin_text, admin_markup = bot.localized_menu_content(
        "translation_video_factory",
        True,
        "vi",
    )

    assert admin_text == customer_text
    assert _button_map(admin_markup) == _button_map(customer_markup)


def test_customer_exact_resume_restores_one_ms_srt_quantization_from_sidecar():
    sidecar = {
        "cues": [
            {
                "cue_id": "cue-0002-live",
                "start_ms": 14_475,
                "end_ms": 16_255,
            }
        ]
    }
    cached = [{"start": 14.475, "end": 16.254, "text": "cached"}]

    restored = bot.subdub_restore_auto_exact_cached_timing(sidecar, cached)

    assert restored == [
        {
            "start": 14.475,
            "end": 16.255,
            "start_ms": 14_475,
            "end_ms": 16_255,
            "source_start_ms": 14_475,
            "source_end_ms": 16_255,
            "text": "cached",
        }
    ]


def test_customer_exact_resume_rejects_more_than_one_ms_timing_change():
    sidecar = {
        "cues": [
            {
                "cue_id": "cue-0002-live",
                "start_ms": 14_475,
                "end_ms": 16_257,
            }
        ]
    }
    cached = [{"start": 14.475, "end": 16.254, "text": "cached"}]

    with pytest.raises(subdub_speaker_cast.AutoCastUnavailable):
        bot.subdub_restore_auto_exact_cached_timing(sidecar, cached)


def test_customer_exact_resume_loader_uses_signed_timing_with_one_ms_drift(
    monkeypatch,
    tmp_path,
):
    source_media = b"normalized-customer-media"
    source_srt = "1\n00:00:14,475 --> 00:00:16,254\ncached\n"
    media_path = tmp_path / "normalized_source.mp4"
    source_path = tmp_path / "auto_exact_source.srt"
    metadata_path = tmp_path / "auto_exact_cache.json"
    media_path.write_bytes(source_media)
    source_path.write_text(source_srt, encoding="utf-8")
    sidecar = subdub_speaker_cast.build_sidecar(
        [
            {
                "cue_id": "cue-0001-signed",
                "start": 14.475,
                "end": 16.255,
                "source_start_ms": 14_475,
                "source_end_ms": 16_255,
                "text": "cached",
                "speaker": 0,
                "chunk_index": 0,
                "speaker_id": "chunk_00:speaker_0",
                "speaker_confidence": 0.99,
            }
        ],
        media_sha256=hashlib.sha256(source_media).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(source_srt),
    )
    sidecar_receipt = subdub_speaker_cast.persist_sidecar(
        sidecar,
        workspace=str(tmp_path),
    )
    stored_cache = {
        "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
        "source_file": source_path.name,
        "translated_file": "",
        "source_media_file": media_path.name,
        "source_subtitle_sha256": bot._subdub_auto_text_sha256(source_srt),
        "translated_subtitle_sha256": "",
        "dub_text_source": "source",
        "target_language": "original",
    }
    metadata_path.write_text(
        json.dumps(stored_cache, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    cache = {**stored_cache, "metadata_file": metadata_path.name}
    receipt = {
        "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
        "media_sha256": hashlib.sha256(source_media).hexdigest(),
    }
    state = {
        "_pipeline_workspace": str(tmp_path),
        "speaker_sidecar_path": sidecar_receipt["path"],
        "speaker_sidecar_sha256": sidecar_receipt["sha256"],
        "source_mime_type": "video/mp4",
        "target_language": "original",
    }
    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )

    prepared = bot._subdub_auto_load_cached_prepared(
        {
            "workspace": str(tmp_path),
            "auto_exact_cache": cache,
            "auto_exact_receipt": receipt,
        },
        state,
    )

    assert prepared["asr_provider"] == "cached_auto_exact_receipt"
    assert prepared["translation_provider"] == ""
    assert prepared["source_segments"][0]["cue_id"] == "cue-0001-signed"
    assert prepared["source_segments"][0]["end"] == 16.255
