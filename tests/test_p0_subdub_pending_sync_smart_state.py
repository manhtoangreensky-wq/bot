import asyncio
import hashlib
import inspect
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import subdub_canonical_cues


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _load_functions(namespace):
    sync_start = BOT_SOURCE.index("def video_dubbing_sync_state_fields(")
    sync_end = BOT_SOURCE.index("\ndef subdub_telegram_file_too_big", sync_start)
    short_start = BOT_SOURCE.index("def _short_pending_text(")
    short_end = BOT_SOURCE.index("\ndef _safe_int", short_start)
    pending_start = BOT_SOURCE.index("def set_video_dubbing_pending(")
    pending_end = BOT_SOURCE.index("\ndef get_video_dubbing_pending", pending_start)
    single_start = BOT_SOURCE.index("def subdub_canonical_single_speaker_segments(")
    single_end = BOT_SOURCE.index("\nasync def _subdub_auto_bootstrap_cached_media_source", single_start)
    failure_start = BOT_SOURCE.index("def subdub_multi_acoustic_failure_evidence(")
    prepare_start = BOT_SOURCE.index("async def video_dubbing_prepare_subtitles(")
    prepare_end = BOT_SOURCE.index("\ndef subdub_auto_validated_voice_pools", prepare_start)
    source = "\n".join(
        (
            BOT_SOURCE[sync_start:sync_end],
            BOT_SOURCE[short_start:short_end],
            BOT_SOURCE[pending_start:pending_end],
            BOT_SOURCE[single_start:single_end],
            BOT_SOURCE[failure_start:prepare_start],
            BOT_SOURCE[prepare_start:prepare_end],
        )
    )
    exec(compile(source, "<subdub-pending-source>", "exec"), namespace)
    return namespace


def _namespace():
    auto_multi = SimpleNamespace(
        MULTI_ACOUSTIC_STATE_FIELDS=frozenset(),
        is_auto_multi_speaker_state=lambda _state: False,
        bounded_multi_acoustic_evidence=lambda _state: {},
        acoustic_sidecar_evidence=lambda _state: {},
        run_local_acoustic_diarization_off_event_loop=None,
    )
    speaker_cast = SimpleNamespace(
        AutoCastUnavailable=type("AutoCastUnavailable", (Exception,), {}),
        AutoCastManualRequired=type("AutoCastManualRequired", (Exception,), {}),
        valid_speaker_index=lambda value: type(value) is int and value >= 0,
        MAX_SIDECAR_CUES=10_000,
        build_sidecar=lambda segments, **_kwargs: {"cues": list(segments)},
        persist_sidecar=lambda _sidecar, *, workspace: {
            "path": str(Path(workspace) / "speaker_cast.sidecar.json"),
            "sha256": "sidecar-sha256",
        },
    )
    return {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": {},
        "video_dubbing_pending_key": lambda user_id: f"video_dubbing:{user_id}",
        "time": time,
        "hashlib": hashlib,
        "inspect": inspect,
        "os": os,
        "re": re,
        "Path": Path,
        "subdub_translation_cache_language_key": lambda value: str(value or "").lower(),
        "auto_multi_speaker": auto_multi,
        "auto_smart_multivoice": SimpleNamespace(
            is_auto_smart_multivoice_state=lambda state: bool(
                isinstance(state, dict)
                and (
                    state.get("auto_speaker_lane") == "auto_smart_multivoice"
                    or state.get("auto_smart_multivoice_opt_in") is True
                )
            )
        ),
        "normalize_video_translate_mode": lambda value: str(value or ""),
        "VIDEO_SUBTITLE_MODE_CREATE": "create",
        "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "VIDEO_DUBBING_FLOW_TRANSCRIPT": "transcript",
        "VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE": "subtitle_file_translation",
        "VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "subdub_product_type_from_mode": lambda mode, _state: mode,
        "subdub_expected_media_for_product": lambda _product: "video",
        "subdub_back_stack_for_entry": lambda mode, _origin: mode,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
        "SUBDUB_VISUAL_OCR_PUBLIC_ENABLED": False,
        "_safe_int": lambda value, default=0: int(value or default),
        "resolve_subdub_execution_asr_kwargs": lambda _state: {},
        "set_subdub_active_pipeline_state": lambda _state: None,
        "reset_subdub_active_pipeline_state": lambda _token: None,
        "video_dubbing_resolve_source_script": None,
        "video_dubbing_is_subtitle_text_source": lambda *_args: False,
        "video_dubbing_plain_script": lambda _subtitle: "hello",
        "video_dubbing_segments_from_subtitle": lambda _subtitle: [],
        "video_dubbing_srt_from_segments": lambda _segments: (
            "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
        ),
        "subdub_speaker_sidecar_subtitle_sha256": lambda _subtitle: "subtitle-sha",
        "set_video_dubbing_artifact": lambda *_args: "source-ref",
        "get_video_dubbing_artifact": lambda *_args: "",
        "_extract_subdub_auto_pcm": None,
        "subdub_speaker_cast": speaker_cast,
        "subdub_canonical_cues": subdub_canonical_cues,
        "subdub_canonical_auto_speaker_segments": None,
        "subdub_mode_requests_translation": lambda _mode, _state: False,
        "subdub_validate_cue_locked_timing": lambda *_args, **_kwargs: {"ok": True},
        "subdub_detect_language_from_text": lambda *_args: "en",
        "subtitle_dub_workspace_path_safety": lambda _path: {"allowed": True},
        "update_subtitle_dub_pipeline_job": lambda *_args, **_kwargs: None,
        "subdub_emit_progress_callback": lambda *_args, **_kwargs: asyncio.sleep(0),
    }


