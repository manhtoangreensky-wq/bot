import asyncio
from pathlib import Path

from services import subdub_combo_blackbox
from services import subtitle_dub_product_pipeline as pipeline


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def _segments(label: str) -> list[dict]:
    return [{"index": 1, "start": 0.0, "end": 1.0, "text": label}]


def test_combo_normalization_forces_translated_subtitle_video_contract():
    state = subdub_combo_blackbox.normalize_combo_state(
        {
            "mode": pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "translate_requested": "0",
            "dub_text_source": "source",
            "output_type": "video",
            "combo_subpath": "direct_dub",
        }
    )

    assert state["translate_requested"] == "1"
    assert state["dub_text_source"] == "translated"
    assert state["output_type"] == "video_subtitle"
    assert state["output_format"] == "video_subtitle"
    assert state["combo_subpath"] == "create_then_dub"
    assert state["dub_source"] == "translated_subtitle"


def test_dub_only_policy_never_uses_translated_segments_from_stale_state():
    source = _segments("source speech")
    translated = _segments("translated speech")
    policy = pipeline.resolve_subdub_dub_audio_policy(
        {
            "mode": pipeline.VIDEO_SUBTITLE_MODE_DUB,
            "translate_requested": "1",
            "target_language": "English",
            "dub_text_source": "translated",
            "dubbed_voice_volume_percent": 0,
        },
        {"source_segments": source, "output_segments": translated},
    )

    assert policy["dub_text_source"] == "source"
    assert policy["tts_segments"] == source
    assert policy["source_tts_rendered"] is True
    assert policy["target_tts_rendered"] is False
    assert policy["dubbed_voice_volume_percent"] == 0


def test_combo_policy_uses_translation_and_fails_closed_when_it_is_missing():
    source = _segments("source speech")
    translated = _segments("translated speech")
    state = {
        "mode": pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "translate_requested": "0",
        "target_language": "original",
        "dub_text_source": "source",
    }

    translated_policy = pipeline.resolve_subdub_dub_audio_policy(
        state,
        {"source_segments": source, "output_segments": translated},
    )
    missing_policy = pipeline.resolve_subdub_dub_audio_policy(
        state,
        {"source_segments": source, "output_segments": []},
    )

    assert translated_policy["dub_text_source"] == "translated"
    assert translated_policy["tts_segments"] == translated
    assert translated_policy["target_tts_rendered"] is True
    assert missing_policy["dub_text_source"] == "translated"
    assert missing_policy["tts_segments"] == []


def test_combo_core_forwards_translated_subtitle_and_audio_mix_to_renderer():
    rendered = []

    async def prepare(state):
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "source_segments": _segments("source speech"),
            "output_segments": _segments("translated speech"),
            "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\ntranslated speech\n",
            "output_script": "translated speech",
            "translation_provider": "fixture",
        }

    async def synthesize(segments, **_kwargs):
        assert segments == _segments("translated speech")
        return {
            "provider": "fixture-tts",
            "chunks": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "audio_duration": 1.0,
                    "audio_bytes": b"speech",
                }
            ],
        }

    async def render(source_bytes, **kwargs):
        rendered.append((source_bytes, dict(kwargs)))
        return b"mp4", "rendered"

    for dubbed_volume in (0, 150):
        result = asyncio.run(
            pipeline.process_subtitle_dub_job(
                mode=pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                state={
                    "mode": pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                    "target_language": "English",
                    "translate_requested": "1",
                    "dub_text_source": "translated",
                    "output_type": "video_subtitle",
                    "video_duration": 1,
                    "keep_original_audio": "1",
                    "original_audio_volume_percent": 30,
                    "dubbed_voice_volume_percent": dubbed_volume,
                },
                user_id=1,
                prepare_subtitles=prepare,
                srt_from_text=lambda text, _duration: text,
                segments_from_text=lambda text, _duration: _segments(text),
                segments_from_subtitle=lambda _text: _segments("translated speech"),
                subtitle_output_items=lambda *_args: [],
                resolve_voice_id=lambda *_args: "fixture-voice",
                parse_voice_speed=lambda _value: 1.0,
                synthesize_segments=synthesize,
                build_timeline_audio=lambda *_args: (b"audio", "timeline"),
                normalize_audio=lambda audio: (audio, "normalized"),
                validate_audio=lambda _audio: {"ok": True, "duration": 1.0},
                render_video=render,
                video_render_ready=lambda _output: True,
                ffmpeg_ready=lambda: True,
                dub_mux_enabled=True,
            )
        )

        assert result["ok"] is True

    assert [item[0] for item in rendered] == [b"video", b"video"]
    assert all(item[1]["subtitle_bytes"].startswith(b"1\n00:00:00,000") for item in rendered)
    assert all(item[1]["keep_original_audio"] is True for item in rendered)
    assert all(item[1]["original_audio_volume_percent"] == 30 for item in rendered)
    assert [item[1]["dubbed_voice_volume_percent"] for item in rendered] == [0, 150]


def test_pipeline_core_normalizes_legacy_combo_before_mode_resolution():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    start = source.index("async def _execute_video_dubbing_pipeline_core(")
    end = source.index("\nasync def ", start + 1)
    block = source[start:end]
    marker = "state = subdub_combo_blackbox.normalize_combo_state(state)"

    assert marker in block
    assert block.index(marker) < block.index("confirmed_product =")
