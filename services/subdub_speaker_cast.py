"""Fail-closed speaker cue sidecars for SubDub automatic casting."""

from __future__ import annotations

from array import array
from collections.abc import Mapping
import hashlib
import hmac
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from services import subdub_canonical_cues


AUTO_CAST_UNAVAILABLE = "AUTO_CAST_UNAVAILABLE"
AUTO_CAST_MANUAL_REQUIRED = "AUTO_CAST_MANUAL_REQUIRED"
SIDECAR_VERSION = 1
MAX_SIDECAR_CUES = 20_000
MAX_SIDECAR_BYTES = 4 * 1024 * 1024
SIDECAR_FILENAME = "speaker_cast.sidecar.json"
MAX_SPEAKER_LABELS = 16

PCM_SAMPLE_RATE = 16_000
PCM_WINDOW_SAMPLES = 8_000
PCM_WINDOW_BYTES = PCM_WINDOW_SAMPLES * 2
MAX_AUTO_SPEAKER_LABELS = 16
MAX_SPEAKER_VOICED_SECONDS = 3.0
MAX_JOB_SAMPLE_SECONDS = 48.0
MAX_WORK_BUFFER_BYTES = 1_048_576
CLASSIFIER_WALL_TIMEOUT_SECONDS = 30.0
LOW_MAX_HZ = 155.0
HIGH_MIN_HZ = 165.0
MIN_REGISTER_CONFIDENCE = 0.75

_PCM_BYTES_PER_SAMPLE = 2
_PCM_WINDOW_SECONDS = PCM_WINDOW_SAMPLES / PCM_SAMPLE_RATE
_MIN_VOICED_SECONDS = 1.0
_MIN_WINDOW_RMS = 0.01
_MIN_PITCH_HZ = 70.0
_MAX_PITCH_HZ = 300.0
_AUTOCORRELATION_STRIDE = 4
_MAX_RELATIVE_PITCH_SPREAD = 0.18
_MIN_REGISTER_VOTE_RATIO = 2.0 / 3.0
_MIN_REGISTER_TOTAL_RATIO = 0.50
_STRONG_SINGLE_WINDOW_MIN_CONFIDENCE = MIN_REGISTER_CONFIDENCE
_STRONG_SINGLE_WINDOW_LOW_MAX_HZ = 145.0
_STRONG_SINGLE_WINDOW_HIGH_MIN_HZ = HIGH_MIN_HZ
_PITCH_ANALYSIS_DECIMATION = 8
_PITCH_ANALYSIS_SAMPLE_RATE = PCM_SAMPLE_RATE // _PITCH_ANALYSIS_DECIMATION
_PITCH_FRAME_SAMPLES = 400
_PITCH_FRAME_HOP_SAMPLES = 200
_PITCH_DIFFERENCE_STRIDE = 1
_PITCH_YIN_THRESHOLD = 0.24
_PITCH_YIN_MAXIMUM = 0.32
_MIN_PITCH_FRAME_CONFIDENCE = 0.68
_MIN_PITCH_FRAMES = 1
_MAX_FRAME_RELATIVE_PITCH_DEVIATION = 0.22
_MAX_HARMONIC_PURITY_COMPONENTS = 4
_MAX_HARMONIC_PURITY_HZ = 900.0
_MIN_HARMONIC_SERIES_PURITY = 0.02
_MIN_FUNDAMENTAL_HARMONIC_SHARE = 0.03
_MAX_COMPETING_PITCH_RATIO = 0.0075
_COMPETING_FFT_SIZE = 512
_HARMONIC_EXCLUSION_HZ = 15.0
_COMPETING_PITCH_STABILITY_HZ = 8.0
_MIN_COMPETING_PITCH_FRAMES = 2
_STABILITY_CONFIDENCE_SLOPE = 5.0 / 3.0

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SPEAKER_ID_RE = re.compile(r"^chunk_(\d+):speaker_(\d+)$")
_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SIDECAR_METADATA_FIELDS = (
    "speaker",
    "speaker_confidence",
    "speaker_id",
    "chunk_index",
    "voice_register",
    "tts_voice_id",
)


class AutoCastUnavailable(RuntimeError):
    """Raised when automatic casting cannot prove cue/sidecar identity."""

    def __init__(self, message: str = AUTO_CAST_UNAVAILABLE) -> None:
        super().__init__(str(message or AUTO_CAST_UNAVAILABLE))


class AutoCastManualRequired(RuntimeError):
    """Raised when bounded local evidence cannot support automatic casting."""

    def __init__(self) -> None:
        super().__init__(AUTO_CAST_MANUAL_REQUIRED)


def _validated_voice_pools(
    validated_pools: Mapping[str, object],
) -> dict[str, list[str]]:
    if not isinstance(validated_pools, Mapping):
        raise AutoCastManualRequired()
    if set(validated_pools) != {"low", "high"}:
        raise AutoCastManualRequired()

    normalized: dict[str, list[str]] = {}
    all_voice_ids: set[str] = set()
    for register in ("low", "high"):
        raw_pool = validated_pools.get(register)
        if not isinstance(raw_pool, (list, tuple)) or not raw_pool:
            raise AutoCastManualRequired()
        pool: list[str] = []
        for raw_voice_id in raw_pool:
            if type(raw_voice_id) is not str:
                raise AutoCastManualRequired()
            voice_id = raw_voice_id.strip()
            if voice_id != raw_voice_id or _VOICE_ID_RE.fullmatch(voice_id) is None:
                raise AutoCastManualRequired()
            if voice_id in all_voice_ids:
                raise AutoCastManualRequired()
            all_voice_ids.add(voice_id)
            pool.append(voice_id)
        normalized[register] = sorted(pool)
    return normalized