def _load_asr_contract(namespace):
    namespace.update({
        "DEEPGRAM_API_KEY": "configured-test-key",
        "ASR_PROVIDER": "deepgram",
        "AUTO_CAST_UNAVAILABLE": "AUTO_CAST_UNAVAILABLE",
        "get_asr_adapter_readiness": lambda **_kwargs: {"configured": True},
        "auto_speaker": SimpleNamespace(
            is_auto_speaker_state=lambda state: state.get("voice_selection_mode") == "auto_speaker",
        ),
        "video_dubbing_has_media": lambda _state: True,
    })
    fragments = []
    for start, end in (
        ("def resolve_subdub_asr_plan(", "\ndef video_dubbing_asr_missing_for_state"),
        ("def resolve_subdub_execution_asr_kwargs(", "\ndef video_dubbing_guard_text"),
        ("async def _subdub_auto_bootstrap_cached_media_source(", "\nasync def video_dubbing_prepare_subtitles"),
    ):
        first = BOT_SOURCE.index(start)
        fragments.append(BOT_SOURCE[first:BOT_SOURCE.index(end, first)])
    exec(compile("\n".join(fragments), "<subdub-asr-contract-source>", "exec"), namespace)
    return namespace


def test_smart_asr_without_snapshot_explicitly_disables_cloud_speaker_labels():
    namespace = _load_asr_contract(_namespace())
    kwargs = namespace["resolve_subdub_execution_asr_kwargs"]({
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": True,
    })

    assert kwargs["require_auto_multi_word_timeline"] is True
    assert kwargs.get("require_diarization") is False


def test_non_smart_asr_without_snapshot_keeps_legacy_kwargs():
    namespace = _load_asr_contract(_namespace())
    namespace["resolve_subdub_asr_plan"] = lambda **_kwargs: {
        "require_word_timeline": False, "require_provider_speaker_labels": False,
    }
    assert namespace["resolve_subdub_execution_asr_kwargs"]({"mode": "dub"}) == {}


