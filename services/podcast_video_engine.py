"""Truthful, UI-free Podcast Video route and local FFmpeg engine for 29K.

The local lane preserves one approved audio track from an audio or video
source. It consumes a completed transcript artifact instead of pretending to
perform ASR or diarization. Approved still visuals become one or more ordered
scenes, then captions, an optional waveform, logo, and watermark are applied
before a fully decoded MP4 can be finalized.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from array import array
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from services import frame_video_runtime
from services import ffmpeg_text
from services import multiscene_video_pipeline as pipeline
from services import video_engine_contract


PRODUCT_FAMILY = "podcast_video"
ROUTE_ID = "podcast_video_local_v1"
ENGINE_ADAPTER = "podcast_video_local_ffmpeg_v29k"
WORKER_JOB_TYPE = "podcast_video_local_render"
WORKER_OWNER = "local_worker"
CANONICAL_WORKER_CAPABILITY = "podcast_video_local_ffmpeg"
SUPPORTED_MODES = (
    video_engine_contract.VideoEngineMode.SINGLE_SCENE.value,
    video_engine_contract.VideoEngineMode.MULTI_SCENE.value,
)
ALLOWED_SOURCE_TYPES = ("audio", "video")
SUPPORTED_LAYOUTS = ("single_visual", "scene_visuals", "speaker_layout")
PODCAST_VIDEO_ENGINE_FLAG_DEFAULTS = {
    "PODCAST_VIDEO_ENGINE_ENABLED": False,
    "PODCAST_VIDEO_RUNTIME_REGISTERED": False,
    "PODCAST_VIDEO_PUBLIC_ALLOWED": False,
    "PODCAST_VIDEO_AUTO_RETRY": False,
    "PODCAST_VIDEO_AUTO_FALLBACK": False,
}
SUPPORTED_POSITIONS = {
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
}
TIMELINE_TOLERANCE_SECONDS = 0.08
DIARIZATION_CONFIDENCE_MIN = 0.80
SPEECH_PCM_SAMPLE_RATE = 16_000
SPEECH_FEATURE_WINDOW_SAMPLES = 320
SPEECH_CONTENT_SIMILARITY_MIN = 0.92
OVERLAY_REGION_MIN_MEAN_ABS_DIFF = 0.25
OVERLAY_REGION_STRONG_CHANNEL_DIFF = 18
OVERLAY_REGION_MIN_STRONG_DIFF_RATIO = 0.0001


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _strict_bool(value: Any, blocker: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return value == 1
    token = _clean(value).lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(blocker)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _speech_pcm_feature_profile(path: str | Path) -> dict[str, Any]:
    raw_features: list[tuple[float, float]] = []
    peak_abs = 0
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            if (
                channels != 1
                or sample_width != 2
                or sample_rate != SPEECH_PCM_SAMPLE_RATE
            ):
                raise ValueError("podcast_speech_pcm_profile_invalid")
            while True:
                frames = handle.readframes(SPEECH_FEATURE_WINDOW_SAMPLES)
                if not frames:
                    break
                window = array("h")
                window.frombytes(frames)
                if sys.byteorder != "little":
                    window.byteswap()
                if len(window) < SPEECH_FEATURE_WINDOW_SAMPLES // 2:
                    continue
                peak_abs = max(
                    peak_abs,
                    max(abs(int(sample)) for sample in window),
                )
                rms = math.sqrt(
                    sum(float(sample) * float(sample) for sample in window)
                    / len(window)
                ) / 32768.0
                zero_crossings = sum(
                    1
                    for previous, current in zip(window, window[1:])
                    if (previous < 0 <= current) or (previous >= 0 > current)
                )
                raw_features.append(
                    (rms, zero_crossings / max(1, len(window) - 1))
                )
    except ValueError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError("podcast_speech_pcm_invalid") from exc
    if not raw_features:
        raise ValueError("podcast_speech_pcm_too_short")
    max_rms = max(value[0] for value in raw_features)
    features = tuple(
        (
            round(rms / max(max_rms, 0.000001), 5),
            round(zero_crossing_rate, 5),
        )
        for rms, zero_crossing_rate in raw_features
    )
    non_silent_windows = sum(1 for rms, _zcr in raw_features if rms >= 0.001)
    return {
        "pcm_sha256": _sha256_file(path),
        "feature_sha256": _sha256_text(_canonical_json(features)),
        "features": features,
        "window_count": len(features),
        "peak_abs": peak_abs,
        "non_silent_ratio": round(non_silent_windows / len(features), 6),
    }


def compare_speech_pcm_content(
    source_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    source = _speech_pcm_feature_profile(source_path)
    output = _speech_pcm_feature_profile(output_path)
    source_features = source["features"]
    output_features = output["features"]
    minimum_overlap = max(1, int(min(len(source_features), len(output_features)) * 0.85))
    best_similarity = 0.0
    for lag in range(-8, 9):
        source_start = max(0, -lag)
        output_start = max(0, lag)
        overlap = min(
            len(source_features) - source_start,
            len(output_features) - output_start,
        )
        if overlap < minimum_overlap:
            continue
        source_window = source_features[source_start : source_start + overlap]
        output_window = output_features[output_start : output_start + overlap]
        rms_error = sum(
            abs(left[0] - right[0])
            for left, right in zip(source_window, output_window)
        ) / overlap
        crossing_error = sum(
            abs(left[1] - right[1])
            for left, right in zip(source_window, output_window)
        ) / overlap
        similarity = max(
            0.0,
            1.0
            - 0.60 * min(1.0, rms_error)
            - 0.40 * min(1.0, crossing_error / 0.08),
        )
        best_similarity = max(best_similarity, similarity)
    content_match = bool(
        source["peak_abs"] >= 64
        and source["non_silent_ratio"] >= 0.01
        and best_similarity >= SPEECH_CONTENT_SIMILARITY_MIN
    )
    return {
        "content_match": content_match,
        "similarity": round(best_similarity, 6),
        "source_pcm_sha256": source["pcm_sha256"],
        "output_pcm_sha256": output["pcm_sha256"],
        "source_feature_sha256": source["feature_sha256"],
        "output_feature_sha256": output["feature_sha256"],
        "source_window_count": source["window_count"],
        "output_window_count": output["window_count"],
        "source_non_silent_ratio": source["non_silent_ratio"],
    }


def _valid_sha256(value: Any) -> bool:
    token = _clean(value).lower()
    return len(token) == 64 and all(character in "0123456789abcdef" for character in token)


def _normalize_ratio(value: Any) -> str:
    token = _clean(value or "9:16").lower().replace("x", ":")
    if token not in {"9:16", "16:9", "1:1", "4:5"}:
        raise ValueError("podcast_aspect_ratio_unsupported")
    return token


def _strict_position(value: Any, fallback: str, field_name: str) -> str:
    token = (_clean(value) or fallback).lower().replace("-", "_")
    if token not in SUPPORTED_POSITIONS:
        raise ValueError(f"{field_name}_invalid")
    return token


def _normalize_motion(value: Any) -> str:
    token = _clean(value or "ken_burns").lower().replace("-", "_")
    token = {"pan": "pan_horizontal", "push_in": "zoom_in", "push_out": "zoom_out"}.get(
        token,
        token,
    )
    if token not in frame_video_runtime.MOTIONS or token == "none":
        raise ValueError("podcast_motion_unsupported")
    return token


def _bounded_float(value: Any, blocker: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(blocker)
    try:
        selected = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(blocker) from exc
    if selected < minimum or selected > maximum:
        raise ValueError(blocker)
    return selected


def podcast_video_engine_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in PODCAST_VIDEO_ENGINE_FLAG_DEFAULTS.items()
    }


def shared_podcast_video_engine_route() -> dict[str, Any]:
    return {
        "product": PRODUCT_FAMILY,
        "state": video_engine_contract.VideoRouteState.CONNECTED.value,
        "connected": True,
        "public_product_type": PRODUCT_FAMILY,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ADAPTER,
        "worker_owner": WORKER_OWNER,
        "required_capability": CANONICAL_WORKER_CAPABILITY,
        "required_capabilities": (CANONICAL_WORKER_CAPABILITY,),
        "supported_modes": SUPPORTED_MODES,
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }


def missing_podcast_video_runtime_route() -> dict[str, Any]:
    return {
        "product": PRODUCT_FAMILY,
        "state": video_engine_contract.VideoRouteState.ENGINE_MISSING.value,
        "connected": False,
        "public_product_type": "",
        "worker_job_type": "",
        "engine_route": "",
        "worker_owner": "",
        "required_capability": "",
        "required_capabilities": (),
        "supported_modes": (),
        "provider_enabled": False,
        "local_enabled": False,
        "blocker": "podcast_runtime_entrypoint_missing",
    }


def podcast_video_engine_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "engine_adapter": ENGINE_ADAPTER,
        "supported_modes": SUPPORTED_MODES,
        "allowed_source_types": ALLOWED_SOURCE_TYPES,
        "supported_layouts": SUPPORTED_LAYOUTS,
        "completed_transcript_required": True,
        "automatic_asr": False,
        "automatic_diarization": False,
        "active_speaker_qc_required": True,
        "provider_required": False,
        "provider_calls": 0,
        "music_generation": False,
        "automatic_retry": False,
        "automatic_fallback": False,
        "production_finalizer_ready": False,
        "durable_exactly_once": False,
        "production_finalizer_blocker": "podcast_production_finalizer_missing",
        "fixture_finalizer": "in_memory_local_legal_fixture_only",
        "artifact_promise": {
            "container": "mp4",
            "video_stream": True,
            "speech_audio_stream": True,
            "full_decode": True,
            "unclipped_speech": True,
            "ordered_scenes": True,
            "transcript_coverage": True,
        },
        "flags": podcast_video_engine_flags(environ),
    }


def _source_material(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise ValueError("podcast_source_required")
    source_type = _clean(source.get("source_type")).lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("podcast_source_type_unsupported")
    source_id = _clean(source.get("source_id"))
    rights_receipt_id = _clean(source.get("rights_receipt_id"))
    if not source_id:
        raise ValueError("podcast_source_id_required")
    if not _flag(source.get("rights_approved")) or not rights_receipt_id:
        raise ValueError("podcast_source_rights_required")
    path = Path(_clean(source.get("path"))).expanduser()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("podcast_source_artifact_required")
    actual_sha = _sha256_file(path)
    expected_sha = _clean(source.get("sha256")).lower()
    if expected_sha and expected_sha != actual_sha:
        raise ValueError("podcast_source_artifact_fingerprint_mismatch")
    return {
        "source_id": source_id,
        "source_type": source_type,
        "source_sha256": actual_sha,
        "source_bytes": path.stat().st_size,
        "rights_receipt_id": rights_receipt_id,
    }


def podcast_source_fingerprint(source: Mapping[str, Any]) -> str:
    return _sha256_text(_canonical_json(_source_material(source)))


def _probe_media(path: str | Path, ffprobe_path: str = "") -> dict[str, Any]:
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""
    if not ffprobe:
        raise ValueError("ffprobe_missing")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("podcast_source_probe_failed") from exc
    if completed.returncode != 0:
        raise ValueError("podcast_source_probe_failed")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("podcast_source_probe_failed") from exc
    streams = tuple(payload.get("streams") or ())
    audio_streams: list[Mapping[str, Any]] = []
    video_streams: list[Mapping[str, Any]] = []
    audio_stream_indexes: list[int] = []
    video_stream_indexes: list[int] = []
    for fallback_index, item in enumerate(streams):
        codec_type = _clean(item.get("codec_type"))
        try:
            stream_index = int(item.get("index"))
        except (TypeError, ValueError):
            stream_index = fallback_index
        if codec_type == "audio":
            audio_streams.append(item)
            audio_stream_indexes.append(stream_index)
        elif codec_type == "video":
            video_streams.append(item)
            video_stream_indexes.append(stream_index)
    duration_values: list[float] = []
    for value in (
        [payload.get("format", {}).get("duration")]
        + [item.get("duration") for item in streams]
    ):
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            duration_values.append(duration)
    audio_duration_values: list[float] = []
    for item in audio_streams:
        try:
            duration = float(item.get("duration"))
        except (TypeError, ValueError):
            continue
        if duration > 0:
            audio_duration_values.append(duration)
    duration_seconds = max(duration_values or [0.0])
    audio_duration_seconds = max(audio_duration_values or [duration_seconds])
    return {
        "duration_seconds": round(duration_seconds, 6),
        "audio_duration_seconds": round(audio_duration_seconds, 6),
        "audio_stream_count": len(audio_streams),
        "video_stream_count": len(video_streams),
        "audio_stream_indexes": tuple(audio_stream_indexes),
        "video_stream_indexes": tuple(video_stream_indexes),
        "selected_audio_stream_index": (
            audio_stream_indexes[0] if audio_stream_indexes else -1
        ),
        "audio_codecs": tuple(_clean(item.get("codec_name")) for item in audio_streams),
        "video_codecs": tuple(_clean(item.get("codec_name")) for item in video_streams),
    }


def probe_podcast_source(
    source: Mapping[str, Any],
    *,
    ffprobe_path: str = "",
) -> dict[str, Any]:
    source_info = _source_material(source)
    path = Path(_clean(source.get("path"))).expanduser()
    probe = _probe_media(path, ffprobe_path)
    if probe["audio_stream_count"] < 1 or probe["duration_seconds"] <= 0:
        raise ValueError("podcast_source_audio_required")
    if source_info["source_type"] == "video" and probe["video_stream_count"] < 1:
        raise ValueError("podcast_source_video_required")
    return {
        "ok": True,
        "blocker": "",
        **source_info,
        **probe,
        "source_fingerprint": _sha256_text(_canonical_json(source_info)),
    }


def _normalize_transcript(
    source_fingerprint: str,
    transcript: Mapping[str, Any],
    *,
    source_duration_seconds: float,
    layout_mode: str,
) -> dict[str, Any]:
    if not isinstance(transcript, Mapping) or _clean(transcript.get("status")).lower() != "completed":
        raise ValueError("podcast_transcript_required")
    if _clean(transcript.get("source_fingerprint")).lower() != source_fingerprint:
        raise ValueError("podcast_transcript_source_mismatch")
    transcriber = _clean(transcript.get("transcriber"))
    language = _clean(transcript.get("language"))
    if not transcriber:
        raise ValueError("podcast_transcriber_required")
    if not language:
        raise ValueError("podcast_transcript_language_required")
    try:
        speaker_count = int(transcript.get("speaker_count") or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("podcast_speaker_count_invalid") from exc
    if speaker_count < 1 or speaker_count > 16:
        raise ValueError("podcast_speaker_count_invalid")
    raw_segments = tuple(transcript.get("segments") or ())
    if not raw_segments:
        raise ValueError("podcast_transcript_required")
    normalized_segments: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_speakers: set[str] = set()
    previous_start = -1.0
    for raw in raw_segments:
        if not isinstance(raw, Mapping):
            raise ValueError("podcast_transcript_segment_invalid")
        segment_id = _clean(raw.get("segment_id"))
        text = _clean(raw.get("text"))
        if not segment_id or segment_id in seen_ids or not text:
            raise ValueError("podcast_transcript_segment_invalid")
        start = _bounded_float(
            raw.get("start_seconds"),
            "podcast_transcript_segment_invalid",
            minimum=0.0,
            maximum=source_duration_seconds + TIMELINE_TOLERANCE_SECONDS,
        )
        end = _bounded_float(
            raw.get("end_seconds"),
            "podcast_transcript_segment_invalid",
            minimum=0.0,
            maximum=source_duration_seconds + TIMELINE_TOLERANCE_SECONDS,
        )
        if end <= start or start < previous_start:
            raise ValueError("podcast_transcript_segment_invalid")
        previous_start = start
        speaker_id = _clean(raw.get("speaker_id"))
        if speaker_count == 1:
            speaker_id = speaker_id or "speaker-1"
            if speaker_id != "speaker-1":
                raise ValueError("podcast_speaker_mapping_invalid")
        elif not speaker_id:
            raise ValueError("podcast_speaker_mapping_invalid")
        seen_ids.add(segment_id)
        seen_speakers.add(speaker_id)
        normalized_segments.append(
            {
                "segment_id": segment_id,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": text,
                "speaker_id": speaker_id,
            }
        )
    if speaker_count > 1 and len(seen_speakers) != speaker_count:
        raise ValueError("podcast_speaker_mapping_invalid")
    raw_diarization = dict(transcript.get("diarization") or {})
    diarization_required = speaker_count > 1 or layout_mode == "speaker_layout"
    if diarization_required:
        if _clean(raw_diarization.get("status")).lower() != "completed":
            raise ValueError("podcast_diarization_required")
        model = _clean(raw_diarization.get("model"))
        confidence = _bounded_float(
            raw_diarization.get("confidence"),
            "podcast_diarization_confidence_invalid",
            minimum=0.0,
            maximum=1.0,
        )
        if not model or confidence < DIARIZATION_CONFIDENCE_MIN:
            raise ValueError("podcast_diarization_confidence_invalid")
        active_speaker_qc = _flag(raw_diarization.get("active_speaker_qc_passed"))
        if layout_mode == "speaker_layout" and not active_speaker_qc:
            raise ValueError("podcast_active_speaker_qc_required")
        diarization = {
            "required": True,
            "status": "completed",
            "model": model,
            "confidence": confidence,
            "active_speaker_qc_passed": active_speaker_qc,
        }
    else:
        diarization = {
            "required": False,
            "status": "not_required",
            "model": "",
            "confidence": 0.0,
            "active_speaker_qc_passed": False,
        }
    material = {
        "source_fingerprint": source_fingerprint,
        "transcriber": transcriber,
        "language": language,
        "speaker_count": speaker_count,
        "diarization": diarization,
        "segments": normalized_segments,
    }
    return {
        **material,
        "transcript_sha256": _sha256_text(_canonical_json(material)),
        "active_speaker_accuracy_claimed": bool(
            layout_mode == "speaker_layout"
            and diarization["active_speaker_qc_passed"]
            and diarization["confidence"] >= DIARIZATION_CONFIDENCE_MIN
        ),
    }


@dataclass(frozen=True)
class PodcastScene:
    scene_id: str
    scene_index: int
    start_seconds: float
    end_seconds: float
    transcript_segment_ids: tuple[str, ...]
    speaker_ids: tuple[str, ...]
    visual_prompt: str
    asset_id: str
    asset_path: str
    asset_sha256: str
    asset_bytes: int
    asset_rights_approved: bool
    asset_rights_receipt_id: str
    motion: str

    @property
    def duration_seconds(self) -> float:
        return round(self.end_seconds - self.start_seconds, 3)


@dataclass(frozen=True)
class PodcastVideoPlan:
    mode: str
    layout_mode: str
    source_id: str
    source_type: str
    source_fingerprint: str
    source_sha256: str
    source_bytes: int
    source_rights_receipt_id: str
    source_duration_seconds: float
    source_audio_stream_count: int
    source_audio_stream_index: int
    source_video_stream_count: int
    transcriber: str
    transcript_language: str
    speaker_count: int
    diarization: Mapping[str, Any]
    active_speaker_accuracy_claimed: bool
    transcript_segments: tuple[Mapping[str, Any], ...]
    transcript_sha256: str
    scenes: tuple[PodcastScene, ...]
    aspect_ratio: str
    captions_enabled: bool
    waveform_enabled: bool
    final_assets: Mapping[str, Any]
    expected_duration_seconds: float
    scene_order_sha256: str
    transcript_coverage_sha256: str
    plan_sha256: str


def _scene_material(scene: PodcastScene) -> dict[str, Any]:
    return {
        "scene_id": scene.scene_id,
        "scene_index": scene.scene_index,
        "start_seconds": scene.start_seconds,
        "end_seconds": scene.end_seconds,
        "duration_seconds": scene.duration_seconds,
        "transcript_segment_ids": scene.transcript_segment_ids,
        "speaker_ids": scene.speaker_ids,
        "visual_prompt": scene.visual_prompt,
        "asset_id": scene.asset_id,
        "asset_sha256": scene.asset_sha256,
        "asset_bytes": scene.asset_bytes,
        "asset_rights_approved": scene.asset_rights_approved,
        "asset_rights_receipt_id": scene.asset_rights_receipt_id,
        "motion": scene.motion,
    }


def _coverage_material(plan: PodcastVideoPlan) -> dict[str, Any]:
    return {
        "source_fingerprint": plan.source_fingerprint,
        "transcript_sha256": plan.transcript_sha256,
        "segments": plan.transcript_segments,
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "scene_index": scene.scene_index,
                "start_seconds": scene.start_seconds,
                "end_seconds": scene.end_seconds,
                "transcript_segment_ids": scene.transcript_segment_ids,
                "speaker_ids": scene.speaker_ids,
            }
            for scene in plan.scenes
        ],
    }


def _plan_material(plan: PodcastVideoPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "layout_mode": plan.layout_mode,
        "source_id": plan.source_id,
        "source_type": plan.source_type,
        "source_fingerprint": plan.source_fingerprint,
        "source_sha256": plan.source_sha256,
        "source_bytes": plan.source_bytes,
        "source_rights_receipt_id": plan.source_rights_receipt_id,
        "source_duration_seconds": plan.source_duration_seconds,
        "source_audio_stream_count": plan.source_audio_stream_count,
        "source_audio_stream_index": plan.source_audio_stream_index,
        "source_video_stream_count": plan.source_video_stream_count,
        "transcriber": plan.transcriber,
        "transcript_language": plan.transcript_language,
        "speaker_count": plan.speaker_count,
        "diarization": plan.diarization,
        "active_speaker_accuracy_claimed": plan.active_speaker_accuracy_claimed,
        "transcript_segments": plan.transcript_segments,
        "transcript_sha256": plan.transcript_sha256,
        "scenes": [_scene_material(scene) for scene in plan.scenes],
        "aspect_ratio": plan.aspect_ratio,
        "captions_enabled": plan.captions_enabled,
        "waveform_enabled": plan.waveform_enabled,
        "final_assets": {
            key: value for key, value in plan.final_assets.items() if key != "logo_path"
        },
        "expected_duration_seconds": plan.expected_duration_seconds,
        "scene_order_sha256": plan.scene_order_sha256,
        "transcript_coverage_sha256": plan.transcript_coverage_sha256,
    }


def _normalize_final_assets(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    logo_path_value = _clean(raw.get("logo_path"))
    explicit_logo_enabled = raw.get(
        "logo_enabled",
        raw.get("enable_logo", bool(logo_path_value)),
    )
    logo_enabled = _strict_bool(
        explicit_logo_enabled,
        "podcast_logo_enabled_invalid",
    )
    logo_path = Path(logo_path_value).expanduser() if logo_path_value else None
    logo_sha = _clean(raw.get("logo_sha256")).lower()
    logo_rights_approved = _strict_bool(
        raw.get("logo_rights_approved", False),
        "podcast_logo_asset_rights_required",
    )
    logo_rights_receipt_id = _clean(raw.get("logo_rights_receipt_id"))
    if logo_enabled:
        if logo_path is None or not logo_path.is_file() or logo_path.stat().st_size <= 0:
            raise ValueError("podcast_logo_asset_missing")
        actual_sha = _sha256_file(logo_path)
        if logo_sha and logo_sha != actual_sha:
            raise ValueError("podcast_logo_asset_fingerprint_mismatch")
        logo_sha = actual_sha
        if not logo_rights_approved or not logo_rights_receipt_id:
            raise ValueError("podcast_logo_asset_rights_required")
    caption_position = _strict_position(
        raw.get("caption_position"),
        "bottom_center",
        "podcast_caption_position",
    )
    if caption_position != "bottom_center":
        raise ValueError("podcast_caption_position_unsupported")
    return {
        "logo_enabled": logo_enabled,
        "logo_asset_id": _clean(raw.get("logo_asset_id") or "podcast-logo") if logo_enabled else "",
        "logo_path": str(logo_path.resolve()) if logo_enabled and logo_path else "",
        "logo_sha256": logo_sha if logo_enabled else "",
        "logo_bytes": logo_path.stat().st_size if logo_enabled and logo_path else 0,
        "logo_rights_approved": logo_rights_approved if logo_enabled else False,
        "logo_rights_receipt_id": logo_rights_receipt_id if logo_enabled else "",
        "logo_position": _strict_position(
            raw.get("logo_position"),
            "top_left",
            "podcast_logo_position",
        ),
        "watermark_text": _clean(raw.get("watermark_text"))[:500],
        "watermark_position": _strict_position(
            raw.get("watermark_position"),
            "bottom_right",
            "podcast_watermark_position",
        ),
        "caption_position": caption_position,
    }


def compile_podcast_video_plan(
    *,
    source: Mapping[str, Any],
    transcript: Mapping[str, Any],
    scenes: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    mode: str,
    layout_mode: str,
    aspect_ratio: str = "9:16",
    captions_enabled: bool = True,
    waveform_enabled: bool = False,
    final_assets: Mapping[str, Any] | None = None,
    ffprobe_path: str = "",
) -> PodcastVideoPlan:
    selected_mode = _clean(mode).lower()
    if selected_mode not in SUPPORTED_MODES:
        raise ValueError("podcast_mode_unsupported")
    selected_layout = _clean(layout_mode).lower()
    if selected_layout not in SUPPORTED_LAYOUTS:
        raise ValueError("podcast_layout_unsupported")
    raw_scenes = tuple(scenes or ())
    if selected_mode == "single_scene" and len(raw_scenes) != 1:
        raise ValueError("single_scene_requires_one_scene")
    if selected_mode == "multi_scene" and len(raw_scenes) < 2:
        raise ValueError("multi_scene_requires_multiple_scenes")
    if selected_layout == "single_visual" and len(raw_scenes) != 1:
        raise ValueError("podcast_single_visual_requires_one_scene")
    source_probe = probe_podcast_source(source, ffprobe_path=ffprobe_path)
    source_fingerprint = source_probe["source_fingerprint"]
    transcript_info = _normalize_transcript(
        source_fingerprint,
        transcript,
        source_duration_seconds=float(source_probe["duration_seconds"]),
        layout_mode=selected_layout,
    )
    transcript_by_id = {
        str(item["segment_id"]): item for item in transcript_info["segments"]
    }
    known_speakers = {
        _clean(item.get("speaker_id")) for item in transcript_info["segments"]
    }
    compiled_scenes: list[PodcastScene] = []
    covered_segments: list[str] = []
    cursor = 0.0
    for ordinal, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError("podcast_scene_invalid")
        scene_index = int(raw.get("scene_index") or ordinal)
        if scene_index != ordinal:
            raise ValueError("podcast_scene_order_invalid")
        start = _bounded_float(
            raw.get("start_seconds"),
            "podcast_scene_timeline_invalid",
            minimum=0.0,
            maximum=float(source_probe["duration_seconds"]) + TIMELINE_TOLERANCE_SECONDS,
        )
        end = _bounded_float(
            raw.get("end_seconds"),
            "podcast_scene_timeline_invalid",
            minimum=0.0,
            maximum=float(source_probe["duration_seconds"]) + TIMELINE_TOLERANCE_SECONDS,
        )
        if end <= start:
            raise ValueError("podcast_scene_timeline_invalid")
        if start > cursor + TIMELINE_TOLERANCE_SECONDS:
            raise ValueError("podcast_scene_timeline_gap")
        if start < cursor - TIMELINE_TOLERANCE_SECONDS:
            raise ValueError("podcast_scene_timeline_overlap")
        if end - start < 1.0:
            raise ValueError("podcast_scene_timeline_invalid")
        cursor = end
        segment_ids = tuple(
            _clean(item)
            for item in (raw.get("transcript_segment_ids") or ())
            if _clean(item)
        )
        if not segment_ids or len(set(segment_ids)) != len(segment_ids):
            raise ValueError("podcast_transcript_segment_coverage_invalid")
        if any(item not in transcript_by_id or item in covered_segments for item in segment_ids):
            raise ValueError("podcast_transcript_segment_coverage_invalid")
        for segment_id in segment_ids:
            segment = transcript_by_id[segment_id]
            if (
                float(segment["start_seconds"]) < start - TIMELINE_TOLERANCE_SECONDS
                or float(segment["end_seconds"]) > end + TIMELINE_TOLERANCE_SECONDS
            ):
                raise ValueError("podcast_transcript_segment_coverage_invalid")
            covered_segments.append(segment_id)
        speaker_ids = tuple(
            _clean(item) for item in (raw.get("speaker_ids") or ()) if _clean(item)
        )
        if not speaker_ids or any(item not in known_speakers for item in speaker_ids):
            raise ValueError("podcast_speaker_mapping_invalid")
        referenced_speakers = {
            _clean(transcript_by_id[item].get("speaker_id")) for item in segment_ids
        }
        if selected_layout == "speaker_layout" and not referenced_speakers <= set(speaker_ids):
            raise ValueError("podcast_speaker_mapping_invalid")
        visual_prompt = _clean(raw.get("visual_prompt"))
        asset_id = _clean(raw.get("asset_id"))
        asset_path = Path(_clean(raw.get("asset_path"))).expanduser()
        rights_receipt = _clean(raw.get("asset_rights_receipt_id"))
        if not visual_prompt:
            raise ValueError("podcast_visual_prompt_required")
        if not asset_id or not asset_path.is_file() or asset_path.stat().st_size <= 0:
            raise ValueError("podcast_scene_asset_missing")
        asset_sha = _sha256_file(asset_path)
        expected_sha = _clean(raw.get("asset_sha256")).lower()
        if expected_sha and expected_sha != asset_sha:
            raise ValueError("podcast_scene_asset_fingerprint_mismatch")
        if not _flag(raw.get("asset_rights_approved")) or not rights_receipt:
            raise ValueError("podcast_scene_asset_rights_required")
        compiled_scenes.append(
            PodcastScene(
                scene_id=_clean(raw.get("scene_id") or f"scene-{ordinal}"),
                scene_index=scene_index,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                transcript_segment_ids=segment_ids,
                speaker_ids=speaker_ids,
                visual_prompt=visual_prompt,
                asset_id=asset_id,
                asset_path=str(asset_path.resolve()),
                asset_sha256=asset_sha,
                asset_bytes=asset_path.stat().st_size,
                asset_rights_approved=True,
                asset_rights_receipt_id=rights_receipt,
                motion=_normalize_motion(raw.get("motion")),
            )
        )
    if abs(cursor - float(source_probe["duration_seconds"])) > TIMELINE_TOLERANCE_SECONDS:
        raise ValueError("podcast_scene_timeline_gap")
    if set(covered_segments) != set(transcript_by_id) or len(covered_segments) != len(transcript_by_id):
        raise ValueError("podcast_transcript_segment_coverage_invalid")
    final_asset_info = _normalize_final_assets(final_assets)
    scene_order_sha = _sha256_text(
        _canonical_json(
            [
                {
                    "scene_id": scene.scene_id,
                    "scene_index": scene.scene_index,
                    "start_seconds": scene.start_seconds,
                    "end_seconds": scene.end_seconds,
                    "asset_sha256": scene.asset_sha256,
                }
                for scene in compiled_scenes
            ]
        )
    )
    provisional = PodcastVideoPlan(
        mode=selected_mode,
        layout_mode=selected_layout,
        source_id=source_probe["source_id"],
        source_type=source_probe["source_type"],
        source_fingerprint=source_fingerprint,
        source_sha256=source_probe["source_sha256"],
        source_bytes=int(source_probe["source_bytes"]),
        source_rights_receipt_id=_clean(source_probe["rights_receipt_id"]),
        source_duration_seconds=round(float(source_probe["duration_seconds"]), 3),
        source_audio_stream_count=int(source_probe["audio_stream_count"]),
        source_audio_stream_index=int(source_probe["selected_audio_stream_index"]),
        source_video_stream_count=int(source_probe["video_stream_count"]),
        transcriber=transcript_info["transcriber"],
        transcript_language=transcript_info["language"],
        speaker_count=int(transcript_info["speaker_count"]),
        diarization=_json_safe(transcript_info["diarization"]),
        active_speaker_accuracy_claimed=bool(
            transcript_info["active_speaker_accuracy_claimed"]
        ),
        transcript_segments=tuple(
            _json_safe(item) for item in transcript_info["segments"]
        ),
        transcript_sha256=transcript_info["transcript_sha256"],
        scenes=tuple(compiled_scenes),
        aspect_ratio=_normalize_ratio(aspect_ratio),
        captions_enabled=_strict_bool(
            captions_enabled,
            "podcast_captions_enabled_invalid",
        ),
        waveform_enabled=_strict_bool(
            waveform_enabled,
            "podcast_waveform_enabled_invalid",
        ),
        final_assets=_json_safe(final_asset_info),
        expected_duration_seconds=round(float(source_probe["duration_seconds"]), 3),
        scene_order_sha256=scene_order_sha,
        transcript_coverage_sha256="",
        plan_sha256="",
    )
    coverage_sha = _sha256_text(_canonical_json(_coverage_material(provisional)))
    provisional = replace(provisional, transcript_coverage_sha256=coverage_sha)
    return replace(
        provisional,
        plan_sha256=_sha256_text(_canonical_json(_plan_material(provisional))),
    )


def validate_podcast_video_plan(plan: PodcastVideoPlan) -> dict[str, Any]:
    if not isinstance(plan, PodcastVideoPlan):
        return {"ok": False, "blocker": "podcast_plan_required"}
    if _sha256_text(_canonical_json(_plan_material(plan))) != plan.plan_sha256:
        return {"ok": False, "blocker": "podcast_plan_hash_mismatch"}
    if _sha256_text(_canonical_json(_coverage_material(plan))) != plan.transcript_coverage_sha256:
        return {"ok": False, "blocker": "podcast_transcript_coverage_hash_mismatch"}
    count = len(plan.scenes)
    if plan.mode == "single_scene" and count != 1:
        return {"ok": False, "blocker": "single_scene_requires_one_scene"}
    if plan.mode == "multi_scene" and count < 2:
        return {"ok": False, "blocker": "multi_scene_requires_multiple_scenes"}
    if plan.mode not in SUPPORTED_MODES:
        return {"ok": False, "blocker": "podcast_mode_unsupported"}
    if plan.layout_mode not in SUPPORTED_LAYOUTS:
        return {"ok": False, "blocker": "podcast_layout_unsupported"}
    if [scene.scene_index for scene in plan.scenes] != list(range(1, count + 1)):
        return {"ok": False, "blocker": "podcast_scene_order_invalid"}
    if (
        plan.source_audio_stream_count < 1
        or plan.source_audio_stream_index < 0
        or not _valid_sha256(plan.source_sha256)
    ):
        return {"ok": False, "blocker": "podcast_source_audio_required"}
    if not _valid_sha256(plan.transcript_sha256):
        return {"ok": False, "blocker": "podcast_transcript_invalid"}
    transcript_ids = [_clean(item.get("segment_id")) for item in plan.transcript_segments]
    covered = [item for scene in plan.scenes for item in scene.transcript_segment_ids]
    if not transcript_ids or len(set(transcript_ids)) != len(transcript_ids):
        return {"ok": False, "blocker": "podcast_transcript_invalid"}
    if covered != transcript_ids:
        return {"ok": False, "blocker": "podcast_transcript_segment_coverage_invalid"}
    if plan.active_speaker_accuracy_claimed and (
        plan.layout_mode != "speaker_layout"
        or not _flag(plan.diarization.get("active_speaker_qc_passed"))
        or float(plan.diarization.get("confidence") or 0.0) < DIARIZATION_CONFIDENCE_MIN
    ):
        return {"ok": False, "blocker": "podcast_active_speaker_qc_required"}
    final_assets = dict(plan.final_assets or {})
    if final_assets.get("logo_enabled") and (
        not _valid_sha256(final_assets.get("logo_sha256"))
        or int(final_assets.get("logo_bytes") or 0) <= 0
        or not _flag(final_assets.get("logo_rights_approved"))
        or not _clean(final_assets.get("logo_rights_receipt_id"))
    ):
        return {"ok": False, "blocker": "podcast_logo_asset_manifest_invalid"}
    return {
        "ok": True,
        "blocker": "",
        "scene_count": count,
        "scene_order": [scene.scene_index for scene in plan.scenes],
        "transcript_segment_count": len(plan.transcript_segments),
        "transcript_coverage_complete": True,
        "source_duration_seconds": plan.source_duration_seconds,
        "scene_order_sha256": plan.scene_order_sha256,
        "transcript_coverage_sha256": plan.transcript_coverage_sha256,
        "plan_sha256": plan.plan_sha256,
    }


def build_podcast_video_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    plan: PodcastVideoPlan,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    admin_no_charge: bool = False,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    validation = validate_podcast_video_plan(plan)
    if not validation.get("ok"):
        raise ValueError(_clean(validation.get("blocker") or "podcast_plan_invalid"))
    mode = video_engine_contract.VideoEngineMode(plan.mode)
    payload = {
        "route_id": ROUTE_ID,
        "plan_sha256": plan.plan_sha256,
        "source_fingerprint": plan.source_fingerprint,
        "transcript_sha256": plan.transcript_sha256,
        "transcript_coverage_sha256": plan.transcript_coverage_sha256,
        "scene_order_sha256": plan.scene_order_sha256,
        "scene_count": len(plan.scenes),
        "admin_no_charge": _strict_bool(
            admin_no_charge,
            "podcast_admin_no_charge_invalid",
        ),
        "charge_plan": _json_safe(dict(charge_plan or {})),
        "provider_calls": 0,
        "music_generation": False,
        "automatic_retry": False,
        "automatic_fallback": False,
    }
    approved_plan = {
        "route_id": ROUTE_ID,
        "approved": True,
        "mode": plan.mode,
        "layout_mode": plan.layout_mode,
        "source_id": plan.source_id,
        "source_type": plan.source_type,
        "source_fingerprint": plan.source_fingerprint,
        "source_sha256": plan.source_sha256,
        "source_audio_stream_index": plan.source_audio_stream_index,
        "source_rights_receipt_id": plan.source_rights_receipt_id,
        "transcript_sha256": plan.transcript_sha256,
        "plan_sha256": plan.plan_sha256,
        "scenes": [_scene_material(scene) for scene in plan.scenes],
    }
    input_assets = tuple(
        [
            {
                "asset_id": plan.source_id,
                "asset_type": plan.source_type,
                "asset_sha256": plan.source_sha256,
                "asset_bytes": plan.source_bytes,
                "audio_stream_index": plan.source_audio_stream_index,
                "rights_receipt_id": plan.source_rights_receipt_id,
            }
        ]
        + [
            {
                "scene_index": scene.scene_index,
                "asset_id": scene.asset_id,
                "asset_sha256": scene.asset_sha256,
                "asset_bytes": scene.asset_bytes,
                "rights_receipt_id": scene.asset_rights_receipt_id,
            }
            for scene in plan.scenes
        ]
    )
    if plan.final_assets.get("logo_enabled"):
        input_assets += (
            {
                "asset_id": _clean(plan.final_assets.get("logo_asset_id")),
                "asset_type": "image",
                "asset_sha256": _clean(plan.final_assets.get("logo_sha256")),
                "asset_bytes": int(plan.final_assets.get("logo_bytes") or 0),
                "rights_receipt_id": _clean(
                    plan.final_assets.get("logo_rights_receipt_id")
                ),
            },
        )
    common = {
        "user_id": user_id,
        "language": language,
        "approved_plan": approved_plan,
        "input_assets": input_assets,
        "aspect_ratio": plan.aspect_ratio,
        "duration_profile": {
            "duration_seconds": plan.expected_duration_seconds,
            "profile": "podcast_video_local",
        },
        "audio_policy": {
            "enabled": True,
            "source_sha256": plan.source_sha256,
            "selected_audio_stream_index": plan.source_audio_stream_index,
            "preserve_speech": True,
            "music_generation": False,
        },
        "voice_policy": {
            "enabled": False,
            "completed_transcript": True,
            "automatic_asr": False,
        },
        "provider_selection": "local",
        "runtime_sha": runtime_sha,
        "expected_worker_sha": expected_worker_sha,
    }
    key = video_engine_contract.stable_request_idempotency_key(
        confirmation_id=confirmation_id,
        product_type=video_engine_contract.VideoProduct.PODCAST_VIDEO,
        mode=mode,
        payload=payload,
        **common,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"{ROUTE_ID}:{key[:20]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.PODCAST_VIDEO,
        mode=mode,
        explicit_confirmation_receipt=dict(explicit_confirmation_receipt),
        confirmed=True,
        payload=payload,
        **common,
    )


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_clean(item) for item in value if _clean(item))
    return ()


def podcast_video_engine_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: PodcastVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
) -> dict[str, Any]:
    flags = podcast_video_engine_flags(environ)
    blocker = ""
    if not flags["PODCAST_VIDEO_ENGINE_ENABLED"]:
        blocker = "podcast_video_engine_disabled"
    elif public_request and not flags["PODCAST_VIDEO_PUBLIC_ALLOWED"]:
        blocker = "podcast_video_public_disabled"
    elif flags["PODCAST_VIDEO_AUTO_RETRY"]:
        blocker = "automatic_retry_forbidden"
    elif flags["PODCAST_VIDEO_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.PODCAST_VIDEO:
        blocker = "podcast_video_product_required"
    elif request.mode.value != plan.mode:
        blocker = "podcast_video_mode_mismatch"
    plan_validation = validate_podcast_video_plan(plan)
    if not blocker and not plan_validation.get("ok"):
        blocker = _clean(plan_validation.get("blocker") or "podcast_plan_invalid")
    if not blocker and request.payload.get("plan_sha256") != plan.plan_sha256:
        blocker = "podcast_request_plan_mismatch"
    shared = video_engine_contract.evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not blocker and not shared.get("ready"):
        blocker = _clean(shared.get("blocker") or "worker_not_ready")
    if not blocker and ENGINE_ADAPTER not in set(_sequence(manifest.get("engine_adapters"))):
        blocker = "worker_adapter_missing"
    if not blocker and not _flag(manifest.get("artifact_ready")):
        blocker = "worker_artifact_not_ready"
    return {
        "ready": not blocker,
        "submit_allowed": not blocker,
        "blocker": blocker,
        "flags": flags,
        "plan": plan_validation,
        "shared_readiness": shared,
        "route": shared_podcast_video_engine_route(),
        "provider_calls": 0,
        "music_generation": False,
    }


@dataclass
class PodcastVideoEngineLedger:
    jobs_by_idempotency: dict[str, video_engine_contract.VideoEngineJob] = field(default_factory=dict)
    records_by_job_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    render_count: int = 0
    compose_count: int = 0
    provider_calls: int = 0
    paid_provider_calls: int = 0
    music_generation_calls: int = 0
    delivery_count: int = 0
    production_telegram_deliveries: int = 0
    receipt_count: int = 0
    charge_attempts: int = 0
    wallet_mutations: int = 0
    terminal_report_count: int = 0


def _ledger_counters(ledger: PodcastVideoEngineLedger) -> dict[str, int]:
    return {
        "job_count": len(ledger.jobs_by_idempotency),
        "render_count": ledger.render_count,
        "compose_count": ledger.compose_count,
        "provider_calls": ledger.provider_calls,
        "paid_provider_calls": ledger.paid_provider_calls,
        "music_generation_calls": ledger.music_generation_calls,
        "delivery_count": ledger.delivery_count,
        "production_telegram_deliveries": ledger.production_telegram_deliveries,
        "receipt_count": ledger.receipt_count,
        "charge_attempts": ledger.charge_attempts,
        "wallet_mutations": ledger.wallet_mutations,
        "terminal_report_count": ledger.terminal_report_count,
    }


def _job_factory(
    request: video_engine_contract.VideoEngineRequest,
    route: Mapping[str, Any],
) -> video_engine_contract.VideoEngineJob:
    return video_engine_contract.VideoEngineJob(
        job_id=f"p29k-{request.idempotency_key[:24]}",
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type=_clean(route.get("worker_job_type")),
        engine_route=_clean(route.get("engine_route")),
        worker_owner=_clean(route.get("worker_owner")),
        status="queued",
    )


def _dispatch_result(
    ledger: PodcastVideoEngineLedger,
    record: Mapping[str, Any] | None,
    *,
    submitted: bool,
    idempotent_replay: bool,
    blocker: str = "",
) -> dict[str, Any]:
    current = dict(record or {})
    return {
        "ok": bool(current and not blocker),
        "submitted": bool(submitted),
        "idempotent_replay": bool(idempotent_replay),
        "blocker": blocker,
        "job_id": _clean(current.get("job_id")),
        "terminal_state": _clean(current.get("terminal_state")),
        **_ledger_counters(ledger),
    }


def dispatch_podcast_video(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: PodcastVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: PodcastVideoEngineLedger,
    environ: Mapping[str, Any] | None,
    public_request: bool = False,
) -> dict[str, Any]:
    readiness = podcast_video_engine_readiness(
        request,
        plan=plan,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
        public_request=public_request,
    )
    if not readiness.get("ready"):
        return {
            **_dispatch_result(
                ledger,
                None,
                submitted=False,
                idempotent_replay=False,
                blocker=_clean(readiness.get("blocker") or "podcast_video_not_ready"),
            ),
            "readiness": readiness,
        }
    guarded = video_engine_contract.guarded_submit(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        jobs_by_idempotency=ledger.jobs_by_idempotency,
        submitter=_job_factory,
        environ=environ,
    )
    job = guarded.get("job")
    if not isinstance(job, video_engine_contract.VideoEngineJob):
        return {
            **_dispatch_result(
                ledger,
                None,
                submitted=False,
                idempotent_replay=False,
                blocker=_clean(guarded.get("blocker") or "podcast_job_not_created"),
            ),
            "readiness": readiness,
        }
    record = ledger.records_by_job_id.get(job.job_id)
    if record is None:
        record = {
            "job_id": job.job_id,
            "request": request,
            "plan": plan,
            "admin_no_charge": bool(request.payload.get("admin_no_charge")),
            "render_attempted": False,
            "artifact_path": "",
            "artifact_sha256": "",
            "output_bytes": 0,
            "evidence_dir": "",
            "terminal_state": "queued",
            "blocker": "",
            "validation": {},
            "delivery": {},
            "receipt": {},
            "charge": {},
            "terminal_report": {},
        }
        ledger.records_by_job_id[job.job_id] = record
    return {
        **_dispatch_result(
            ledger,
            record,
            submitted=bool(guarded.get("submitted")),
            idempotent_replay=bool(guarded.get("idempotent_replay")),
        ),
        "readiness": readiness,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _output_geometry(aspect_ratio: str) -> tuple[int, int]:
    return {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1": (720, 720),
        "4:5": (720, 900),
    }[_normalize_ratio(aspect_ratio)]


@contextmanager
def _selected_pipeline_ffmpeg(ffmpeg: str):
    selected = str(Path(ffmpeg).resolve())
    previous = os.environ.get("FFMPEG_PATH")
    os.environ["FFMPEG_PATH"] = selected
    try:
        discovered = pipeline._ffmpeg_path()
        if not discovered or Path(discovered).resolve() != Path(selected):
            raise RuntimeError("podcast_pipeline_ffmpeg_mismatch")
        yield
    finally:
        if previous is None:
            os.environ.pop("FFMPEG_PATH", None)
        else:
            os.environ["FFMPEG_PATH"] = previous


def _full_decode(path: str, ffmpeg: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [ffmpeg, "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "podcast_full_decode_failed"}
    return {
        "ok": completed.returncode == 0,
        "reason": "" if completed.returncode == 0 else "podcast_full_decode_failed",
    }


def _extract_speech_pcm(
    *,
    input_path: str | Path,
    output_path: str | Path,
    stream_index: int,
    ffmpeg: str,
) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(input_path),
                "-map",
                f"0:{int(stream_index)}",
                "-vn",
                "-sn",
                "-dn",
                "-ac",
                "1",
                "-ar",
                str(SPEECH_PCM_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("podcast_speech_pcm_extract_failed") from exc
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("podcast_speech_pcm_extract_failed")
    return str(target)


def _motion_evidence(path: str, ffmpeg: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                path,
                "-map",
                "0:v:0",
                "-vf",
                "fps=4",
                "-frames:v",
                "12",
                "-f",
                "framemd5",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "podcast_motion_probe_failed", "unique_frames": 0}
    hashes = {
        line.rsplit(",", 1)[-1].strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "," in line
    }
    return {
        "ok": completed.returncode == 0 and len(hashes) > 1,
        "reason": "" if completed.returncode == 0 and len(hashes) > 1 else "podcast_motion_invalid",
        "unique_frames": len(hashes),
    }


def _overlay_region_box(
    *,
    position: str,
    width: int,
    height: int,
    width_ratio: float,
    height_ratio: float,
) -> tuple[int, int, int, int]:
    selected = _strict_position(position, "center", "podcast_overlay_evidence_position")
    crop_width = max(2, min(width, int(round(width * width_ratio))))
    crop_height = max(2, min(height, int(round(height * height_ratio))))
    crop_width -= crop_width % 2
    crop_height -= crop_height % 2
    if selected in {"top_left", "center_left", "bottom_left"}:
        x = 0
    elif selected in {"top_center", "center", "bottom_center"}:
        x = (width - crop_width) // 2
    else:
        x = width - crop_width
    if selected in {"top_left", "top_center", "top_right"}:
        y = 0
    elif selected in {"center_left", "center", "center_right"}:
        y = (height - crop_height) // 2
    else:
        y = height - crop_height
    return crop_width, crop_height, max(0, x), max(0, y)


def _video_region_frame(
    *,
    path: str | Path,
    ffmpeg: str,
    timestamp_seconds: float,
    width: int,
    height: int,
    box: tuple[int, int, int, int],
) -> bytes:
    crop_width, crop_height, x, y = box
    filtergraph = (
        f"scale={width}:{height}:flags=bicubic,"
        f"crop={crop_width}:{crop_height}:{x}:{y},format=rgb24"
    )
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-ss",
                f"{max(0.0, float(timestamp_seconds)):.3f}",
                "-frames:v",
                "1",
                "-vf",
                filtergraph,
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("podcast_overlay_visual_probe_failed") from exc
    expected_bytes = crop_width * crop_height * 3
    payload = bytes(completed.stdout or b"")
    if completed.returncode != 0 or len(payload) != expected_bytes:
        raise RuntimeError("podcast_overlay_visual_probe_failed")
    return payload


def _overlay_visual_evidence(
    *,
    baseline_path: str | Path,
    output_path: str | Path,
    ffmpeg: str,
    timestamp_seconds: float,
    width: int,
    height: int,
    position: str,
    width_ratio: float,
    height_ratio: float,
) -> dict[str, Any]:
    box = _overlay_region_box(
        position=position,
        width=width,
        height=height,
        width_ratio=width_ratio,
        height_ratio=height_ratio,
    )
    try:
        baseline = _video_region_frame(
            path=baseline_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=timestamp_seconds,
            width=width,
            height=height,
            box=box,
        )
        output = _video_region_frame(
            path=output_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=timestamp_seconds,
            width=width,
            height=height,
            box=box,
        )
    except RuntimeError as exc:
        return {
            "ok": False,
            "changed": False,
            "reason": _clean(exc) or "podcast_overlay_visual_probe_failed",
            "position": position,
            "region": list(box),
        }
    channel_differences = [
        abs(int(before) - int(after))
        for before, after in zip(baseline, output)
    ]
    mean_difference = sum(channel_differences) / len(channel_differences)
    strong_difference_ratio = sum(
        1
        for difference in channel_differences
        if difference >= OVERLAY_REGION_STRONG_CHANNEL_DIFF
    ) / len(channel_differences)
    changed = bool(
        mean_difference >= OVERLAY_REGION_MIN_MEAN_ABS_DIFF
        and strong_difference_ratio >= OVERLAY_REGION_MIN_STRONG_DIFF_RATIO
    )
    return {
        "ok": changed,
        "changed": changed,
        "reason": "" if changed else "podcast_overlay_visual_change_missing",
        "position": position,
        "timestamp_seconds": round(float(timestamp_seconds), 3),
        "region": list(box),
        "mean_absolute_difference": round(mean_difference, 6),
        "strong_difference_ratio": round(strong_difference_ratio, 8),
        "baseline_frame_sha256": hashlib.sha256(baseline).hexdigest(),
        "output_frame_sha256": hashlib.sha256(output).hexdigest(),
    }


def _unrequested_visual_evidence(position: str = "") -> dict[str, Any]:
    return {
        "ok": True,
        "changed": False,
        "requested": False,
        "position": position,
    }


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _srt_caption_text(value: Any) -> str:
    text = ffmpeg_text.sanitize_overlay_text(_clean(value), limit=4_000)
    return (
        text.replace("-->", "-- >")
        .replace("<", "[")
        .replace(">", "]")
        .replace("{", "(")
        .replace("}", ")")
    )


def _write_transcript_srt(plan: PodcastVideoPlan, path: Path) -> str:
    blocks = [
        (
            f"{index}\n"
            f"{_srt_time(float(segment['start_seconds']))} --> "
            f"{_srt_time(float(segment['end_seconds']))}\n"
            f"{_srt_caption_text(segment['text'])}\n"
        )
        for index, segment in enumerate(plan.transcript_segments, start=1)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")
    return str(path)


def _scene_runtime_state(
    scene: PodcastScene,
    plan: PodcastVideoPlan,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = Path(scene.asset_path).suffix.lower()
    mime_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    photos = [
        {
            "file_id": scene.asset_id,
            "file_unique_id": scene.asset_sha256,
            "file_name": Path(scene.asset_path).name,
            "file_size": scene.asset_bytes,
            "mime_type": mime_type,
            "source": "podcast_video_engine_29k",
        }
    ]
    runtime_manifest = frame_video_runtime.canonical_image_manifest(photos)
    image_id = runtime_manifest[0]["image_id"]
    state = {
        "photos": runtime_manifest,
        "image_count": 1,
        "ratio": plan.aspect_ratio.replace(":", "x"),
        "duration_seconds": scene.duration_seconds,
        "image_durations": {image_id: scene.duration_seconds},
        "transition": "none",
        "motion": scene.motion,
        "image_motions": {image_id: scene.motion},
        "fit_mode": "contain",
        "background_color": "#111111",
        "quality": "fast",
        "text_overlays": [],
        "font_path": os.environ.get("TOANAAS_FFMPEG_FONT", ""),
    }
    return runtime_manifest, state


def _overlay_waveform(
    *,
    master_video_path: str,
    source_path: str,
    output_path: str,
    width: int,
    height: int,
    duration_seconds: float,
    ffmpeg: str,
) -> str:
    wave_height = max(80, min(240, height // 5))
    filtergraph = (
        f"[1:a:0]showwaves=s={width}x{wave_height}:mode=line:rate=24:"
        "colors=white@0.85,format=rgba[wave];"
        "[0:v:0][wave]overlay=x=0:y=H-h-70:shortest=1[vout]"
    )
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            master_video_path,
            "-i",
            source_path,
            "-filter_complex",
            filtergraph,
            "-map",
            "[vout]",
            "-an",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0 or not Path(output_path).is_file():
        raise RuntimeError("podcast_waveform_render_failed")
    return output_path


def _watermark_font_path() -> str:
    candidates = (
        _clean(os.environ.get("TOANAAS_FFMPEG_FONT")),
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    return next(
        (str(Path(item).resolve()) for item in candidates if item and Path(item).is_file()),
        "",
    )


def _watermark_position(position: str) -> tuple[str, str]:
    token = _strict_position(position, "bottom_right", "podcast_watermark_position")
    if token in {"top_left", "center_left", "bottom_left"}:
        x_expr = "24"
    elif token in {"top_center", "center", "bottom_center"}:
        x_expr = "(w-text_w)/2"
    else:
        x_expr = "w-text_w-24"
    if token in {"top_left", "top_center", "top_right"}:
        y_expr = "24"
    elif token in {"center_left", "center", "center_right"}:
        y_expr = "(h-text_h)/2"
    else:
        y_expr = "h-text_h-24"
    return x_expr, y_expr


def _overlay_watermark(
    *,
    master_video_path: str,
    output_path: str,
    text: str,
    position: str,
    duration_seconds: float,
    ffmpeg: str,
) -> str:
    content = ffmpeg_text.sanitize_overlay_text(text)
    if not content:
        raise RuntimeError("podcast_watermark_text_invalid")
    font = _watermark_font_path()
    if not font:
        raise RuntimeError("podcast_watermark_font_missing")
    x_expr, y_expr = _watermark_position(position)
    filtergraph = (
        "drawtext="
        f"fontfile='{ffmpeg_text.escape_filter_path(font)}':"
        f"text='{ffmpeg_text.escape_filter_text(content)}':"
        f"{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:fontcolor=white:fontsize=36:"
        "borderw=2:bordercolor=black@0.65:box=1:boxcolor=black@0.25:"
        f"boxborderw=10:x={x_expr}:y={y_expr}"
    )
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            master_video_path,
            "-map",
            "0:v:0",
            "-vf",
            filtergraph,
            "-an",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0 or not Path(output_path).is_file():
        raise RuntimeError("podcast_watermark_render_failed")
    return output_path


def _execution_result(
    ledger: PodcastVideoEngineLedger,
    record: Mapping[str, Any],
    *,
    ok: bool,
    blocker: str = "",
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "blocker": blocker,
        "job_id": _clean(record.get("job_id")),
        "terminal_state": _clean(record.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "output_path": _clean(record.get("artifact_path")),
        "output_bytes": int(record.get("output_bytes") or 0),
        "evidence_dir": _clean(record.get("evidence_dir")),
        "validation": dict(record.get("validation") or {}),
        **_ledger_counters(ledger),
    }


def _fail_record(
    ledger: PodcastVideoEngineLedger,
    record: dict[str, Any],
    blocker: str,
    *,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    record["blocker"] = blocker
    record["terminal_state"] = "failed_no_charge"
    return _execution_result(
        ledger,
        record,
        ok=False,
        blocker=blocker,
        idempotent_replay=idempotent_replay,
    )


def execute_podcast_video_local(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: PodcastVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: PodcastVideoEngineLedger,
    output_root: str | Path,
    environ: Mapping[str, Any] | None,
    source_path: str,
    asset_paths: Mapping[str, str],
    final_asset_paths: Mapping[str, str] | None = None,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    public_request: bool = False,
    fixture_mode: bool = False,
) -> dict[str, Any]:
    fixture_enabled = _strict_bool(
        fixture_mode,
        "podcast_fixture_mode_invalid",
    )
    local_environ = dict(environ or {})
    if fixture_enabled:
        local_environ["PODCAST_VIDEO_RUNTIME_REGISTERED"] = "1"
    dispatched = dispatch_podcast_video(
        request,
        plan=plan,
        manifest=manifest,
        runtime_sha=runtime_sha,
        ledger=ledger,
        environ=local_environ,
        public_request=public_request,
    )
    if dispatched.get("blocker"):
        return dispatched
    record = ledger.records_by_job_id.get(_clean(dispatched.get("job_id")))
    if not isinstance(record, dict):
        return {**dispatched, "ok": False, "blocker": "podcast_job_not_found"}
    record["fixture_only"] = fixture_enabled
    artifact = Path(_clean(record.get("artifact_path")))
    if record.get("validation", {}).get("ok"):
        if (
            artifact.is_file()
            and artifact.stat().st_size == int(record.get("output_bytes") or 0)
            and _sha256_file(artifact) == record.get("artifact_sha256")
        ):
            return _execution_result(ledger, record, ok=True, idempotent_replay=True)
        return _fail_record(
            ledger,
            record,
            "podcast_artifact_changed_after_validation",
            idempotent_replay=True,
        )
    if record.get("render_attempted"):
        return _fail_record(
            ledger,
            record,
            _clean(record.get("blocker") or "podcast_render_not_retriable"),
            idempotent_replay=True,
        )
    record["render_attempted"] = True
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""
    if not ffmpeg:
        return _fail_record(ledger, record, "ffmpeg_missing")
    if not ffprobe:
        return _fail_record(ledger, record, "ffprobe_missing")
    selected_source = Path(_clean(source_path)).expanduser()
    if not selected_source.is_file() or selected_source.stat().st_size <= 0:
        return _fail_record(ledger, record, "podcast_source_artifact_required")
    if _sha256_file(selected_source) != plan.source_sha256:
        return _fail_record(ledger, record, "podcast_source_artifact_fingerprint_mismatch")
    try:
        source_probe = _probe_media(selected_source, ffprobe)
    except ValueError as exc:
        return _fail_record(ledger, record, _clean(exc))
    if source_probe["audio_stream_count"] < 1:
        return _fail_record(ledger, record, "podcast_source_audio_required")

    final_assets = dict(plan.final_assets or {})
    selected_logo = ""
    if final_assets.get("logo_enabled"):
        logo_id = _clean(final_assets.get("logo_asset_id"))
        logo_path = Path(
            _clean((final_asset_paths or {}).get(logo_id) or final_assets.get("logo_path"))
        )
        if not logo_path.is_file() or logo_path.stat().st_size <= 0:
            return _fail_record(ledger, record, "podcast_logo_asset_missing")
        if _sha256_file(logo_path) != _clean(final_assets.get("logo_sha256")):
            return _fail_record(ledger, record, "podcast_logo_asset_fingerprint_mismatch")
        selected_logo = str(logo_path.resolve())

    workspace = Path(output_root) / record["job_id"]
    scene_dir = workspace / "scenes"
    evidence_dir = workspace / "evidence"
    scene_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    record["evidence_dir"] = str(evidence_dir)
    source_speech_pcm = evidence_dir / "source_speech_pcm.wav"
    try:
        _extract_speech_pcm(
            input_path=selected_source,
            output_path=source_speech_pcm,
            stream_index=plan.source_audio_stream_index,
            ffmpeg=ffmpeg,
        )
    except (RuntimeError, ValueError) as exc:
        record["safe_error"] = type(exc).__name__
        return _fail_record(ledger, record, "podcast_source_speech_extract_failed")
    scene_clip_paths: dict[int, str] = {}
    pipeline_scenes: list[pipeline.SceneSpec] = []
    transcript_by_id = {
        str(item["segment_id"]): dict(item) for item in plan.transcript_segments
    }
    for scene in plan.scenes:
        selected = Path(_clean(asset_paths.get(scene.asset_id)))
        if not selected.is_file() or selected.stat().st_size <= 0:
            return _fail_record(ledger, record, "podcast_scene_asset_missing")
        if _sha256_file(selected) != scene.asset_sha256:
            return _fail_record(ledger, record, "podcast_scene_asset_fingerprint_mismatch")
        runtime_manifest, state = _scene_runtime_state(scene, plan)
        clip_path = scene_dir / f"scene_{scene.scene_index:03d}.mp4"
        try:
            command = frame_video_runtime.build_ffmpeg_command(
                [str(selected.resolve())],
                str(clip_path),
                state,
                ffmpeg_path=ffmpeg,
                min_images=1,
                continuous_still_motion=True,
            )
            completed = subprocess.run(
                command.command,
                capture_output=True,
                text=True,
                timeout=max(180, int(scene.duration_seconds * 60)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            record["safe_error"] = type(exc).__name__
            return _fail_record(ledger, record, "podcast_scene_render_failed")
        if completed.returncode != 0:
            record["safe_error"] = _clean(completed.stderr)[-500:]
            return _fail_record(ledger, record, "podcast_scene_render_failed")
        clip_probe = frame_video_runtime.probe_mp4(
            str(clip_path),
            command.expected_duration,
            expects_audio=False,
            ffprobe_path=ffprobe,
        )
        clip_motion = _motion_evidence(str(clip_path), ffmpeg)
        if not clip_probe.get("ok"):
            return _fail_record(
                ledger,
                record,
                _clean(clip_probe.get("reason") or "podcast_scene_invalid"),
            )
        if not clip_motion.get("ok"):
            return _fail_record(
                ledger,
                record,
                _clean(clip_motion.get("reason") or "podcast_motion_invalid"),
            )
        ledger.render_count += 1
        scene_clip_paths[scene.scene_index] = str(clip_path)
        scene_manifest = {
            **_scene_material(scene),
            "transcript_segments": [
                transcript_by_id[item] for item in scene.transcript_segment_ids
            ],
            "runtime_manifest": runtime_manifest,
            "visual_prompt_sha256": _sha256_text(scene.visual_prompt),
            "clip_path": str(clip_path),
            "clip_sha256": _sha256_file(clip_path),
            "clip_probe": clip_probe,
            "motion_evidence": clip_motion,
            "provider_calls": 0,
            "music_generation_calls": 0,
        }
        _write_json(
            evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json",
            scene_manifest,
        )
        narration = " ".join(
            _clean(transcript_by_id[item].get("text"))
            for item in scene.transcript_segment_ids
        )
        pipeline_scenes.append(
            pipeline.SceneSpec(
                scene_id=scene.scene_index,
                title=f"Podcast scene {scene.scene_index}",
                visual_prompt=scene.visual_prompt,
                video_prompt=(
                    f"{scene.visual_prompt}; motion={scene.motion}; "
                    f"source_audio_sha256={plan.source_sha256}"
                ),
                narration_text=narration,
                target_duration_sec=scene.duration_seconds,
                aspect_ratio=plan.aspect_ratio,
                transition="cut",
                seed_image_path=str(selected.resolve()),
                provider_params={
                    "provider": "local",
                    "source_fingerprint": plan.source_fingerprint,
                    "rights_receipt_id": scene.asset_rights_receipt_id,
                },
            )
        )

    width, height = _output_geometry(plan.aspect_ratio)
    try:
        with _selected_pipeline_ffmpeg(ffmpeg):
            composition = pipeline.finalize_multiscene_scene_clips(
                user_id=str(request.user_id),
                job_id=record["job_id"],
                workspace_dir=str(workspace / "composition"),
                scenes=pipeline_scenes,
                scene_clip_paths=scene_clip_paths,
                enable_voice=False,
                enable_subtitle=False,
                enable_logo=False,
                output_width=width,
                output_height=height,
                output_fps=24,
                transition_duration_sec=0.0,
                preserve_scene_audio=False,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        record["safe_error"] = type(exc).__name__
        return _fail_record(ledger, record, "podcast_composition_failed")
    if not composition.get("ok") or not _clean(composition.get("final_video_path")):
        record["composition"] = _json_safe(composition)
        return _fail_record(
            ledger,
            record,
            _clean(composition.get("error") or "podcast_composition_failed"),
        )
    expected_scene_order = [scene.scene_index for scene in plan.scenes]
    try:
        composition_scene_count = int(composition.get("scene_count") or 0)
        coverage_count = int(composition.get("scene_coverage_count") or 0)
        coverage_expected = int(composition.get("scene_coverage_expected") or 0)
    except (TypeError, ValueError):
        composition_scene_count = 0
        coverage_count = 0
        coverage_expected = 0
    composition_coverage_valid = bool(
        list(composition.get("scene_order") or ()) == expected_scene_order
        and composition_scene_count == len(expected_scene_order)
        and coverage_count == len(expected_scene_order)
        and coverage_expected == len(expected_scene_order)
        and _flag(composition.get("scene_coverage_valid_bool"))
        and not list(composition.get("missing_scene_indexes") or ())
        and _flag(composition.get("concat_output_valid"))
        and _flag(composition.get("final_mp4_valid"))
    )
    if not composition_coverage_valid:
        record["composition"] = _json_safe(composition)
        return _fail_record(
            ledger,
            record,
            "podcast_composition_scene_coverage_invalid",
        )
    ledger.compose_count += 1
    visual_master = Path(_clean(composition.get("final_video_path")))
    transcript_srt = _write_transcript_srt(
        plan,
        evidence_dir / "podcast_transcript.srt",
    )
    overlay_probe_timestamp = min(
        max(0.1, plan.expected_duration_seconds / 2.0),
        max(0.1, plan.expected_duration_seconds - 0.1),
    )
    waveform_master = visual_master
    waveform_applied = False
    waveform_visual_evidence = _unrequested_visual_evidence("bottom_center")
    if plan.waveform_enabled:
        waveform_path = workspace / "composition" / "waveform_master.mp4"
        try:
            _overlay_waveform(
                master_video_path=str(visual_master),
                source_path=str(source_speech_pcm),
                output_path=str(waveform_path),
                width=width,
                height=height,
                duration_seconds=plan.expected_duration_seconds,
                ffmpeg=ffmpeg,
            )
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            record["safe_error"] = type(exc).__name__
            return _fail_record(ledger, record, "podcast_waveform_render_failed")
        waveform_master = waveform_path
        waveform_applied = bool(
            waveform_path.is_file()
            and waveform_path.stat().st_size > 0
            and _sha256_file(waveform_path) != _sha256_file(visual_master)
        )
        waveform_visual_evidence = _overlay_visual_evidence(
            baseline_path=visual_master,
            output_path=waveform_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=overlay_probe_timestamp,
            width=width,
            height=height,
            position="bottom_center",
            width_ratio=0.96,
            height_ratio=0.38,
        )
        waveform_applied = bool(
            waveform_applied and waveform_visual_evidence.get("changed")
        )
    watermark_text = _clean(final_assets.get("watermark_text"))
    watermark_master = waveform_master
    watermark_applied = False
    watermark_position = _clean(
        final_assets.get("watermark_position") or "bottom_right"
    )
    watermark_visual_evidence = _unrequested_visual_evidence(watermark_position)
    if watermark_text:
        watermark_path = workspace / "composition" / "watermark_master.mp4"
        try:
            _overlay_watermark(
                master_video_path=str(waveform_master),
                output_path=str(watermark_path),
                text=watermark_text,
                position=watermark_position,
                duration_seconds=plan.expected_duration_seconds,
                ffmpeg=ffmpeg,
            )
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            blocker = _clean(exc) or "podcast_watermark_render_failed"
            return _fail_record(ledger, record, blocker)
        watermark_master = watermark_path
        watermark_applied = bool(
            watermark_path.is_file()
            and watermark_path.stat().st_size > 0
            and _sha256_file(watermark_path) != _sha256_file(waveform_master)
        )
        watermark_visual_evidence = _overlay_visual_evidence(
            baseline_path=waveform_master,
            output_path=watermark_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=overlay_probe_timestamp,
            width=width,
            height=height,
            position=watermark_position,
            width_ratio=0.55,
            height_ratio=0.38,
        )
        watermark_applied = bool(
            watermark_applied and watermark_visual_evidence.get("changed")
        )
    final_path = workspace / "composition" / "final_podcast.mp4"
    try:
        with _selected_pipeline_ffmpeg(ffmpeg):
            pipeline.mux_final_multiscene_video(
                master_video_path=str(watermark_master),
                output_path=str(final_path),
                voice_audio_path=str(source_speech_pcm),
                subtitle_path=transcript_srt if plan.captions_enabled else None,
                logo_path=selected_logo or None,
                logo_text=None,
                burn_subtitles=bool(plan.captions_enabled),
                logo_position=_clean(final_assets.get("logo_position") or "top_left"),
                watermark_position=watermark_position,
                preserve_master_audio=False,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        record["safe_error"] = type(exc).__name__
        return _fail_record(ledger, record, "podcast_final_mux_failed")
    final_probe = frame_video_runtime.probe_mp4(
        str(final_path),
        plan.expected_duration_seconds,
        expects_audio=True,
        ffprobe_path=ffprobe,
    )
    decode = _full_decode(str(final_path), ffmpeg)
    motion = _motion_evidence(str(final_path), ffmpeg)
    try:
        output_probe = _probe_media(final_path, ffprobe)
    except ValueError:
        output_probe = {
            "duration_seconds": 0.0,
            "audio_duration_seconds": 0.0,
            "audio_stream_count": 0,
            "video_stream_count": 0,
        }
    output_duration = float(output_probe.get("duration_seconds") or 0.0)
    output_audio_duration = float(output_probe.get("audio_duration_seconds") or 0.0)
    caption_position = _clean(final_assets.get("caption_position") or "bottom_center")
    caption_visual_evidence = _unrequested_visual_evidence(caption_position)
    if plan.captions_enabled:
        first_segment = dict(plan.transcript_segments[0])
        caption_timestamp = (
            float(first_segment.get("start_seconds") or 0.0)
            + float(first_segment.get("end_seconds") or 0.0)
        ) / 2.0
        caption_visual_evidence = _overlay_visual_evidence(
            baseline_path=watermark_master,
            output_path=final_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=caption_timestamp,
            width=width,
            height=height,
            position=caption_position,
            width_ratio=0.90,
            height_ratio=0.40,
        )
    logo_requested = bool(final_assets.get("logo_enabled"))
    logo_position = _clean(final_assets.get("logo_position") or "top_left")
    logo_visual_evidence = _unrequested_visual_evidence(logo_position)
    if logo_requested:
        logo_visual_evidence = _overlay_visual_evidence(
            baseline_path=watermark_master,
            output_path=final_path,
            ffmpeg=ffmpeg,
            timestamp_seconds=overlay_probe_timestamp,
            width=width,
            height=height,
            position=logo_position,
            width_ratio=0.40,
            height_ratio=0.40,
        )
    output_speech_pcm = evidence_dir / "output_speech_pcm.wav"
    speech_content_proof: dict[str, Any] = {
        "content_match": False,
        "similarity": 0.0,
        "source_pcm_sha256": "",
        "output_pcm_sha256": "",
        "source_feature_sha256": "",
        "output_feature_sha256": "",
    }
    output_audio_stream_index = int(output_probe.get("selected_audio_stream_index") or 0)
    if int(output_probe.get("audio_stream_count") or 0) > 0:
        try:
            _extract_speech_pcm(
                input_path=final_path,
                output_path=output_speech_pcm,
                stream_index=output_audio_stream_index,
                ffmpeg=ffmpeg,
            )
            speech_content_proof = compare_speech_pcm_content(
                source_speech_pcm,
                output_speech_pcm,
            )
        except (RuntimeError, ValueError, OSError):
            speech_content_proof = dict(speech_content_proof)
    duration_tolerance = max(0.18, plan.expected_duration_seconds * 0.03)
    speech_clipped = bool(
        output_duration < plan.source_duration_seconds - duration_tolerance
        or output_audio_duration < plan.source_duration_seconds - duration_tolerance
    )
    speech_audio_continuity = bool(
        int(output_probe.get("audio_stream_count") or 0) == 1
        and not speech_clipped
        and abs(output_duration - plan.source_duration_seconds) <= duration_tolerance
    )
    scene_coverage = bool(
        composition_coverage_valid
        and len(scene_clip_paths) == len(plan.scenes)
        and all(
            (evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json").is_file()
            for scene in plan.scenes
        )
    )
    covered_segments = [item for scene in plan.scenes for item in scene.transcript_segment_ids]
    transcript_coverage = bool(
        covered_segments == [str(item["segment_id"]) for item in plan.transcript_segments]
        and _sha256_text(_canonical_json(_coverage_material(plan)))
        == plan.transcript_coverage_sha256
    )
    captions_applied = bool(
        not plan.captions_enabled
        or (
            Path(transcript_srt).is_file()
            and Path(transcript_srt).stat().st_size > 0
            and caption_visual_evidence.get("changed")
        )
    )
    watermark_requested = bool(watermark_text)
    logo_applied = bool(
        not logo_requested
        or (
            selected_logo
            and final_path.is_file()
            and logo_visual_evidence.get("changed")
        )
    )
    watermark_applied = bool(
        not watermark_requested or (watermark_applied and final_path.is_file())
    )
    validation = {
        **final_probe,
        "ok": bool(
            final_probe.get("ok")
            and decode.get("ok")
            and motion.get("ok")
            and speech_audio_continuity
            and speech_content_proof.get("content_match")
            and scene_coverage
            and transcript_coverage
            and captions_applied
            and (not plan.waveform_enabled or waveform_applied)
            and logo_applied
            and watermark_applied
        ),
        "full_decode": bool(decode.get("ok")),
        "motion_valid": bool(motion.get("ok")),
        "audio_stream_count": int(output_probe.get("audio_stream_count") or 0),
        "video_stream_count": int(output_probe.get("video_stream_count") or 0),
        "output_duration_seconds": output_duration,
        "output_audio_duration_seconds": output_audio_duration,
        "source_duration_seconds": plan.source_duration_seconds,
        "source_audio_sha256": plan.source_sha256,
        "selected_source_audio_stream_index": plan.source_audio_stream_index,
        "selected_output_audio_stream_index": output_audio_stream_index,
        "speech_audio_continuity": speech_audio_continuity,
        "speech_content_match": bool(speech_content_proof.get("content_match")),
        "speech_content_similarity": float(
            speech_content_proof.get("similarity") or 0.0
        ),
        "source_speech_pcm_sha256": _clean(
            speech_content_proof.get("source_pcm_sha256")
        ),
        "output_speech_pcm_sha256": _clean(
            speech_content_proof.get("output_pcm_sha256")
        ),
        "source_speech_feature_sha256": _clean(
            speech_content_proof.get("source_feature_sha256")
        ),
        "output_speech_feature_sha256": _clean(
            speech_content_proof.get("output_feature_sha256")
        ),
        "speech_clipped": speech_clipped,
        "scene_coverage_complete": scene_coverage,
        "transcript_coverage_complete": transcript_coverage,
        "transcript_segment_count": len(plan.transcript_segments),
        "scene_count": len(plan.scenes),
        "scene_order": [scene.scene_index for scene in plan.scenes],
        "compositor_scene_order": list(composition.get("scene_order") or ()),
        "compositor_scene_coverage_valid": _flag(
            composition.get("scene_coverage_valid_bool")
        ),
        "scene_order_sha256": plan.scene_order_sha256,
        "transcript_sha256": plan.transcript_sha256,
        "transcript_coverage_sha256": plan.transcript_coverage_sha256,
        "captions_applied": captions_applied,
        "waveform_applied": waveform_applied if plan.waveform_enabled else False,
        "logo_applied": logo_applied if logo_requested else False,
        "watermark_applied": watermark_applied if watermark_requested else False,
        "caption_visual_evidence": caption_visual_evidence,
        "waveform_visual_evidence": waveform_visual_evidence,
        "logo_visual_evidence": logo_visual_evidence,
        "watermark_visual_evidence": watermark_visual_evidence,
        "active_speaker_accuracy_claimed": plan.active_speaker_accuracy_claimed,
        "provider_calls": 0,
        "music_generation_calls": 0,
        "compose_count": 1,
    }
    if not validation["ok"]:
        validation_blocker = _clean(
            (
                final_probe.get("reason")
                if not final_probe.get("ok")
                else ""
            )
            or decode.get("reason")
            or motion.get("reason")
            or ("podcast_speech_audio_discontinuity" if not speech_audio_continuity else "")
            or (
                "podcast_speech_content_mismatch"
                if not speech_content_proof.get("content_match")
                else ""
            )
            or ("podcast_scene_coverage_incomplete" if not scene_coverage else "")
            or ("podcast_transcript_coverage_incomplete" if not transcript_coverage else "")
            or ("podcast_captions_not_applied" if not captions_applied else "")
            or (
                "podcast_waveform_not_applied"
                if plan.waveform_enabled and not waveform_applied
                else ""
            )
            or ("podcast_logo_not_applied" if logo_requested and not logo_applied else "")
            or (
                "podcast_watermark_not_applied"
                if watermark_requested and not watermark_applied
                else ""
            )
            or "podcast_artifact_invalid"
        )
        validation["reason"] = validation_blocker
        record["validation"] = validation
        return _fail_record(
            ledger,
            record,
            validation_blocker,
        )
    validation["reason"] = ""
    source_manifest = {
        "source_id": plan.source_id,
        "source_type": plan.source_type,
        "source_fingerprint": plan.source_fingerprint,
        "source_sha256": plan.source_sha256,
        "source_bytes": plan.source_bytes,
        "source_rights_receipt_id": plan.source_rights_receipt_id,
        "source_duration_seconds": plan.source_duration_seconds,
        "source_audio_stream_count": plan.source_audio_stream_count,
        "source_audio_stream_index": plan.source_audio_stream_index,
        "source_speech_pcm_sha256": _clean(
            speech_content_proof.get("source_pcm_sha256")
        ),
        "source_speech_feature_sha256": _clean(
            speech_content_proof.get("source_feature_sha256")
        ),
        "transcriber": plan.transcriber,
        "transcript_sha256": plan.transcript_sha256,
        "speaker_count": plan.speaker_count,
        "diarization": plan.diarization,
        "active_speaker_accuracy_claimed": plan.active_speaker_accuracy_claimed,
    }
    _write_json(evidence_dir / "podcast_source_manifest.json", source_manifest)
    _write_json(
        evidence_dir / "job_manifest.json",
        {
            "job_id": record["job_id"],
            "route_id": ROUTE_ID,
            "plan": _plan_material(plan),
            "plan_sha256": plan.plan_sha256,
            "source_audio_sha256": plan.source_sha256,
            "scene_order_sha256": plan.scene_order_sha256,
            "transcript_coverage_sha256": plan.transcript_coverage_sha256,
            "final_assets": {
                key: value for key, value in final_assets.items() if key != "logo_path"
            },
            "provider_calls": 0,
            "music_generation_calls": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
        },
    )
    _write_json(evidence_dir / "validation_report.json", validation)
    record.update(
        {
            "artifact_path": str(final_path),
            "artifact_sha256": _sha256_file(final_path),
            "output_bytes": final_path.stat().st_size,
            "terminal_state": "rendered_validated",
            "blocker": "",
            "validation": validation,
            "composition": _json_safe(composition),
        }
    )
    return _execution_result(ledger, record, ok=True)


def _finalize_result(
    ledger: PodcastVideoEngineLedger,
    record: Mapping[str, Any],
    *,
    ok: bool,
    blocker: str = "",
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "blocker": blocker,
        "job_id": _clean(record.get("job_id")),
        "terminal_state": _clean(record.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "delivery": dict(record.get("delivery") or {}),
        "receipt": dict(record.get("receipt") or {}),
        "charge": dict(record.get("charge") or {}),
        "terminal_report": dict(record.get("terminal_report") or {}),
        **_ledger_counters(ledger),
    }


def finalize_podcast_video_fixture(
    *,
    ledger: PodcastVideoEngineLedger,
    job_id: str,
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    record = ledger.records_by_job_id.get(_clean(job_id))
    if not isinstance(record, dict):
        return {
            "ok": False,
            "blocker": "podcast_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    try:
        fixture_only = _strict_bool(
            record.get("fixture_only"),
            "podcast_fixture_finalizer_forbidden",
        )
    except ValueError:
        fixture_only = False
    if not fixture_only:
        record["terminal_state"] = "blocked_no_charge"
        record["blocker"] = "podcast_fixture_finalizer_forbidden"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="podcast_fixture_finalizer_forbidden",
        )
    request = record.get("request")
    request_payload = dict(
        request.payload
        if isinstance(request, video_engine_contract.VideoEngineRequest)
        else {}
    )
    try:
        admin_no_charge = _strict_bool(
            record.get("admin_no_charge", request_payload.get("admin_no_charge")),
            "podcast_fixture_admin_no_charge_required",
        )
    except ValueError:
        admin_no_charge = False
    if not admin_no_charge:
        record["terminal_state"] = "blocked_no_charge"
        record["blocker"] = "podcast_fixture_admin_no_charge_required"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="podcast_fixture_admin_no_charge_required",
        )
    existing_charge = dict(record.get("charge") or {})
    try:
        existing_amount = int(existing_charge.get("amount_xu") or 0)
    except (TypeError, ValueError):
        existing_amount = -1
    if existing_charge and (
        _flag(existing_charge.get("wallet_mutated")) or existing_amount != 0
    ):
        record["terminal_state"] = "blocked_no_charge"
        record["blocker"] = "podcast_fixture_wallet_forbidden"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="podcast_fixture_wallet_forbidden",
        )
    if record.get("terminal_report", {}).get("emitted"):
        return _finalize_result(ledger, record, ok=True, idempotent_replay=True)
    if not record.get("validation", {}).get("ok"):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "podcast_artifact_not_validated"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="podcast_artifact_not_validated",
        )
    artifact = Path(_clean(record.get("artifact_path")))
    artifact_sha = _clean(record.get("artifact_sha256"))
    output_bytes = int(record.get("output_bytes") or 0)
    if (
        not artifact.is_file()
        or artifact.stat().st_size != output_bytes
        or _sha256_file(artifact) != artifact_sha
    ):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "podcast_artifact_changed_after_validation"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="podcast_artifact_changed_after_validation",
        )
    evidence_dir = Path(_clean(record.get("evidence_dir")))

    if not record.get("delivery", {}).get("accepted"):
        if record.get("delivery_attempted"):
            return _finalize_result(ledger, record, ok=False, blocker="delivery_not_accepted")
        record["delivery_attempted"] = True
        ledger.delivery_count += 1
        try:
            delivery = dict(
                deliverer(
                    {
                        "job_id": record["job_id"],
                        "artifact_path": str(artifact),
                        "artifact_sha256": artifact_sha,
                        "output_bytes": output_bytes,
                        "idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            delivery = {}
        if delivery.get("production"):
            ledger.production_telegram_deliveries += 1
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "production_telegram_delivery_forbidden"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="production_telegram_delivery_forbidden",
            )
        if not delivery.get("accepted") or not _clean(delivery.get("message_id")):
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "delivery_not_accepted"
            return _finalize_result(ledger, record, ok=False, blocker="delivery_not_accepted")
        record["delivery"] = delivery

    if not record.get("receipt", {}).get("persisted"):
        if record.get("receipt_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_not_persisted",
            )
        record["receipt_attempted"] = True
        ledger.receipt_count += 1
        receipt_seed = {
            "job_id": record["job_id"],
            "delivered": True,
            "delivery_idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
            "delivery_message_id": _clean(record["delivery"].get("message_id")),
            "output_sha256": artifact_sha,
            "output_bytes": output_bytes,
            "delivered_at": str(time.time()),
        }
        try:
            persisted = dict(receipt_persister(receipt_seed) or {})
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            persisted = {}
        receipt = video_engine_contract.VideoDeliveryReceipt(
            **receipt_seed,
            receipt_id=_clean(persisted.get("receipt_id")),
        )
        if not persisted.get("persisted") or not receipt.valid:
            record["receipt"] = {**receipt_seed, **persisted, "persisted": False}
            record["blocker"] = "delivery_receipt_not_persisted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_not_persisted",
            )
        record["receipt"] = {**asdict(receipt), **persisted, "persisted": True}
        if _clean(record.get("evidence_dir")):
            _write_json(evidence_dir / "delivery_receipt.json", record["receipt"])

    if not record.get("charge", {}).get("recorded"):
        record["charge"] = {
            "recorded": True,
            "amount_xu": 0,
            "wallet_mutated": False,
            "fixture_only": True,
        }

    if not record.get("terminal_report", {}).get("emitted"):
        if record.get("terminal_report_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
            )
        record["terminal_report_attempted"] = True
        ledger.terminal_report_count += 1
        try:
            report = dict(
                terminal_reporter(
                    {
                        "job_id": record["job_id"],
                        "artifact_sha256": artifact_sha,
                        "delivery_message_id": _clean(record["delivery"].get("message_id")),
                        "receipt_id": _clean(record["receipt"].get("receipt_id")),
                        "amount_xu": int(record["charge"].get("amount_xu") or 0),
                        "idempotency_key": f"report:{record['job_id']}:{artifact_sha}",
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            report = {}
        if not report.get("emitted"):
            record["terminal_report"] = {**report, "emitted": False}
            record["blocker"] = "terminal_report_not_emitted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
            )
        record["terminal_report"] = {**report, "emitted": True}
        record["terminal_state"] = "final_delivered"
        record["blocker"] = ""
        if _clean(record.get("evidence_dir")):
            _write_json(evidence_dir / "terminal_report.json", record["terminal_report"])
    return _finalize_result(ledger, record, ok=True)


def finalize_podcast_video(
    *,
    ledger: PodcastVideoEngineLedger,
    job_id: str,
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    charger: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    del deliverer, receipt_persister, charger, terminal_reporter
    record = ledger.records_by_job_id.get(_clean(job_id))
    if not isinstance(record, dict):
        return {
            "ok": False,
            "blocker": "podcast_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    record["terminal_state"] = "blocked_no_charge"
    record["blocker"] = "podcast_production_finalizer_missing"
    return _finalize_result(
        ledger,
        record,
        ok=False,
        blocker="podcast_production_finalizer_missing",
    )
