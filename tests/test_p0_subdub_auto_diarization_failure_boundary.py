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


class AutoDiarizationFailureBoundaryTests(unittest.TestCase):
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