@pytest.mark.parametrize("cached_subtitle", [False, True])
@pytest.mark.parametrize("has_snapshot", [False, True])
def test_smart_134_second_asr_reaches_local_acoustic_without_cloud_labels(
    cached_subtitle, has_snapshot,
):
    namespace = _load_asr_contract(_load_functions(_namespace()))
    captured = []

    class AcousticBoundaryReached(Exception):
        pass

    async def resolve_source(
        *_args, duration_seconds=0, require_auto_multi_word_timeline=False,
        require_diarization=False, **_kwargs,
    ):
        captured.append((duration_seconds, require_auto_multi_word_timeline, require_diarization))
        if require_diarization or not require_auto_multi_word_timeline:
            raise namespace["subdub_speaker_cast"].AutoCastUnavailable("ASR contract requires cloud labels")
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:01,000 --> 00:00:02,000\nhola\n",
            "segments": [{"start": 1.0, "end": 2.0, "text": "hola", "speaker": None}],
            "word_timeline": [{"index": 0, "word": "hola", "start": 1.0, "end": 2.0}],
            "duration_seconds": 134.0,
        }

    async def extract_pcm(*_args, **_kwargs):
        raise AcousticBoundaryReached()

    namespace["video_dubbing_resolve_source_script"] = resolve_source
    namespace["_extract_subdub_auto_pcm"] = extract_pcm
    namespace["get_video_dubbing_artifact"] = lambda _user, ref: (
        "1\n00:00:01,000 --> 00:00:02,000\ncached\n" if ref == "cached-ref" else ""
    )
    state = {
        "mode": "dub", "video_processing_mode": "dub", "input_duration": 134,
        "source_media_type": "video", "source_mime_type": "video/mp4",
        "_pipeline_source_bytes_override": b"normalized-134-second-source",
        "_pipeline_source_content_type_override": "video/mp4",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "voice_selection_mode": "auto_smart_multivoice",
        "subdub_final_confirmed": True,
    }
    if cached_subtitle:
        state["subtitle_ref"] = "cached-ref"
    if has_snapshot:
        state.update({
            "subdub_asr_plan_version": "r8_2",
            "subdub_asr_route_id": "smart_multivoice_deepgram",
            "subdub_asr_provider": "deepgram",
            "subdub_asr_require_word_timeline": True,
            "subdub_asr_require_provider_speaker_labels": False,
            "subdub_local_acoustic_diarization_allowed": True,
        })

    with pytest.raises(AcousticBoundaryReached):
        asyncio.run(namespace["video_dubbing_prepare_subtitles"](
            None, state, "smart-134", allow_confirmed_product=True, require_auto_cast=True,
        ))

    assert captured == [(134, True, False)]


@pytest.mark.parametrize("cached_subtitle", [False, True])
def test_exact_two_asr_keeps_cloud_diarization_contract(cached_subtitle):
    namespace = _load_asr_contract(_load_functions(_namespace()))
    captured = []

    class ResolverBoundaryReached(Exception):
        pass

    async def resolve_source(
        *_args, require_auto_multi_word_timeline=False, require_diarization=False, **_kwargs,
    ):
        captured.append((require_auto_multi_word_timeline, require_diarization))
        raise ResolverBoundaryReached()

    namespace["video_dubbing_resolve_source_script"] = resolve_source
    namespace["get_video_dubbing_artifact"] = lambda _user, ref: (
        "1\n00:00:01,000 --> 00:00:02,000\ncached\n" if ref == "cached-ref" else ""
    )
    state = {
        "mode": "dub", "input_duration": 134,
        "source_media_type": "video", "source_mime_type": "video/mp4",
        "_pipeline_source_bytes_override": b"exact-two-source",
        "voice_selection_mode": "auto_speaker",
    }
    if cached_subtitle:
        state["subtitle_ref"] = "cached-ref"

    with pytest.raises(ResolverBoundaryReached):
        asyncio.run(namespace["video_dubbing_prepare_subtitles"](
            None, state, "exact-two-134", allow_confirmed_product=True, require_auto_cast=True,
        ))

    assert captured == [(False, True)]


