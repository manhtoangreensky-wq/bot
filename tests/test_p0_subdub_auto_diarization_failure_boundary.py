import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services import subdub_speaker_cast
from services.subdub_blackboxes import auto_speaker


def _load_resolver_from_production_source():
    source = Path("bot.py").read_text(encoding="utf-8")
    start = source.index("async def video_dubbing_resolve_source_script(")
    end = source.index("\nasync def video_dubbing_render_video(", start)
    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "subdub_speaker_cast": subdub_speaker_cast,
        "AUTO_CAST_UNAVAILABLE": subdub_speaker_cast.AUTO_CAST_UNAVAILABLE,
    }
    exec(compile(source[start:end], "bot.py", "exec"), namespace)
    return namespace["video_dubbing_resolve_source_script"], namespace


def _load_video_dubbing_prepare_subtitles_from_production_source():
    source = Path("bot.py").read_text(encoding="utf-8")
    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "hashlib": __import__("hashlib"),
        "inspect": __import__("inspect"),
        "os": __import__("os"),
    }
    sync_start = source.index("def video_dubbing_sync_state_fields(")
    sync_end = source.index("\ndef subdub_telegram_file_too_big", sync_start)
    prepare_start = source.index("async def video_dubbing_prepare_subtitles(")
    prepare_end = source.index("\ndef subdub_auto_validated_voice_pools", prepare_start)
    exec(compile(source[sync_start:sync_end], "bot.py", "exec"), namespace)
    exec(compile(source[prepare_start:prepare_end], "bot.py", "exec"), namespace)
    return namespace["video_dubbing_prepare_subtitles"], namespace