def assign_stable_voices(
    classifications: dict[str, dict],
    *,
    speaker_order: list[str],
    validated_pools: dict[str, list[str]],
    assignment_seed: str,
) -> dict[str, dict]:
    """Assign distinct provider-neutral voice IDs in canonical cue order."""

    if not isinstance(classifications, Mapping) or not classifications:
        raise AutoCastManualRequired()
    if not isinstance(speaker_order, (list, tuple)) or not speaker_order:
        raise AutoCastManualRequired()
    ordered_speakers = list(speaker_order)
    if (
        len(ordered_speakers) > MAX_AUTO_SPEAKER_LABELS
        or len(set(ordered_speakers)) != len(ordered_speakers)
        or set(ordered_speakers) != set(classifications)
    ):
        raise AutoCastManualRequired()
    seed = _normalized_sha256(assignment_seed)
    if not seed:
        raise AutoCastManualRequired()
    pools = _validated_voice_pools(validated_pools)

    register_counts = {"low": 0, "high": 0}
    normalized_classifications: dict[str, tuple[str, float]] = {}
    for speaker_id in ordered_speakers:
        try:
            validated_speaker_identity({"speaker_id": speaker_id})
        except AutoCastUnavailable as exc:
            raise AutoCastManualRequired() from exc
        item = classifications.get(speaker_id)
        if not isinstance(item, Mapping):
            raise AutoCastManualRequired()
        item_speaker_id = item.get("speaker_id")
        if item_speaker_id not in (None, speaker_id):
            raise AutoCastManualRequired()
        register = item.get("voice_register")
        confidence_value = item.get("confidence")
        if register not in register_counts or isinstance(confidence_value, bool):
            raise AutoCastManualRequired()
        try:
            confidence = float(confidence_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AutoCastManualRequired() from exc
        if not math.isfinite(confidence) or confidence < MIN_REGISTER_CONFIDENCE:
            raise AutoCastManualRequired()
        normalized_classifications[speaker_id] = (str(register), confidence)
        register_counts[str(register)] += 1

    if any(register_counts[register] > len(pools[register]) for register in register_counts):
        raise AutoCastManualRequired()

    result: dict[str, dict] = {}
    used: dict[str, set[str]] = {"low": set(), "high": set()}
    for speaker_id in ordered_speakers:
        register, _confidence = normalized_classifications[speaker_id]
        available = [
            voice_id
            for voice_id in pools[register]
            if voice_id not in used[register]
        ]
        if not available:
            raise AutoCastManualRequired()
        digest = hashlib.sha256(
            f"{seed}:{speaker_id}:{register}".encode("utf-8", errors="strict")
        ).digest()
        voice_id = available[int.from_bytes(digest[:8], "big") % len(available)]
        used[register].add(voice_id)
        result[speaker_id] = {
            "speaker_id": speaker_id,
            "voice_register": register,
            "voice_id": voice_id,
        }
    return result


def pitch_register(median_hz: float, *, confidence: float) -> str:
    """Map a confident acoustic pitch estimate to the approved register labels."""

    try:
        normalized_hz = float(median_hz)
        normalized_confidence = float(confidence)
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if (
        not math.isfinite(normalized_hz)
        or not math.isfinite(normalized_confidence)
        or normalized_confidence < MIN_REGISTER_CONFIDENCE
    ):
        return "unknown"
    if normalized_hz <= LOW_MAX_HZ:
        return "low"
    if normalized_hz >= HIGH_MIN_HZ:
        return "high"
    return "unknown"


def valid_speaker_index(value: Any) -> bool:
    return type(value) is int and 0 <= value < MAX_SPEAKER_LABELS


def normalized_speaker_key(chunk_index: int, speaker: int) -> str:
    if type(chunk_index) is not int or chunk_index < 0:
        raise AutoCastUnavailable()
    if not valid_speaker_index(speaker):
        raise AutoCastUnavailable()
    try:
        speaker_id = f"chunk_{chunk_index:02d}:speaker_{speaker}"
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(speaker_id) > 128:
        raise AutoCastUnavailable()
    return speaker_id


def _normalized_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _bounded_text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[: max(0, int(maximum))]


def _finite_confidence(value: Any) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    if not math.isfinite(confidence):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _optional_nonnegative_int(item: dict, field: str) -> int | None:
    if field not in item:
        return None
    value = item.get(field)
    if type(value) is not int or value < 0:
        raise AutoCastUnavailable()
    return value


def validated_speaker_identity(item: dict) -> tuple[int, int, str]:
    if not isinstance(item, dict):
        raise AutoCastUnavailable()
    speaker = _optional_nonnegative_int(item, "speaker")
    chunk_index = _optional_nonnegative_int(item, "chunk_index")
    speaker_id = str(item.get("speaker_id") or "").strip()
    match = _SPEAKER_ID_RE.fullmatch(speaker_id)
    if len(speaker_id) > 128 or match is None:
        raise AutoCastUnavailable()
    try:
        identity_chunk = int(match.group(1))
        identity_speaker = int(match.group(2))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if (
        speaker_id != normalized_speaker_key(identity_chunk, identity_speaker)
        or (speaker is not None and speaker != identity_speaker)
        or (chunk_index is not None and chunk_index != identity_chunk)
    ):
        raise AutoCastUnavailable()
    return identity_chunk, identity_speaker, speaker_id


def _canonical_cues(cues: Iterable[dict]) -> list[dict]:
    source = [dict(item or {}) for item in (cues or [])]
    if len(source) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    prepared: list[dict] = []
    for position, item in enumerate(source, start=1):
        current = dict(item)
        if current.get("source_start_ms") is None and current.get("start_ms") is not None:
            current["source_start_ms"] = current.get("start_ms")
        if current.get("source_end_ms") is None and current.get("end_ms") is not None:
            current["source_end_ms"] = current.get("end_ms")
        if not str(current.get("source_text") or current.get("text") or "").strip():
            current["text"] = f"__speaker_cue_{position:06d}__"
        prepared.append(current)
    try:
        canonical = subdub_canonical_cues.canonicalize_segments(
            prepared,
            extraction_source="speaker_sidecar",
            source_language="auto",
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(canonical) != len(source):
        raise AutoCastUnavailable()
    output: list[dict] = []
    for original, normalized in zip(source, canonical):
        output.append(
            {
                **original,
                "cue_id": str(normalized.get("cue_id") or "").strip(),
                "start_ms": int(normalized.get("source_start_ms") or 0),
                "end_ms": int(normalized.get("source_end_ms") or 0),
            }
        )
    return output


def _timeline_rows(cues: Iterable[dict]) -> list[tuple[str, int, int]]:
    canonical = _canonical_cues(cues)
    rows = [
        (
            str(item.get("cue_id") or "").strip(),
            int(item.get("start_ms") or 0),
            int(item.get("end_ms") or 0),
        )
        for item in canonical
    ]
    cue_ids = [row[0] for row in rows]
    if any(not cue_id for cue_id in cue_ids) or len(set(cue_ids)) != len(cue_ids):
        raise AutoCastUnavailable()
    return rows


def _signature_for_rows(rows: Iterable[tuple[str, int, int]]) -> str:
    serialized = "\n".join(f"{cue_id}:{start_ms}:{end_ms}" for cue_id, start_ms, end_ms in rows)
    return hashlib.sha256(serialized.encode("utf-8", errors="strict")).hexdigest()


def cue_timeline_signature(cues: list[dict]) -> str:
    return _signature_for_rows(_timeline_rows(cues))


def build_sidecar(
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> dict:
    media_hash = _normalized_sha256(media_sha256)
    subtitle_hash = _normalized_sha256(subtitle_sha256)
    if not media_hash or not subtitle_hash:
        raise ValueError("sidecar_sha256_invalid")
    canonical = _canonical_cues(cues)
    rows = _timeline_rows(canonical)
    entries: list[dict] = []
    for item, (cue_id, start_ms, end_ms) in zip(canonical, rows):
        identity_chunk, identity_speaker, speaker_id = validated_speaker_identity(item)
        speaker = identity_speaker if "speaker" in item else None
        chunk_index = identity_chunk if "chunk_index" in item else None
        entry: dict[str, Any] = {
            "cue_id": cue_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "speaker_id": speaker_id,
            "speaker_confidence": _finite_confidence(item.get("speaker_confidence")),
        }
        if speaker is not None:
            entry["speaker"] = speaker
        if chunk_index is not None:
            entry["chunk_index"] = chunk_index
        if "voice_register" in item:
            entry["voice_register"] = _bounded_text(item.get("voice_register"), 32)
        if "tts_voice_id" in item:
            entry["tts_voice_id"] = _bounded_text(item.get("tts_voice_id"), 256)
        entries.append(entry)
    return {
        "version": SIDECAR_VERSION,
        "media_sha256": media_hash,
        "subtitle_sha256": subtitle_hash,
        "timeline_signature": _signature_for_rows(rows),
        "cues": entries,
    }


def _sidecar_rows(sidecar: dict) -> list[tuple[str, int, int]]:
    entries = sidecar.get("cues")
    if not isinstance(entries, list) or len(entries) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    rows: list[tuple[str, int, int]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise AutoCastUnavailable()
        cue_id = raw.get("cue_id")
        start_ms = raw.get("start_ms")
        end_ms = raw.get("end_ms")
        numeric_confidence = raw.get("speaker_confidence")
        if (
            type(cue_id) is not str
            or not cue_id
            or cue_id != cue_id.strip()
            or type(start_ms) is not int
            or type(end_ms) is not int
            or type(numeric_confidence) is not float
        ):
            raise AutoCastUnavailable()
        validated_speaker_identity(raw)
        if (
            start_ms < 0
            or end_ms <= start_ms
            or not math.isfinite(numeric_confidence)
            or not 0.0 <= numeric_confidence <= 1.0
        ):
            raise AutoCastUnavailable()
        rows.append((cue_id, start_ms, end_ms))
    cue_ids = [row[0] for row in rows]
    if len(cue_ids) != len(set(cue_ids)):
        raise AutoCastUnavailable()
    return rows


def sidecar_matches(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> bool:
    try:
        if not isinstance(sidecar, dict):
            return False
        if type(sidecar.get("version")) is not int or sidecar.get("version") != SIDECAR_VERSION:
            return False
        media_hash = _normalized_sha256(media_sha256)
        subtitle_hash = _normalized_sha256(subtitle_sha256)
        if not media_hash or not subtitle_hash:
            return False
        if _normalized_sha256(sidecar.get("media_sha256")) != media_hash:
            return False
        if _normalized_sha256(sidecar.get("subtitle_sha256")) != subtitle_hash:
            return False
        expected_rows = _timeline_rows(cues)
        stored_rows = _sidecar_rows(sidecar)
        if stored_rows != expected_rows:
            return False
        signature = _signature_for_rows(expected_rows)
        return bool(
            _normalized_sha256(sidecar.get("timeline_signature")) == signature
            and len(stored_rows) == len(expected_rows)
        )
    except (AutoCastUnavailable, TypeError, ValueError, OverflowError):
        return False


def restore_cached_cue_ids_from_sidecar(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> list[dict]:
    """Restore canonical cue IDs lost by SRT serialization, fail closed."""

    try:
        if (
            not isinstance(sidecar, dict)
            or type(sidecar.get("version")) is not int
            or sidecar.get("version") != SIDECAR_VERSION
        ):
            raise AutoCastUnavailable()
        media_hash = _normalized_sha256(media_sha256)
        subtitle_hash = _normalized_sha256(subtitle_sha256)
        if (
            not media_hash
            or not subtitle_hash
            or _normalized_sha256(sidecar.get("media_sha256")) != media_hash
            or _normalized_sha256(sidecar.get("subtitle_sha256")) != subtitle_hash
        ):
            raise AutoCastUnavailable()
        source = _canonical_cues(cues)
        source_rows = _timeline_rows(source)
        stored_rows = _sidecar_rows(sidecar)
        if len(source_rows) != len(stored_rows):
            raise AutoCastUnavailable()
        restored: list[dict] = []
        for cue, source_row, stored_row in zip(source, source_rows, stored_rows):
            stored_cue_id, stored_start_ms, stored_end_ms = stored_row
            if source_row[1:] != (stored_start_ms, stored_end_ms):
                raise AutoCastUnavailable()
            restored.append({**cue, "cue_id": stored_cue_id})
        return restored
    except AutoCastUnavailable:
        raise
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc


def join_sidecar(sidecar: dict, cues: list[dict]) -> list[dict]:
    if (
        not isinstance(sidecar, dict)
        or type(sidecar.get("version")) is not int
        or sidecar.get("version") != SIDECAR_VERSION
    ):
        raise AutoCastUnavailable()
    source = _canonical_cues(cues)
    source_rows = _timeline_rows(source)
    stored_rows = _sidecar_rows(sidecar)
    if len(stored_rows) != len(source_rows):
        raise AutoCastUnavailable()
    entries = list(sidecar.get("cues") or [])
    by_cue_id = {str(item.get("cue_id")): dict(item) for item in entries}
    joined: list[dict] = []
    for cue, (cue_id, start_ms, end_ms) in zip(source, source_rows):
        entry = by_cue_id.get(cue_id)
        if (
            not entry
            or int(entry.get("start_ms")) != start_ms
            or int(entry.get("end_ms")) != end_ms
        ):
            raise AutoCastUnavailable()
        metadata = {
            key: entry[key]
            for key in _SIDECAR_METADATA_FIELDS
            if key in entry
        }
        joined.append({**cue, **metadata})
    return joined


def require_matching_sidecar(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> list[dict]:
    if not sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    ):
        raise AutoCastUnavailable()
    return join_sidecar(sidecar, cues)


def _workspace_file(workspace: str, path: str | os.PathLike[str]) -> Path:
    if not str(workspace or "").strip() or not str(path or "").strip():
        raise AutoCastUnavailable()
    root = Path(str(workspace or "")).expanduser().resolve(strict=False)
    target = Path(path).expanduser().resolve(strict=False)
    try:
        contained = os.path.commonpath((str(root), str(target))) == str(root)
    except ValueError as exc:
        raise AutoCastUnavailable() from exc
    if not root.is_dir() or not contained or target == root:
        raise AutoCastUnavailable()
    return target


def persist_sidecar(sidecar: dict, *, workspace: str) -> dict[str, str]:
    if not isinstance(sidecar, dict) or sidecar.get("version") != SIDECAR_VERSION:
        raise AutoCastUnavailable()
    entries = sidecar.get("cues")
    if not isinstance(entries, list) or len(entries) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    if not str(workspace or "").strip():
        raise AutoCastUnavailable()
    root = Path(str(workspace or "")).expanduser().resolve(strict=False)
    target = _workspace_file(str(root), root / SIDECAR_FILENAME)
    try:
        payload = json.dumps(
            sidecar,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(payload) > MAX_SIDECAR_BYTES:
        raise AutoCastUnavailable()
    temporary = target.with_name(f"{target.name}.tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AutoCastUnavailable() from exc
    return {
        "path": str(target),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def load_sidecar(
    path: str,
    *,
    expected_sha256: str,
    workspace: str,
) -> dict:
    expected_hash = _normalized_sha256(expected_sha256)
    if not expected_hash:
        raise AutoCastUnavailable()
    target = _workspace_file(workspace, path)
    try:
        size = target.stat().st_size
        if size <= 0 or size > MAX_SIDECAR_BYTES:
            raise AutoCastUnavailable()
        with open(target, "rb") as handle:
            payload = handle.read(MAX_SIDECAR_BYTES + 1)
    except AutoCastUnavailable:
        raise
    except OSError as exc:
        raise AutoCastUnavailable() from exc
    if len(payload) != size or len(payload) > MAX_SIDECAR_BYTES:
        raise AutoCastUnavailable()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise AutoCastUnavailable()
    try:
        sidecar = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise AutoCastUnavailable() from exc
    if (
        not isinstance(sidecar, dict)
        or sidecar.get("version") != SIDECAR_VERSION
        or not isinstance(sidecar.get("cues"), list)
        or len(sidecar.get("cues") or []) > MAX_SIDECAR_CUES
    ):
        raise AutoCastUnavailable()
    return sidecar


def ordered_auto_speaker_labels(cues: Iterable[dict]) -> list[str]:
    """Return distinct canonical labels in first-cue order, failing at label 17."""

    if isinstance(cues, (str, bytes, bytearray, dict)):
        raise AutoCastUnavailable()
    labels: list[str] = []
    seen: set[str] = set()
    for raw in cues or []:
        if not isinstance(raw, dict):
            raise AutoCastUnavailable()
        _chunk_index, _speaker, speaker_id = validated_speaker_identity(raw)
        if speaker_id in seen:
            continue
        if len(labels) >= MAX_AUTO_SPEAKER_LABELS:
            raise AutoCastManualRequired()
        seen.add(speaker_id)
        labels.append(speaker_id)
    return labels


def _ensure_classifier_active(
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> None:
    try:
        stopped = bool(stop_requested())
        expired = time.monotonic() >= deadline_monotonic
    except Exception as exc:
        raise AutoCastManualRequired() from exc
    if stopped or expired:
        raise AutoCastManualRequired()


def _bounded_median(values: list[float]) -> float:
    if not values:
        raise AutoCastManualRequired()
    ordered = sorted(float(value) for value in values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _speaker_window_offsets(
    ranges: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    max_windows: int,
) -> list[int]:
    if (
        not isinstance(ranges, (list, tuple))
        or len(ranges) > MAX_SIDECAR_CUES
        or type(max_windows) is not int
        or max_windows < 1
    ):
        raise AutoCastManualRequired()
    offsets: list[int] = []
    pending_start: float | None = None
    pending_end: float | None = None
    previous_start = -1.0

    def consume_interval(start: float, end: float) -> None:
        duration = end - start
        available = duration - _PCM_WINDOW_SECONDS
        if available < -1e-12 or len(offsets) >= max_windows:
            return
        candidate_count = min(
            int(MAX_SPEAKER_VOICED_SECONDS / _PCM_WINDOW_SECONDS),
            max(1, int(math.floor((duration + 1e-12) / _PCM_WINDOW_SECONDS))),
            max_windows - len(offsets),
        )
        for candidate_index in range(candidate_count):
            _ensure_classifier_active(deadline_monotonic, stop_requested)
            fraction = (candidate_index + 1) / (candidate_count + 1)
            cursor = start + max(0.0, available) * fraction
            offsets.append(int(round(cursor * PCM_SAMPLE_RATE)) * _PCM_BYTES_PER_SAMPLE)

    for position, raw_range in enumerate(ranges):
        if position % 64 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise AutoCastManualRequired()
        try:
            start = float(raw_range[0])
            end = float(raw_range[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise AutoCastManualRequired() from exc
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            raise AutoCastManualRequired()
        previous_start = start
        if pending_start is None:
            pending_start, pending_end = start, end
            continue
        assert pending_end is not None
        if start <= pending_end + 1e-12:
            pending_end = max(pending_end, end)
            continue
        consume_interval(pending_start, pending_end)
        if len(offsets) >= max_windows:
            break
        pending_start, pending_end = start, end

    if (
        len(offsets) < max_windows
        and pending_start is not None
        and pending_end is not None
    ):
        consume_interval(pending_start, pending_end)
    return offsets


def _stable_register_evidence(
    frequencies: list[float],
    confidences: list[float],
) -> tuple[str, float, float, int]:
    if len(frequencies) != len(confidences) or not frequencies:
        raise AutoCastManualRequired()
    if len(frequencies) == 1:
        try:
            frequency = float(frequencies[0])
            confidence = float(confidences[0])
        except (TypeError, ValueError, OverflowError) as exc:
            raise AutoCastManualRequired() from exc
        if (
            not math.isfinite(frequency)
            or not math.isfinite(confidence)
            or not _STRONG_SINGLE_WINDOW_MIN_CONFIDENCE <= confidence <= 1.0
        ):
            raise AutoCastManualRequired()
        if frequency <= _STRONG_SINGLE_WINDOW_LOW_MAX_HZ:
            register = "low"
        elif frequency >= _STRONG_SINGLE_WINDOW_HIGH_MIN_HZ:
            register = "high"
        else:
            raise AutoCastManualRequired()
        return register, frequency, confidence, 1
    groups: dict[str, list[tuple[float, float]]] = {"low": [], "high": []}
    for frequency, confidence in zip(frequencies, confidences):
        register = pitch_register(frequency, confidence=confidence)
        if register in groups:
            groups[register].append((frequency, confidence))
    known_count = sum(len(items) for items in groups.values())
    ranked = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
    register, evidence = ranked[0]
    runner_up_count = len(ranked[1][1])
    if (
        len(evidence) < 2
        or len(evidence) == runner_up_count
        or known_count < 2
        or len(evidence) / known_count < _MIN_REGISTER_VOTE_RATIO
        or len(evidence) / len(frequencies) < _MIN_REGISTER_TOTAL_RATIO
    ):
        raise AutoCastManualRequired()

    initial_median = _bounded_median([item[0] for item in evidence])
    inliers = [
        item
        for item in evidence
        if abs(item[0] - initial_median) / initial_median
        <= _MAX_RELATIVE_PITCH_SPREAD
    ]
    if len(inliers) < 2:
        raise AutoCastManualRequired()
    median_hz = _bounded_median([item[0] for item in inliers])
    relative_spread = _bounded_median(
        [abs(item[0] - median_hz) / median_hz for item in inliers]
    )
    if (
        not math.isfinite(relative_spread)
        or relative_spread > _MAX_RELATIVE_PITCH_SPREAD
    ):
        raise AutoCastManualRequired()
    stability_confidence = max(
        0.0,
        1.0 - (_STABILITY_CONFIDENCE_SLOPE * relative_spread),
    )
    confidence = min(
        _bounded_median([item[1] for item in inliers]),
        stability_confidence,
    )
    if pitch_register(median_hz, confidence=confidence) != register:
        raise AutoCastManualRequired()
    return register, median_hz, confidence, len(inliers)


def _estimate_frame_pitch_yin(
    frame: array,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float] | None:
    """Estimate one short voiced frame without assuming a stationary pure tone."""

    frame_length = len(frame)
    if frame_length != _PITCH_FRAME_SAMPLES:
        return None
    total = 0.0
    for index, sample in enumerate(frame):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        total += float(sample)
    mean = total / frame_length
    centered = array("f")
    energy = 0.0
    try:
        for index, sample in enumerate(frame):
            if index % 256 == 0:
                _ensure_classifier_active(deadline_monotonic, stop_requested)
            value = float(sample) - mean
            centered.append(value)
            energy += value * value
    except (MemoryError, OverflowError) as exc:
        raise AutoCastManualRequired() from exc
    rms = math.sqrt(energy / frame_length) / 32_768.0
    if not math.isfinite(rms) or rms < _MIN_WINDOW_RMS:
        return None

    minimum_lag = max(2, int(_PITCH_ANALYSIS_SAMPLE_RATE / _MAX_PITCH_HZ))
    maximum_lag = min(
        frame_length - 2,
        int(_PITCH_ANALYSIS_SAMPLE_RATE / _MIN_PITCH_HZ),
    )
    differences = array("d", [0.0])
    try:
        for lag in range(1, maximum_lag + 1):
            _ensure_classifier_active(deadline_monotonic, stop_requested)
            difference = 0.0
            count = 0
            for step, index in enumerate(
                range(0, frame_length - lag, _PITCH_DIFFERENCE_STRIDE)
            ):
                if step % 256 == 0:
                    _ensure_classifier_active(deadline_monotonic, stop_requested)
                delta = float(centered[index]) - float(centered[index + lag])
                difference += delta * delta
                count += 1
            differences.append(difference / max(1, count))
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc

    normalized = array("d", [1.0])
    cumulative = 0.0
    for lag in range(1, maximum_lag + 1):
        if lag % 64 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        cumulative += float(differences[lag])
        normalized.append(
            (float(differences[lag]) * lag / cumulative)
            if cumulative > 0.0
            else 1.0
        )

    candidate = 0
    lag = minimum_lag
    while lag <= maximum_lag:
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        if normalized[lag] < _PITCH_YIN_THRESHOLD:
            while (
                lag < maximum_lag
                and normalized[lag + 1] < normalized[lag]
            ):
                _ensure_classifier_active(deadline_monotonic, stop_requested)
                lag += 1
            candidate = lag
            break
        lag += 1
    if not candidate:
        candidate = minimum_lag
        for current_lag in range(minimum_lag + 1, maximum_lag + 1):
            _ensure_classifier_active(deadline_monotonic, stop_requested)
            if normalized[current_lag] < normalized[candidate]:
                candidate = current_lag
        if normalized[candidate] > _PITCH_YIN_MAXIMUM:
            return None

    refined_lag = float(candidate)
    if minimum_lag < candidate < maximum_lag:
        left = float(normalized[candidate - 1])
        center = float(normalized[candidate])
        right = float(normalized[candidate + 1])
        curvature = left - (2.0 * center) + right
        if abs(curvature) > 1e-12:
            refined_lag += max(-0.5, min(0.5, 0.5 * (left - right) / curvature))
    if refined_lag <= 0.0:
        return None
    estimated_hz = _PITCH_ANALYSIS_SAMPLE_RATE / refined_lag
    confidence = max(0.0, min(1.0, 1.0 - float(normalized[candidate])))
    if (
        not math.isfinite(estimated_hz)
        or not _MIN_PITCH_HZ <= estimated_hz <= _MAX_PITCH_HZ
        or confidence < _MIN_PITCH_FRAME_CONFIDENCE
    ):
        return None
    return estimated_hz, confidence


def _spectral_projection_power(
    centered: list[float],
    energy: float,
    frequency_hz: float,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> float:
    phase_step = 2.0 * math.pi * frequency_hz / _PITCH_ANALYSIS_SAMPLE_RATE
    phase_cos = 1.0
    phase_sin = 0.0
    step_cos = math.cos(phase_step)
    step_sin = math.sin(phase_step)
    projection_cos = 0.0
    projection_sin = 0.0
    for index, value in enumerate(centered):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        projection_cos += value * phase_cos
        projection_sin += value * phase_sin
        next_cos = (phase_cos * step_cos) - (phase_sin * step_sin)
        phase_sin = (phase_sin * step_cos) + (phase_cos * step_sin)
        phase_cos = next_cos
    return (
        2.0
        * ((projection_cos * projection_cos) + (projection_sin * projection_sin))
        / (len(centered) * energy)
        if centered and energy > 0.0
        else 0.0
    )


def _fft_competing_peak(
    centered: list[float],
    energy: float,
    harmonic_frequencies: list[float],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float]:
    """Find the strongest non-harmonic pitch bin with a bounded radix-2 FFT."""

    if len(centered) > _COMPETING_FFT_SIZE or energy <= 0.0:
        return math.inf, 0.0
    spectrum = [complex(value, 0.0) for value in centered]
    spectrum.extend([0j] * (_COMPETING_FFT_SIZE - len(spectrum)))

    swap_index = 0
    for index in range(1, _COMPETING_FFT_SIZE):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        bit = _COMPETING_FFT_SIZE >> 1
        while swap_index & bit:
            swap_index ^= bit
            bit >>= 1
        swap_index ^= bit
        if index < swap_index:
            spectrum[index], spectrum[swap_index] = (
                spectrum[swap_index],
                spectrum[index],
            )

    block_size = 2
    while block_size <= _COMPETING_FFT_SIZE:
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        angle = -2.0 * math.pi / block_size
        twiddle_step = complex(math.cos(angle), math.sin(angle))
        half = block_size // 2
        for block_start in range(0, _COMPETING_FFT_SIZE, block_size):
            twiddle = 1.0 + 0.0j
            for offset in range(half):
                if offset % 256 == 0:
                    _ensure_classifier_active(deadline_monotonic, stop_requested)
                even = spectrum[block_start + offset]
                odd = spectrum[block_start + offset + half] * twiddle
                spectrum[block_start + offset] = even + odd
                spectrum[block_start + offset + half] = even - odd
                twiddle *= twiddle_step
        block_size *= 2

    minimum_bin = math.ceil(
        _MIN_PITCH_HZ * _COMPETING_FFT_SIZE / _PITCH_ANALYSIS_SAMPLE_RATE
    )
    maximum_bin = math.floor(
        _MAX_PITCH_HZ * _COMPETING_FFT_SIZE / _PITCH_ANALYSIS_SAMPLE_RATE
    )
    strongest = 0.0
    strongest_hz = 0.0
    for bin_index in range(minimum_bin, maximum_bin + 1):
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        frequency_hz = (
            bin_index * _PITCH_ANALYSIS_SAMPLE_RATE / _COMPETING_FFT_SIZE
        )
        if any(
            abs(frequency_hz - harmonic_hz) <= _HARMONIC_EXCLUSION_HZ
            for harmonic_hz in harmonic_frequencies
        ):
            continue
        magnitude = abs(spectrum[bin_index])
        power = 2.0 * magnitude * magnitude / (len(centered) * energy)
        if power > strongest:
            strongest = power
            strongest_hz = frequency_hz
    return strongest, strongest_hz


def _frame_competing_pitch(
    frame: array,
    estimated_hz: float,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float]:
    sampled: list[float] = []
    total = 0.0
    for index, sample in enumerate(frame):
        if index % 128 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        value = float(sample)
        sampled.append(value)
        total += value
    if not sampled:
        return math.inf, 0.0
    mean = total / len(sampled)
    centered: list[float] = []
    energy = 0.0
    for index, value in enumerate(sampled):
        if index % 128 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        normalized = value - mean
        centered.append(normalized)
        energy += normalized * normalized
    if not math.isfinite(energy) or energy <= 0.0:
        return math.inf, 0.0

    component_count = min(
        _MAX_HARMONIC_PURITY_COMPONENTS,
        int(_MAX_HARMONIC_PURITY_HZ / estimated_hz),
    )
    harmonic_frequencies = [
        estimated_hz * harmonic
        for harmonic in range(1, component_count + 1)
    ]
    harmonic_purity = 0.0
    for harmonic_hz in harmonic_frequencies:
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        harmonic_purity += _spectral_projection_power(
            centered,
            energy,
            harmonic_hz,
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )
    if not math.isfinite(harmonic_purity) or harmonic_purity <= 0.0:
        return math.inf, 0.0
    competing_power, competing_hz = _fft_competing_peak(
        centered,
        energy,
        harmonic_frequencies,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
    )
    return competing_power / harmonic_purity, competing_hz


def _pitch_spectrum_metrics(
    samples: array,
    estimated_hz: float,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float]:
    """Return full-window harmonic purity and fundamental share."""

    sampled: list[float] = []
    for index, sample in enumerate(samples):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        sampled.append(float(sample))
    if not sampled:
        return 0.0, 0.0
    total = 0.0
    for index, value in enumerate(sampled):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        total += value
    mean = total / len(sampled)
    centered: list[float] = []
    energy = 0.0
    for index, value in enumerate(sampled):
        if index % 256 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        normalized = value - mean
        centered.append(normalized)
        energy += normalized * normalized
    if not math.isfinite(energy) or energy <= 0.0:
        return 0.0, 0.0

    component_count = min(
        _MAX_HARMONIC_PURITY_COMPONENTS,
        int(_MAX_HARMONIC_PURITY_HZ / estimated_hz),
    )
    harmonic_frequencies = [
        estimated_hz * harmonic
        for harmonic in range(1, component_count + 1)
    ]
    harmonic_powers: list[float] = []
    for harmonic in range(1, component_count + 1):
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        harmonic_powers.append(
            _spectral_projection_power(
                centered,
                energy,
                estimated_hz * harmonic,
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
        )
    purity = sum(harmonic_powers)
    if not math.isfinite(purity) or purity <= 0.0:
        return 0.0, 0.0
    fundamental_share = harmonic_powers[0] / purity if harmonic_powers else 0.0
    return purity, fundamental_share


def _refine_full_rate_pitch(
    samples: array,
    estimated_hz: float,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> float:
    """Refine one bounded estimate at 16 kHz without a broad lag search."""

    if not math.isfinite(estimated_hz) or estimated_hz <= 0.0:
        return estimated_hz
    total = 0.0
    for index, sample in enumerate(samples):
        if index % 1_024 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        total += float(sample)
    mean = total / len(samples)
    centered = array("f")
    try:
        centered.extend(float(sample) - mean for sample in samples)
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc

    minimum_lag = max(1, int(PCM_SAMPLE_RATE / _MAX_PITCH_HZ))
    maximum_lag = min(len(centered) - 2, int(PCM_SAMPLE_RATE / _MIN_PITCH_HZ))
    center_lag = int(round(PCM_SAMPLE_RATE / estimated_hz))
    start_lag = max(minimum_lag, center_lag - 2)
    end_lag = min(maximum_lag, center_lag + 2)
    scores: dict[int, float] = {}
    for lag in range(start_lag, end_lag + 1):
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        cross = 0.0
        left_energy = 0.0
        right_energy = 0.0
        for step, index in enumerate(
            range(lag, len(centered), _AUTOCORRELATION_STRIDE)
        ):
            if step % 512 == 0:
                _ensure_classifier_active(deadline_monotonic, stop_requested)
            left = float(centered[index])
            right = float(centered[index - lag])
            cross += left * right
            left_energy += left * left
            right_energy += right * right
        denominator = math.sqrt(left_energy * right_energy)
        scores[lag] = cross / denominator if denominator > 0.0 else 0.0
    if not scores:
        return estimated_hz

    best_lag = max(scores, key=scores.__getitem__)
    best_score = scores[best_lag]
    if not math.isfinite(best_score) or best_score < 0.35:
        return estimated_hz
    refined_lag = float(best_lag)
    if best_lag - 1 in scores and best_lag + 1 in scores:
        left = scores[best_lag - 1]
        center = scores[best_lag]
        right = scores[best_lag + 1]
        curvature = left - (2.0 * center) + right
        if abs(curvature) > 1e-12:
            refined_lag += max(
                -0.5,
                min(0.5, 0.5 * (left - right) / curvature),
            )
    if refined_lag <= 0.0:
        return estimated_hz
    refined_hz = PCM_SAMPLE_RATE / refined_lag
    if (
        not math.isfinite(refined_hz)
        or abs(refined_hz - estimated_hz) / estimated_hz > 0.05
    ):
        return estimated_hz
    return refined_hz


def _estimate_window_pitch(
    raw: bytes,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float] | None:
    _ensure_classifier_active(deadline_monotonic, stop_requested)
    if not isinstance(raw, bytes) or len(raw) != PCM_WINDOW_BYTES:
        return None

    samples = array("h")
    try:
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc
    if len(samples) != PCM_WINDOW_SAMPLES:
        return None

    analysis_samples = array("h")
    try:
        for offset in range(0, len(samples), _PITCH_ANALYSIS_DECIMATION):
            if offset % 2_048 == 0:
                _ensure_classifier_active(deadline_monotonic, stop_requested)
            block = samples[offset : offset + _PITCH_ANALYSIS_DECIMATION]
            if len(block) != _PITCH_ANALYSIS_DECIMATION:
                return None
            analysis_samples.append(int(round(sum(block) / len(block))))
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc

    maximum_lag = int(_PITCH_ANALYSIS_SAMPLE_RATE / _MIN_PITCH_HZ)
    transient_bytes = (
        len(raw)
        + len(samples) * samples.itemsize
        + len(analysis_samples) * analysis_samples.itemsize
        + len(samples) * 4
        + _PITCH_FRAME_SAMPLES * 4
        + (maximum_lag + 1) * 16
    )
    if transient_bytes > MAX_WORK_BUFFER_BYTES:
        raise AutoCastManualRequired()

    estimates: list[tuple[float, float, float, float]] = []
    for offset in range(
        0,
        len(analysis_samples) - _PITCH_FRAME_SAMPLES + 1,
        _PITCH_FRAME_HOP_SAMPLES,
    ):
        _ensure_classifier_active(deadline_monotonic, stop_requested)
        frame = analysis_samples[offset : offset + _PITCH_FRAME_SAMPLES]
        estimate = _estimate_frame_pitch_yin(
            frame,
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )
        if estimate is not None:
            competing_ratio, competing_hz = _frame_competing_pitch(
                frame,
                estimate[0],
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
            estimates.append(
                (estimate[0], estimate[1], competing_ratio, competing_hz)
            )
    if len(estimates) < _MIN_PITCH_FRAMES:
        return None

    median_hz = _bounded_median([item[0] for item in estimates])
    if not math.isfinite(median_hz) or median_hz <= 0.0:
        return None
    inliers = [
        item
        for item in estimates
        if abs(item[0] - median_hz) / median_hz
        <= _MAX_FRAME_RELATIVE_PITCH_DEVIATION
    ]
    minimum_inliers = max(_MIN_PITCH_FRAMES, math.ceil(len(estimates) * 0.60))
    if len(inliers) < minimum_inliers:
        return None
    competing_frames = [
        item
        for item in inliers
        if item[2] >= _MAX_COMPETING_PITCH_RATIO and item[3] > 0.0
    ]
    if len(competing_frames) >= _MIN_COMPETING_PITCH_FRAMES:
        for position, first in enumerate(competing_frames):
            for second in competing_frames[position + 1 :]:
                _ensure_classifier_active(deadline_monotonic, stop_requested)
                if (
                    abs(first[3] - second[3])
                    <= _COMPETING_PITCH_STABILITY_HZ
                ):
                    return None
    refined_hz = _bounded_median([item[0] for item in inliers])
    refined_hz = _refine_full_rate_pitch(
        samples,
        refined_hz,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
    )
    relative_spread = _bounded_median(
        [abs(item[0] - refined_hz) / refined_hz for item in inliers]
    )
    stability = max(0.0, 1.0 - (relative_spread / 0.32))
    support = 0.5 if len(inliers) == 1 else min(1.0, len(inliers) / 4.0)
    periodicity = _bounded_median([item[1] for item in inliers])
    confidence = max(
        0.0,
        min(1.0, (0.60 * periodicity) + (0.25 * stability) + (0.15 * support)),
    )
    harmonic_purity, fundamental_share = _pitch_spectrum_metrics(
        analysis_samples,
        refined_hz,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
    )
    if (
        confidence < MIN_REGISTER_CONFIDENCE
        or harmonic_purity < _MIN_HARMONIC_SERIES_PURITY
        or fundamental_share < _MIN_FUNDAMENTAL_HARMONIC_SHARE
    ):
        return None
    return refined_hz, confidence


def classify_speaker_registers(
    pcm_path: str,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict]:
    """Classify bounded speaker ranges from streaming mono 16 kHz s16le PCM."""

    if not isinstance(ranges_by_speaker, dict) or not ranges_by_speaker:
        raise AutoCastManualRequired()
    if not callable(stop_requested):
        raise AutoCastManualRequired()
    try:
        absolute_deadline = float(deadline_monotonic)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastManualRequired() from exc
    if not math.isfinite(absolute_deadline):
        raise AutoCastManualRequired()

    labels = ordered_auto_speaker_labels(
        {"speaker_id": speaker_id} for speaker_id in ranges_by_speaker
    )
    if not labels or len(labels) != len(ranges_by_speaker):
        raise AutoCastManualRequired()
    _ensure_classifier_active(absolute_deadline, stop_requested)

    sampled_job_seconds = 0.0
    maximum_accepted_windows = int(
        MAX_SPEAKER_VOICED_SECONDS / _PCM_WINDOW_SECONDS
    )
    maximum_job_windows = int(MAX_JOB_SAMPLE_SECONDS / _PCM_WINDOW_SECONDS)
    candidate_windows_per_speaker = max(
        maximum_accepted_windows,
        maximum_job_windows // len(labels),
    )
    results: dict[str, dict] = {}
    try:
        with open(str(pcm_path or ""), "rb") as handle:
            for speaker_id in labels:
                _ensure_classifier_active(absolute_deadline, stop_requested)
                offsets = _speaker_window_offsets(
                    ranges_by_speaker.get(speaker_id),
                    deadline_monotonic=absolute_deadline,
                    stop_requested=stop_requested,
                    max_windows=candidate_windows_per_speaker,
                )

                frequencies: list[float] = []
                confidences: list[float] = []
                for offset in offsets:
                    sampled_job_seconds += _PCM_WINDOW_SECONDS
                    if sampled_job_seconds > MAX_JOB_SAMPLE_SECONDS + 1e-12:
                        raise AutoCastManualRequired()
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    handle.seek(offset)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    raw = handle.read(PCM_WINDOW_BYTES)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    if len(raw) != PCM_WINDOW_BYTES:
                        raise AutoCastManualRequired()
                    estimate = _estimate_window_pitch(
                        raw,
                        deadline_monotonic=absolute_deadline,
                        stop_requested=stop_requested,
                    )
                    if estimate is None:
                        continue
                    frequency, confidence = estimate
                    frequencies.append(frequency)
                    confidences.append(confidence)
                    if len(frequencies) >= maximum_accepted_windows:
                        break

                _ensure_classifier_active(absolute_deadline, stop_requested)
                register, _median_hz, confidence, inlier_count = (
                    _stable_register_evidence(frequencies, confidences)
                )
                voiced_seconds = inlier_count * _PCM_WINDOW_SECONDS
                minimum_voiced_seconds = (
                    _PCM_WINDOW_SECONDS
                    if inlier_count == 1
                    else _MIN_VOICED_SECONDS
                )
                if (
                    voiced_seconds < minimum_voiced_seconds
                    or voiced_seconds > MAX_SPEAKER_VOICED_SECONDS + 1e-12
                ):
                    raise AutoCastManualRequired()
                results[speaker_id] = {
                    "speaker_id": speaker_id,
                    "voice_register": register,
                    "confidence": round(float(confidence), 6),
                    "voiced_seconds": round(float(voiced_seconds), 3),
                    "sample_count": int(inlier_count * PCM_WINDOW_SAMPLES),
                    "reason": "classified",
                }
                _ensure_classifier_active(absolute_deadline, stop_requested)
    except AutoCastManualRequired:
        raise
    except (OSError, ValueError, TypeError, OverflowError, MemoryError) as exc:
        raise AutoCastManualRequired() from exc

    if not results or sampled_job_seconds > MAX_JOB_SAMPLE_SECONDS + 1e-12:
        raise AutoCastManualRequired()
    return results
