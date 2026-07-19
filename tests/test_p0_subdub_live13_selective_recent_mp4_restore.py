import inspect

import bot


def test_new_dub_jobs_use_direct_known_good_synthesizers():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "result = await synthesize_dub_segment_chunks(*args" in source
    assert "prepare_subdub_combo_tts_segments(" in source
    assert source.count("synthesize_dub_segment_chunks(") == 2
    assert "synthesize_canonical_dub_segment_chunks(" not in source
    assert "build_canonical_dub_timeline_audio(chunks, total_duration)" in source
    assert "standalone_dub_synth_with_canonical_timeline" in source
    assert "checkpoint_dir=" not in source
    assert "tts_resume_context" not in source


def test_combo_direct_synth_uses_translated_text_and_preserves_cue_windows():
    canonical, tts_segments = bot.prepare_subdub_combo_tts_segments(
        [
            {
                "index": 1,
                "start": 1.25,
                "end": 2.75,
                "source_text": "Original one",
                "translated_text": "Cau dich mot",
            },
            {
                "index": 2,
                "start": 3.0,
                "end": 4.5,
                "source_text": "Original two",
                "translated_text": "Cau dich hai",
            },
        ],
        source_language="en",
        target_language="vi",
    )

    assert [item["text"] for item in tts_segments] == ["Cau dich mot", "Cau dich hai"]
    assert [(item["start"], item["end"]) for item in tts_segments] == [(1.25, 2.75), (3.0, 4.5)]
    assert [item["source_start_ms"] for item in canonical] == [1250, 3000]
    assert [item["source_end_ms"] for item in canonical] == [2750, 4500]
    assert [item["translated_text"] for item in canonical] == ["Cau dich mot", "Cau dich hai"]


def test_restart_recovery_keeps_checkpoint_resume_path():
    source = inspect.getsource(bot.subdub_resume_generating_voice_from_checkpoint)

    assert "synthesize_canonical_dub_segment_chunks(" in source
    assert "checkpoint_dir=" in source
    assert "checkpoint_entries=" in source


def test_changing_translation_language_clears_only_derived_outputs(monkeypatch):
    user_id = 991301
    bot.clear_video_dubbing_pending(user_id)
    try:
        source_state = bot.set_video_dubbing_pending(
            user_id,
            "language",
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            source_file_id="source-video",
            source_file_name="input.mp4",
            source_mime_type="video/mp4",
            media_kind="video",
            subtitle_ref="source-subtitle",
            source_subtitle_ref="source-subtitle",
            translated_subtitle_ref="old-translation",
            final_translation_asset_ids="old-translation-assets",
            final_subtitle_asset_ids="old-subtitle-assets",
            final_video_available="1",
            task2_job_id="old-job",
            target_language="Tiếng Việt",
        )
        monkeypatch.setattr(bot, "video_dubbing_uploaded_translate_locked", lambda *_args, **_kwargs: False)

        routed, _text, _markup, status = bot.video_dubbing_uploaded_translate_language_route(
            user_id,
            source_state,
            "English",
            "vi",
        )

        assert status == "confirm"
        assert routed["target_language"] == "English"
        assert routed["source_file_id"] == "source-video"
        assert routed["subtitle_ref"] == "source-subtitle"
        assert routed["source_subtitle_ref"] == "source-subtitle"
        assert routed["translated_subtitle_ref"] == ""
        assert routed["final_translation_asset_ids"] == ""
        assert routed["final_subtitle_asset_ids"] == ""
        assert routed["final_video_available"] == ""
        assert routed["task2_job_id"] == ""
    finally:
        bot.clear_video_dubbing_pending(user_id)