class AutoDiarizationFailureBoundaryTests(unittest.TestCase):
    def test_smart_multi_preserves_pipeline_workspace_across_subtitle_pending_sync(self):
        prepare, namespace = _load_video_dubbing_prepare_subtitles_from_production_source()
        captured = {}

        class ExtractionReached(Exception):
            pass

        async def resolve_source(*_args, **_kwargs):
            return {
                "source_kind": "asr",
                "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "hello", "speaker": None}
                ],
                "word_timeline": [{"word": "hello", "start": 0.0, "end": 1.0}],
                "duration_seconds": 1.0,
            }

        async def extract_pcm(prepared, state, **_kwargs):
            captured["prepared_workspace"] = prepared["state"].get("_pipeline_workspace")
            captured["state_workspace"] = state.get("_pipeline_workspace")
            raise ExtractionReached

        pending = {}

        def set_pending(_user_id, step, **fields):
            pending.update(fields)
            pending.update(
                {"pending_action": "video_dubbing", "step": step, "current_step": step}
            )
            return dict(pending)

        namespace.update(
            {
                "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
                "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
                "SUBDUB_VISUAL_OCR_PUBLIC_ENABLED": False,
                "normalize_video_translate_mode": lambda value: str(value or "dub"),
                "_safe_int": lambda value, default=0: int(value or default),
                "resolve_subdub_execution_asr_kwargs": lambda _state: {},
                "set_subdub_active_pipeline_state": lambda _state: None,
                "reset_subdub_active_pipeline_state": lambda _token: None,
                "auto_multi_speaker": SimpleNamespace(
                    is_auto_multi_speaker_state=lambda state: state.get("auto_speaker_lane")
                    == "auto_multi_speaker"
                ),
                "auto_smart_multivoice": SimpleNamespace(
                    is_auto_smart_multivoice_state=lambda state: bool(
                        state.get("auto_smart_multivoice_opt_in")
                    )
                ),
                "video_dubbing_sync_state_fields": namespace[
                    "video_dubbing_sync_state_fields"
                ],
                "video_dubbing_resolve_source_script": resolve_source,
                "video_dubbing_is_subtitle_text_source": lambda *_args: False,
                "get_video_dubbing_artifact": lambda *_args: "",
                "set_video_dubbing_artifact": lambda *_args: "source-subtitle-ref",
                "set_video_dubbing_pending": set_pending,
                "video_dubbing_plain_script": lambda _subtitle: "hello",
                "video_dubbing_segments_from_subtitle": lambda _subtitle: [],
                "_extract_subdub_auto_pcm": extract_pcm,
                "subdub_speaker_cast": subdub_speaker_cast,
            }
        )
        state = {
            "_pipeline_workspace": "C:/tmp/subdub-smart-job",
            "_pipeline_source_bytes_override": b"source-video",
            "_pipeline_source_content_type_override": "video/mp4",
            "auto_smart_multivoice_opt_in": True,
            "mode": "dub",
            "video_processing_mode": "dub",
            "source_media_type": "video",
            "source_mime_type": "video/mp4",
        }

        with self.assertRaises(ExtractionReached):
            asyncio.run(prepare(None, state, 123, require_auto_cast=True))

        self.assertEqual(captured["prepared_workspace"], state["_pipeline_workspace"])
        self.assertEqual(captured["state_workspace"], state["_pipeline_workspace"])

    def test_auto_resolver_preserves_diarization_unavailable_exception(self):
        resolver, namespace = _load_resolver_from_production_source()

        async def no_embedded_subtitle(*_args, **_kwargs):
            return "", "none"

        async def diarization_unavailable(*_args, **_kwargs):
            return {
                "output_valid": False,
                "status": "AUTO_CAST_UNAVAILABLE",
                "detail": "deepgram_speaker_labels_missing",
            }

        namespace["video_dubbing_extract_embedded_subtitle"] = no_embedded_subtitle
        namespace["transcribe_media_to_segments"] = diarization_unavailable

        with self.assertRaisesRegex(
            subdub_speaker_cast.AutoCastUnavailable,
            "^AUTO_CAST_UNAVAILABLE$",
        ):
            asyncio.run(
                resolver(
                    b"media",
                    "video/mp4",
                    None,
                    require_diarization=True,
                )
            )

    def test_auto_preflight_converts_resolver_boundary_to_manual_recovery(self):
        resolver, namespace = _load_resolver_from_production_source()
        calls = {"post_prepare": 0, "extract_pcm": 0}
        state = {
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "mode": "dub",
        }

        async def no_embedded_subtitle(*_args, **_kwargs):
            return "", "none"

        async def diarization_unavailable(*_args, **_kwargs):
            return {
                "output_valid": False,
                "status": "AUTO_CAST_UNAVAILABLE",
                "detail": "deepgram_speaker_labels_missing",
            }

        async def prepare_subtitles(_state, *, require_auto_cast):
            self.assertTrue(require_auto_cast)
            return await resolver(
                b"media",
                "video/mp4",
                None,
                require_diarization=True,
            )

        async def post_prepare_gate(*_args, **_kwargs):
            calls["post_prepare"] += 1
            raise AssertionError("manual recovery must happen before post-prepare")

        async def extract_pcm(*_args, **_kwargs):
            calls["extract_pcm"] += 1
            raise AssertionError("manual recovery must happen before PCM extraction")

        namespace["video_dubbing_extract_embedded_subtitle"] = no_embedded_subtitle
        namespace["transcribe_media_to_segments"] = diarization_unavailable

        result = asyncio.run(
            auto_speaker.run_auto_speaker_preflight(
                state,
                prepare_subtitles=prepare_subtitles,
                post_prepare_gate=post_prepare_gate,
                extract_pcm=extract_pcm,
            )
        )

        self.assertEqual(result["status"], "AUTO_CAST_MANUAL_REQUIRED")
        self.assertEqual(result["reason"], "AUTO_CAST_UNAVAILABLE")
        self.assertEqual(calls, {"post_prepare": 0, "extract_pcm": 0})

    def test_manual_resolver_failure_keeps_legacy_runtime_error(self):
        resolver, namespace = _load_resolver_from_production_source()

        async def no_embedded_subtitle(*_args, **_kwargs):
            return "", "none"

        async def asr_unavailable(*_args, **_kwargs):
            return {"output_valid": False, "status": "asr_failed"}

        namespace["video_dubbing_extract_embedded_subtitle"] = no_embedded_subtitle
        namespace["transcribe_media_to_segments"] = asr_unavailable

        with self.assertRaisesRegex(RuntimeError, "^asr_failed$") as raised:
            asyncio.run(
                resolver(
                    b"media",
                    "video/mp4",
                    None,
                    require_diarization=False,
                )
            )
        self.assertIs(type(raised.exception), RuntimeError)


if __name__ == "__main__":
    unittest.main()
