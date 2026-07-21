import asyncio
import inspect

import bot


def test_new_dub_jobs_use_restored_pr400_shared_pipeline():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subdub_blackboxes.run_subdub_lane_blackbox(" in source
    assert "runner=subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "prepare_subtitles=_prepare_subtitles_for_blackbox" in source
    assert "synthesize_segments=_synthesize_dub_segments_for_blackbox" in source
    assert "render_video=_render_video_for_blackbox" in source
    assert "synthesize_canonical_dub_segment_chunks(" not in source


def test_combo_audio_policy_uses_translated_text_and_preserves_cue_windows():
    prepared = {
        "source_segments": [
            {"index": 1, "start": 1.25, "end": 2.75, "text": "Original one"},
            {"index": 2, "start": 3.0, "end": 4.5, "text": "Original two"},
        ],
        "output_segments": [
            {"index": 1, "start": 1.25, "end": 2.75, "text": "Cau dich mot"},
            {"index": 2, "start": 3.0, "end": 4.5, "text": "Cau dich hai"},
        ],
    }
    policy = bot.subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        {"target_language": "vi", "translate_requested": True},
        prepared,
    )

    assert policy["dub_text_source"] == "translated"
    assert policy["tts_tracks_count"] == 1
    assert policy["source_tts_rendered"] is False
    assert policy["target_tts_rendered"] is True
    assert [item["text"] for item in policy["tts_segments"]] == ["Cau dich mot", "Cau dich hai"]
    assert [(item["start"], item["end"]) for item in policy["tts_segments"]] == [
        (1.25, 2.75),
        (3.0, 4.5),
    ]


def test_restart_recovery_terminalizes_when_pr400_has_no_resume_executor(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_hydrate_registry_from_persisted",
        lambda job: dict(job or {}),
    )
    monkeypatch.setattr(
        bot,
        "subdub_recovery_tts_checkpoint",
        lambda _job: {"available": True, "valid": [{"artifact_path": "cue-1.wav"}], "total": 2, "completed": 1},
    )
    monkeypatch.setattr(
        bot,
        "subdub_atomic_mutate_persisted_job",
        lambda job, *, reason, mutate: mutate(dict(job or {})),
    )

    recovered = asyncio.run(
        bot.subdub_recover_persisted_job(
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
                "current_stage": "generating_voice",
                "status_registry_missing_after_restart": True,
                "terminal_state": "running",
            },
            object(),
        )
    )

    assert recovered["terminal_state"] == "failed_no_charge"
    assert recovered["charged_xu"] == 0
    assert recovered["recovery_result"] == "tts_resume_not_available_in_restored_runtime"
    assert recovered["blocker"] == "recovery_resume_not_supported_on_pr400_runtime:generating_voice"


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