@pytest.mark.parametrize("count", range(1, 9))
def test_smart_generic_acoustic_keeps_detected_speakers_without_strict_multi_evidence(count):
    namespace = _load_asr_contract(_load_functions(_namespace()))
    namespace["auto_multi_speaker"].MULTI_ACOUSTIC_STATE_FIELDS = frozenset({"multi_acoustic_speaker_count"})
    namespace["USER_PENDING"]["video_dubbing:generic-smart"] = {
        "pending_action": "video_dubbing", "multi_acoustic_speaker_count": 3,
    }
    captured = {}
    classes = {
        f"chunk_00:speaker_{i}": {
            "speaker_id": f"chunk_00:speaker_{i}",
            "voice_register": "high" if i == 0 else "unknown",
            "confidence": 0.99 if i == 0 else 0.0,
        }
        for i in range(count)
    }

    async def resolve_source(*_args, require_auto_multi_word_timeline=False, require_diarization=False, **_kwargs):
        assert require_auto_multi_word_timeline and not require_diarization
        return {
            "source_kind": "asr", "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nspeech\n",
            "segments": [{"start": 0.0, "end": 1.0, "text": "speech", "speaker": None}],
            "word_timeline": [{"index": i, "word": "speech", "start": float(i), "end": i + 0.5} for i in range(count)],
            "duration_seconds": 134.0,
        }

    async def diarize(*_args, **kwargs):
        captured["minimum_speakers"] = kwargs.get("minimum_speakers")
        return {
            "segments": [
                {"cue_id": f"cue-{i}", "speaker_id": f"chunk_00:speaker_{i}", "speaker": i,
                 "chunk_index": 0, "start": float(i), "end": i + 0.5, "text": "speech"}
                for i in range(count)
            ],
            "detected_speaker_count": count, "word_coverage_count": count,
            "smart_acoustic_generic": True, "smart_acoustic_classifications": classes,
        }

    def persist(sidecar, *, workspace):
        captured["sidecar"] = sidecar
        return {"path": str(Path(workspace) / "speaker_cast.sidecar.json"), "sha256": "sidecar-sha"}

    namespace["video_dubbing_resolve_source_script"] = resolve_source
    namespace["_extract_subdub_auto_pcm"] = lambda *_a, **_k: asyncio.sleep(0, result="source.pcm")
    namespace["auto_multi_speaker"].run_local_acoustic_diarization_off_event_loop = diarize
    namespace["subdub_speaker_cast"].persist_sidecar = persist
    state = {
        "mode": "dub", "input_duration": 134,
        "source_media_type": "video", "source_mime_type": "video/mp4",
        "_pipeline_workspace": "C:/tmp/generic-smart", "_pipeline_source_bytes_override": b"source",
        "auto_smart_multivoice_opt_in": True, "auto_speaker_lane": "auto_smart_multivoice",
        "subdub_final_confirmed": True,
    }
    prepared = asyncio.run(namespace["video_dubbing_prepare_subtitles"](
        None, state, "generic-smart", require_auto_cast=True, allow_confirmed_product=True,
    ))

    assert captured["minimum_speakers"] == 1
    assert len(prepared["acoustic_classifications"]) == count
    assert len({segment["speaker_id"] for segment in prepared["source_segments"]}) == count
    assert prepared["state"]["auto_smart_generic_acoustic"] is True
    assert "multi_acoustic_speaker_count" not in prepared["state"]
    assert "acoustic" not in captured["sidecar"]


def test_smart_multi_pending_sync_excludes_user_id_and_keeps_route_contract():
    namespace = _load_functions(_namespace())
    state = {
        "user_id": "smart-user-1",
        "mode": "dub",
        "auto_speaker_lane": "auto_smart_multivoice",
        "voice_selection_mode": "auto_smart_multivoice",
        "auto_smart_multivoice_opt_in": True,
        "auto_smart_dispatch": "n3_plus_proven_v2",
        "subdub_engine_requested": "auto_smart_multivoice",
        "subdub_asr_plan_version": "r8_2",
        "subdub_asr_require_provider_speaker_labels": False,
        "subdub_local_acoustic_diarization_allowed": True,
        "auto_smart_degraded_single_voice": True,
        "auto_smart_degraded_reason": "fixed_vocal_speaker_count_unstable",
    }

    sync_fields = namespace["video_dubbing_sync_state_fields"](state)
    pending = namespace["set_video_dubbing_pending"](
        "smart-user-1", "processing", **sync_fields
    )

    assert "user_id" not in sync_fields
    assert pending["auto_smart_multivoice_opt_in"] is True
    assert pending["subdub_asr_require_provider_speaker_labels"] is False
    for key in (
        "auto_smart_multivoice_opt_in",
        "auto_smart_dispatch",
        "subdub_engine_requested",
        "subdub_asr_plan_version",
        "subdub_asr_require_provider_speaker_labels",
        "subdub_local_acoustic_diarization_allowed",
        "auto_smart_degraded_single_voice",
        "auto_smart_degraded_reason",
    ):
        assert pending[key] == state[key]


