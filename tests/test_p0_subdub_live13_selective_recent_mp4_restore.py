import inspect

import bot


def test_new_dub_jobs_use_direct_known_good_synthesizers():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "synthesize_dub_segment_chunks(*args" not in source
    assert source.count("synthesize_canonical_dub_segment_chunks(") == 1
    assert "build_dub_timeline_audio(chunks" not in source
    assert source.count("build_canonical_dub_timeline_audio(chunks, total_duration)") == 1
    assert "checkpoint_dir=" not in source
    assert "tts_resume_context" not in source


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
