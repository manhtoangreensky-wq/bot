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
    prepare_start = BOT_SOURCE.index("async def video_dubbing_prepare_subtitles(")
    prepare_end = BOT_SOURCE.index("\ndef subdub_auto_validated_voice_pools", prepare_start)
    source = "\n".join(
        (
            BOT_SOURCE[sync_start:sync_end],
            BOT_SOURCE[short_start:short_end],
            BOT_SOURCE[pending_start:pending_end],
            BOT_SOURCE[single_start:single_end],
            BOT_SOURCE[prepare_start:prepare_end],
        )
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
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


def test_smart_multi_unstable_fixed_count_degrades_to_one_voice_without_acoustic_claim():
    tmp_root = BOT_PATH.parent / ".pytest_tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(prefix="smart_multi_", dir=tmp_root))
    namespace = _namespace()
    captured = {}

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

    async def pcm_extract(*_args, **_kwargs):
        return str(tmp_path / "source.pcm")

    async def unstable_diarization(*_args, **_kwargs):
        raise ValueError("fixed_vocal_speaker_count_unstable")

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
        assert {segment["speaker"] for segment in captured["sidecar"]["cues"]} == {0}
        assert "acoustic" not in captured["sidecar"]
        assert pending["auto_smart_degraded_single_voice"] is True
        assert pending["auto_smart_degraded_reason"] == "fixed_vocal_speaker_count_unstable"

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