@pytest.mark.parametrize("wrapped_failure", [False, True])
@pytest.mark.parametrize("failure_code", [
    "fixed_vocal_speaker_count_unstable", "fixed_vocal_view_unstable",
])
def test_smart_multi_unstable_fixed_count_degrades_to_one_voice_without_acoustic_claim(wrapped_failure, failure_code):
    tmp_root = BOT_PATH.parent / ".pytest_tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(prefix="smart_multi_", dir=tmp_root))
    namespace = _namespace()
    captured = {}
    words = [f"word{index:02d}" for index in range(31)]
    source_segments = [
        {"start": float(index * 10), "end": float(index * 10 + 6),
         "text": " ".join(words[index * 8:(index + 1) * 8]), "speaker": None}
        for index in range(4)
    ]

    async def resolve_source(*_args, **_kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
            "segments": source_segments,
            "word_timeline": [
                {"word": word, "start": float(index), "end": float(index + 0.5)}
                for index, word in enumerate(words)
            ],
            "duration_seconds": 60.0,
        }

    async def pcm_extract(*_args, **_kwargs):
        return str(tmp_path / "source.pcm")

    async def unstable_diarization(*_args, **_kwargs):
        if wrapped_failure:
            raise namespace["subdub_speaker_cast"].AutoCastManualRequired() from ValueError(failure_code)
        raise ValueError(failure_code)

    def persist_sidecar(sidecar, *, workspace):
        captured["sidecar"] = dict(sidecar)
        return {
            "path": str(Path(workspace) / "speaker_cast.sidecar.json"),
            "sha256": "sidecar-sha256",
        }

    namespace["video_dubbing_resolve_source_script"] = resolve_source
    namespace["_extract_subdub_auto_pcm"] = pcm_extract
    namespace["auto_multi_speaker"].run_local_acoustic_diarization_off_event_loop = (
        unstable_diarization
    )
    namespace["subdub_speaker_cast"].persist_sidecar = persist_sidecar
    namespace["set_video_dubbing_artifact"] = lambda *_args: "source-ref"
    namespace["get_video_dubbing_artifact"] = lambda *_args: ""
    namespace = _load_functions(namespace)
    state = {
        "user_id": "smart-user-2",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"video-bytes",
        "_pipeline_source_content_type_override": "video/mp4",
        "auto_speaker_lane": "auto_smart_multivoice",
        "voice_selection_mode": "auto_smart_multivoice",
        "auto_smart_multivoice_opt_in": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "subdub_asr_plan_version": "r8_2",
        "mode": "dub",
        "video_processing_mode": "dub",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
    }

    try:
        prepared = asyncio.run(
            namespace["video_dubbing_prepare_subtitles"](
                None, state, "smart-user-2", require_auto_cast=True
            )
        )
        pending = namespace["USER_PENDING"]["video_dubbing:smart-user-2"]

        assert {segment["speaker_id"] for segment in prepared["source_segments"]} == {
            "chunk_00:speaker_0"
        }
        assert [segment["text"] for segment in prepared["source_segments"]] == [
            segment["text"] for segment in source_segments
        ]
        assert {segment["speaker"] for segment in captured["sidecar"]["cues"]} == {0}
        assert "acoustic" not in captured["sidecar"]
        assert pending["auto_smart_degraded_single_voice"] is True
        assert pending["auto_smart_degraded_reason"] == failure_code

        async def unrelated_failure(*_args, **_kwargs):
            raise ValueError("unrelated_acoustic_failure")

        namespace["auto_multi_speaker"].run_local_acoustic_diarization_off_event_loop = (
            unrelated_failure
        )
        with pytest.raises(ValueError, match="unrelated_acoustic_failure"):
            asyncio.run(
                namespace["video_dubbing_prepare_subtitles"](
                    None, state, "smart-user-3", require_auto_cast=True
                )
            )
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
