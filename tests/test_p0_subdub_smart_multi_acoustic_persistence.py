import asyncio
import hashlib
import inspect
import os
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _load_prepare(namespace):
    sync_start = BOT_SOURCE.index("def video_dubbing_sync_state_fields(")
    sync_end = BOT_SOURCE.index("\ndef subdub_telegram_file_too_big", sync_start)
    prepare_start = BOT_SOURCE.index("async def video_dubbing_prepare_subtitles(")
    prepare_end = BOT_SOURCE.index("\ndef subdub_auto_validated_voice_pools", prepare_start)
    exec(compile(BOT_SOURCE[sync_start:sync_end], str(BOT_PATH), "exec"), namespace)
    exec(compile(BOT_SOURCE[prepare_start:prepare_end], str(BOT_PATH), "exec"), namespace)
    return namespace["video_dubbing_prepare_subtitles"]


def _load_resume_state(namespace):
    start = BOT_SOURCE.index("def _subdub_auto_resume_state(")
    end = BOT_SOURCE.index("\ndef _subdub_auto_persist_prepared_cache", start)
    exec(compile(BOT_SOURCE[start:end], str(BOT_PATH), "exec"), namespace)
    return namespace["_subdub_auto_resume_state"]


class SmartMultiAcousticPersistenceTests(unittest.TestCase):
    def test_fresh_smart_multi_persists_acoustic_registers_in_sidecar(self):
        captured = {}
        evidence = {
            "multi_acoustic_speaker_count": 3,
            "multi_acoustic_speaker_registers": ["high", "low", "low"],
            "multi_acoustic_speaker_register_confidences": [0.91, 0.88, 0.86],
            "multi_acoustic_female_speaker_count": 1,
            "multi_acoustic_male_speaker_count": 2,
        }

        class SidecarPersisted(Exception):
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

        async def diarize(*_args, **_kwargs):
            return {
                "segments": [
                    {"cue_id": f"cue-{index}", "text": "hello", "speaker": index}
                    for index in range(3)
                ],
                "provider": "wespeaker-resnet34",
                "model_sha256": "model-sha",
                "algorithm_version": "acoustic-v1",
                "detected_speaker_count": 3,
                "word_count": 1,
                "unit_count": 3,
                "embedding_window_count": 3,
                "speaker_registers": ["high", "low", "low"],
                "speaker_register_confidences": [0.91, 0.88, 0.86],
                "female_speaker_count": 1,
                "male_speaker_count": 2,
            }

        def persist_sidecar(sidecar, *, workspace):
            captured["sidecar"] = dict(sidecar)
            captured["workspace"] = workspace
            raise SidecarPersisted

        auto_multi = SimpleNamespace(
            is_auto_multi_speaker_state=lambda _state: False,
            bounded_multi_acoustic_evidence=lambda _source: dict(evidence),
            acoustic_sidecar_evidence=lambda _source: {
                "speaker_registers": list(evidence["multi_acoustic_speaker_registers"]),
                "speaker_register_confidences": list(
                    evidence["multi_acoustic_speaker_register_confidences"]
                ),
                "female_speaker_count": evidence["multi_acoustic_female_speaker_count"],
                "male_speaker_count": evidence["multi_acoustic_male_speaker_count"],
            },
            run_local_acoustic_diarization_off_event_loop=diarize,
        )
        speaker_cast = SimpleNamespace(
            AutoCastUnavailable=type("AutoCastUnavailable", (Exception,), {}),
            AutoCastManualRequired=type("AutoCastManualRequired", (Exception,), {}),
            valid_speaker_index=lambda value: type(value) is int and value >= 0,
            build_sidecar=lambda segments, **_kwargs: {"cues": list(segments)},
            persist_sidecar=persist_sidecar,
        )
        namespace = {
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "hashlib": hashlib,
            "inspect": inspect,
            "os": os,
            "Path": Path,
            "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
            "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
            "SUBDUB_VISUAL_OCR_PUBLIC_ENABLED": False,
            "normalize_video_translate_mode": lambda value: str(value or "dub"),
            "_safe_int": lambda value, default=0: int(value or default),
            "resolve_subdub_execution_asr_kwargs": lambda _state: {},
            "set_subdub_active_pipeline_state": lambda _state: None,
            "reset_subdub_active_pipeline_state": lambda _token: None,
            "auto_multi_speaker": auto_multi,
            "auto_smart_multivoice": SimpleNamespace(
                is_auto_smart_multivoice_state=lambda state: bool(
                    state.get("auto_smart_multivoice_opt_in")
                )
            ),
            "video_dubbing_resolve_source_script": resolve_source,
            "video_dubbing_is_subtitle_text_source": lambda *_args: False,
            "video_dubbing_plain_script": lambda _subtitle: "hello",
            "video_dubbing_segments_from_subtitle": lambda _subtitle: [],
            "video_dubbing_srt_from_segments": lambda _segments: "generated subtitle",
            "subdub_speaker_sidecar_subtitle_sha256": lambda _subtitle: "subtitle-sha",
            "set_video_dubbing_artifact": lambda *_args: "source-subtitle-ref",
            "get_video_dubbing_artifact": lambda *_args: "",
            "set_video_dubbing_pending": lambda _user_id, step, **fields: {
                **fields,
                "pending_action": "video_dubbing",
                "step": step,
                "current_step": step,
            },
            "_extract_subdub_auto_pcm": lambda *_args, **_kwargs: asyncio.sleep(0, result="source.pcm"),
            "subdub_speaker_cast": speaker_cast,
        }
        prepare = _load_prepare(namespace)
        state = {
            "_pipeline_workspace": "C:/tmp/smart-multi-job",
            "_pipeline_source_bytes_override": b"video",
            "_pipeline_source_content_type_override": "video/mp4",
            "auto_smart_multivoice_opt_in": True,
            "mode": "dub",
            "video_processing_mode": "dub",
            "source_media_type": "video",
            "source_mime_type": "video/mp4",
        }

        with self.assertRaises(SidecarPersisted):
            asyncio.run(prepare(None, state, 123, require_auto_cast=True))

        self.assertEqual(captured["workspace"], "C:/tmp/smart-multi-job")
        self.assertEqual(
            captured["sidecar"].get("acoustic", {}).get("speaker_registers"),
            ["high", "low", "low"],
        )
        self.assertEqual(
            captured["sidecar"]["acoustic"]["speaker_register_confidences"],
            [0.91, 0.88, 0.86],
        )
        self.assertEqual(captured["sidecar"]["acoustic"]["female_speaker_count"], 1)
        self.assertEqual(captured["sidecar"]["acoustic"]["male_speaker_count"], 2)

    def test_smart_multi_resume_preserves_register_lists(self):
        evidence = {
            "multi_acoustic_speaker_registers": ["high", "low", "low"],
            "multi_acoustic_speaker_register_confidences": [0.91, 0.88, 0.86],
            "multi_acoustic_female_speaker_count": 1,
            "multi_acoustic_male_speaker_count": 2,
            "multi_acoustic_gender_model_sha256": "gender-model-sha",
            "multi_acoustic_gender_ambiguous_window_count": 13,
            "multi_acoustic_speaker_count_authority_asr_independent": True,
            "multi_acoustic_word_attribution_uses_asr_timeline": True,
        }
        namespace = {
            "video_dubbing_sync_state_fields": lambda state, *, exclude=None: {
                key: value
                for key, value in dict(state or {}).items()
                if key not in (exclude or set())
                and not str(key).startswith("_pipeline_")
                and not isinstance(value, (bytes, bytearray))
            },
            "auto_multi_speaker": SimpleNamespace(
                is_auto_multi_speaker_state=lambda _state: False,
                bounded_multi_acoustic_evidence=lambda source: {
                    key: value for key, value in source.items() if key in evidence
                },
            ),
            "auto_smart_multivoice": SimpleNamespace(
                is_auto_smart_multivoice_state=lambda state: bool(
                    state.get("auto_smart_multivoice_opt_in")
                )
            ),
        }
        resume_state = _load_resume_state(namespace)
        state = {
            "auto_smart_multivoice_opt_in": True,
            "multi_acoustic_speaker_count": 3,
            "multi_acoustic_word_count": 630,
            "multi_acoustic_unit_count": 77,
            "multi_acoustic_embedding_window_count": 24,
            "multi_acoustic_word_coverage_count": 630,
            "multi_acoustic_overlap_mapped_count": 0,
            "multi_acoustic_centroid_mapped_count": 630,
            **evidence,
        }

        resumed = resume_state(state)

        self.assertEqual(
            resumed["multi_acoustic_speaker_registers"], ["high", "low", "low"]
        )
        self.assertEqual(
            resumed["multi_acoustic_speaker_register_confidences"],
            [0.91, 0.88, 0.86],
        )


if __name__ == "__main__":
    unittest.main()
