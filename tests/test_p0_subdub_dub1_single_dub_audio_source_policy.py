import asyncio

from services import subtitle_dub_product_pipeline as pipeline


SOURCE = [
    {"index": 1, "start": 0.0, "end": 1.5, "text": "Xin chao"},
    {"index": 2, "start": 1.5, "end": 3.0, "text": "Tam biet"},
]
TRANSLATED = [
    {"index": 1, "start": 0.0, "end": 1.5, "text": "Hello"},
    {"index": 2, "start": 1.5, "end": 3.0, "text": "Goodbye"},
]


def _policy(state):
    return pipeline.resolve_subdub_dub_audio_policy(
        state,
        {"source_segments": SOURCE, "output_segments": TRANSLATED},
    )


def test_target_languages_use_translated_text_only():
    for language in ("English", "Japanese", "Korean"):
        policy = _policy({"target_language": language, "translate_requested": "1"})
        assert [item["text"] for item in policy["tts_segments"]] == ["Hello", "Goodbye"]
        assert policy["dub_text_source"] == "translated"
        assert policy["source_tts_rendered"] is False
        assert policy["target_tts_rendered"] is True
        assert policy["tts_tracks_count"] == 1


def test_original_source_selection_uses_source_text_only():
    for token in ("source", "original", "nguyên bản"):
        policy = _policy({"dub_text_source": token, "target_language": "English", "translate_requested": "1"})
        assert policy["dub_text_source"] == "source"
        assert policy["tts_segments"] == SOURCE
        assert policy["source_tts_rendered"] is True
        assert policy["target_tts_rendered"] is False


def test_original_video_audio_is_explicit_only():
    muted = _policy({"target_language": "English", "translate_requested": "1"})
    kept = _policy({"target_language": "English", "translate_requested": "1", "keep_original_audio": "1"})
    assert muted["keep_original_audio"] is False
    assert muted["original_audio_policy"] == "muted"
    assert kept["keep_original_audio"] is True
    assert kept["original_audio_policy"] == "kept_low_volume"
    assert kept["tts_tracks_count"] == 1


def test_missing_translation_never_adds_source_tts_track():
    policy = pipeline.resolve_subdub_dub_audio_policy(
        {"target_language": "English", "translate_requested": "1"},
        {
            "source_segments": SOURCE,
            "output_segments": [TRANSLATED[0], {**SOURCE[1], "translate_missing": True}],
        },
    )
    assert [item["text"] for item in policy["tts_segments"]] == ["Hello"]
    assert policy["tts_tracks_count"] == 1
    assert policy["source_tts_rendered"] is False
    assert policy["target_tts_rendered"] is True


def test_pipeline_synthesizes_once_and_passes_original_audio_choice():
    calls = {"tts": [], "render": []}

    async def prepare(state):
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "source_segments": list(SOURCE),
            "output_segments": list(TRANSLATED),
            "output_script": "Hello Goodbye",
            "output_subtitle": "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n2\n00:00:01,500 --> 00:00:03,000\nGoodbye\n",
            "translation_provider": "fixture",
        }

    async def synthesize(segments, **_kwargs):
        calls["tts"].append(list(segments))
        return {
            "provider": "fixture",
            "chunks": [
                {**segment, "audio_bytes": f"tts-{index}".encode(), "audio_duration": 1.0}
                for index, segment in enumerate(segments, start=1)
            ],
        }

    async def render(_source, **kwargs):
        calls["render"].append(dict(kwargs))
        return b"mp4", "fixture"

    result = asyncio.run(
        pipeline.process_subtitle_dub_job(
            mode=pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            state={
                "output_type": "video_subtitle",
                "video_duration": "3",
                "target_language": "English",
                "translate_requested": "1",
                "keep_original_audio": "1",
            },
            user_id=1,
            prepare_subtitles=prepare,
            srt_from_text=lambda text, _duration: text,
            segments_from_text=lambda _text, _duration: [],
            segments_from_subtitle=lambda _text: [],
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "voice-fixture",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=lambda *_args: (b"timeline", "fixture"),
            normalize_audio=lambda audio: (audio, "fixture"),
            render_video=render,
            video_render_ready=lambda _output: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert len(calls["tts"]) == 1
    assert calls["tts"][0] == TRANSLATED
    assert calls["render"][0]["keep_original_audio"] is True
    assert result["dub_text_source"] == "translated"
    assert result["tts_tracks_count"] == 1
    assert result["source_tts_rendered"] is False
    assert result["target_tts_rendered"] is True
