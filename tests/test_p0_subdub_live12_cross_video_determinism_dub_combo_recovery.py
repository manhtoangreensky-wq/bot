import asyncio
import inspect

import pytest

import bot
from services import subdub_canonical_cues as canonical


def _source_cues():
    return canonical.canonicalize_segments(
        [
            {"index": 1, "start": 0.0, "end": 1.2, "text": "Xin chao"},
            {"index": 2, "start": 1.4, "end": 2.8, "text": "Hen gap lai"},
        ],
        extraction_source="subtitle_stream",
        source_language="vi",
    )


def test_live12_new_upload_clears_every_previous_video_derived_reference():
    fields = bot.video_dubbing_source_fields_from_upload(
        {
            "file_id": "telegram-new-file",
            "file_unique_id": "telegram-new-unique",
            "file_name": "new.mp4",
            "mime_type": "video/mp4",
            "media_kind": "video",
            "duration": 29,
            "file_size": 123456,
        }
    )

    for key in (
        "subtitle_ref",
        "source_subtitle_ref",
        "translated_subtitle_ref",
        "translation_session_id",
        "final_translation_asset_ids",
        "final_subtitle_asset_ids",
        "final_dub_asset_id",
        "final_dub_video_asset_id",
        "final_video_available",
        "task2_job_id",
    ):
        assert fields[key] == "", f"new media can reuse stale cross-video field: {key}"
    assert fields["input_content_hash"]
    assert fields["subdub_pipeline_version"] == "live12-v1"


def test_live12_canonical_identity_is_deterministic_and_video_specific():
    base = {
        "input_content_hash": "video-a-hash",
        "mode": "dub",
        "source_language": "zh",
        "target_language": "vi",
        "voice_id": "female-vi",
        "voice_speed": "1.0",
        "subdub_pipeline_version": "live12-v1",
    }
    first = canonical.canonical_input_identity(**base)
    second = canonical.canonical_input_identity(**base)
    changed_video = canonical.canonical_input_identity(**{**base, "input_content_hash": "video-b-hash"})
    changed_language = canonical.canonical_input_identity(**{**base, "target_language": "en"})

    assert first == second
    assert first != changed_video
    assert first != changed_language


@pytest.mark.parametrize(
    ("text", "target_language"),
    [
        ("Chung ta se gap lai vao ngay mai.", "Tiếng Việt"),
        ("We will meet again tomorrow.", "English"),
        ("TO BE OR NOT TO BE", "English"),
        ("また明日会いましょう。", "日本語"),
        ("また明日会いましょう。", "Tiếng Nhật"),
        ("明天再见。", "中文"),
        ("明天再见。", "Tiếng Trung"),
        ("내일 다시 만나요.", "한국어"),
        ("내일 다시 만나요.", "Tiếng Hàn"),
    ],
)
def test_live12_translation_integrity_accepts_valid_target_scripts(text, target_language):
    result = canonical.validate_translation_text(text, target_language=target_language)
    assert result["accepted"] is True


@pytest.mark.parametrize(
    ("text", "target_language", "reason"),
    [
        ("Xin chao \ufffd ban", "Tiếng Việt", "translation_replacement_character"),
        ("6041055,116089 511123628195284580", "Tiếng Việt", "translation_numeric_garbage"),
        ("SIX TF th KA SF it IE trong x", "Tiếng Việt", "translation_fragmented_garbage"),
        ("这是中文，不是越南语。", "Tiếng Việt", "translation_wrong_script_for_target_language"),
    ],
)
def test_live12_translation_integrity_rejects_live_garbage(text, target_language, reason):
    result = canonical.validate_translation_text(text, target_language=target_language)
    assert result["accepted"] is False
    assert result["reason"] == reason


def test_live12_strict_translation_keeps_cue_timeline_and_rejects_bad_cue():
    source = _source_cues()
    translated = canonical.apply_translations(
        source,
        [
            {"cue_id": source[0]["cue_id"], "translated_text": "Hello"},
            {"cue_id": source[1]["cue_id"], "translated_text": "See you again"},
        ],
        target_language="English",
        reject_invalid=True,
    )
    assert canonical.timeline_signature(translated) == canonical.timeline_signature(source)

    with pytest.raises(ValueError, match=rf"translation_text_invalid:{source[1]['cue_id']}:translation_numeric_garbage"):
        canonical.apply_translations(
            source,
            [
                {"cue_id": source[0]["cue_id"], "translated_text": "Hello"},
                {"cue_id": source[1]["cue_id"], "translated_text": "195 28 45 80 131775 5111246"},
            ],
            target_language="English",
            reject_invalid=True,
        )


def test_live12_invalid_translation_does_not_retry_or_retime(monkeypatch):
    calls = []

    async def fake_translate(text, target_language, **_kwargs):
        calls.append((text, target_language))
        return {"text": "SIX TF th KA SF it IE trong x", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    with pytest.raises(RuntimeError, match="translation_text_invalid"):
        asyncio.run(bot.translate_canonical_subtitle_segments(_source_cues()[:1], "Tiếng Việt"))
    assert len(calls) == 1


def test_live12_dub_and_combo_share_canonical_sequential_tts_contract():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "synthesize_dub_segment_chunks(*args" not in source
    assert "build_dub_timeline_audio(chunks" not in source
    assert source.count("synthesize_canonical_dub_segment_chunks(") == 1
    assert source.count("build_canonical_dub_timeline_audio(chunks, total_duration)") == 1
    assert "checkpoint_dir=" not in source
    assert "tts_resume_context" not in source


def test_live12_tts_scheduler_never_overlaps_and_has_exact_blocker():
    plan = bot.subdub_plan_canonical_tts_timeline(
        [
            {"cue_id": "one", "start": 0.0, "end": 1.0, "audio_duration": 1.0},
            {"cue_id": "two", "start": 0.5, "end": 2.0, "audio_duration": 1.0},
        ],
        2.2,
    )
    assert plan["ok"] is True
    assert plan["overlap_count"] == 0
    assert plan["scheduled"][1]["scheduled_start"] >= plan["scheduled"][0]["scheduled_end"]
    assert plan["tempo_ratio"] <= 1.15

    blocked = bot.subdub_plan_canonical_tts_timeline(
        [{"cue_id": "too-long", "start": 0.0, "end": 1.0, "audio_duration": 5.0}],
        1.0,
    )
    assert blocked["ok"] is False
    assert blocked["blocker"].startswith("tts_cue_cannot_fit_without_overlap:")


def test_live12_recovery_marks_tts_complete_before_mux():
    source = inspect.getsource(bot.subdub_resume_generating_voice_from_checkpoint)
    complete = source.index("tts_complete=True")
    mux = source.index("mux_started=True")
    assert complete < mux
